"""The interview results report: who is ranked, when it's ready, and the
PDF it prints.

The promise under test: the final score is HR's plain average --
(interviewer 1 + interviewer 2 + interviewer 3) / 3 -- while the
Candidate Profile keeps its own 30/30/40 consensus untouched; each
round shows the interviewer's own recommendation, not one read off the
score; the report waits while anyone is still being interviewed,
candidates who never reached the interviews don't hold it up, and the
PDF carries the same order.
"""

from io import BytesIO

from pypdf import PdfReader
from sqlalchemy.orm import object_session

from app.models.enums import ApplicationStatus, UserRole
from app.models.requisition_evaluator import RequisitionEvaluator
from app.services.applications import create_application_with_stage_instances
from tests.conftest import auth_headers, give_confirmed_time
from tests.test_decision_support import _advance_to, _all_items

WORKFLOW = [
    "document_upload",
    "skill_matching",
    "examination",
    "interview_round_1",
    "interview_round_2",
    "interview_round_3",
    "final_decision",
]
ROUNDS = ["interview_round_1", "interview_round_2", "interview_round_3"]


def _hr(client):
    return auth_headers(client, "hr-test@arkivetesting.com")


def _panel(db_session, job, make_user, evaluator):
    """One interviewer per round, on the job's pool once."""
    panel = [evaluator] + [
        make_user(f"panel-{i}@arkivetesting.com", UserRole.evaluator) for i in (2, 3)
    ]
    for person in panel:
        db_session.add(RequisitionEvaluator(requisition_id=job.id, evaluator_id=person.id))
    db_session.flush()
    return panel


def _candidate(db_session, job, make_user, name):
    person = make_user(f"{name.lower().replace(' ', '.')}@arkivetesting.com", UserRole.applicant)
    person.full_name = name
    application = create_application_with_stage_instances(db_session, applicant_id=person.id, requisition=job)
    db_session.flush()
    return application


def _score(client, application, interviewer, stage, rating, recommendation="recommended"):
    headers = _hr(client)
    resp = client.post(
        f"/hr/applications/{application.id}/interview-assignment",
        json={"stage_type": stage, "evaluator_id": interviewer.id},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    eval_headers = auth_headers(client, interviewer.email)
    queue = client.get("/evaluator/interviews", headers=eval_headers).json()
    stage_instance_id = next(
        i["stage_instance_id"] for i in queue if i["application_id"] == application.id and not i["already_evaluated"]
    )
    give_confirmed_time(object_session(application), stage_instance_id)
    resp = client.post(
        f"/evaluator/interviews/{stage_instance_id}/evaluate",
        json={"item_ratings": _all_items(rating), "remarks": "Evaluated.", "recommendation": recommendation},
        headers=eval_headers,
    )
    assert resp.status_code == 200, resp.text


def _interview_fully(client, application, panel, ratings, recommendation="recommended"):
    _advance_to(client, application, "interview_round_3", _hr(client), WORKFLOW)
    for interviewer, stage, rating in zip(panel, ROUNDS, ratings):
        _score(client, application, interviewer, stage, rating, recommendation)


def _report(client, job):
    resp = client.get(f"/hr/requisitions/{job.id}/interview-report", headers=_hr(client))
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_final_score_is_the_plain_average_of_the_interviewers(
    client, db_session, make_job, make_user, hr_admin, evaluator
):
    """A: 4 + 4 + 5 = 13, / 3 = 4.33. B: 5 + 5 + 2 = 12, / 3 = 4.00. On
    the profile's 30/30/40 consensus B would be 3.80 and A 4.40 -- the
    report must use the plain average, and must leave the profile's own
    number exactly as it was."""
    job = make_job(WORKFLOW, title="Systems Administrator")
    panel = _panel(db_session, job, make_user, evaluator)
    a = _candidate(db_session, job, make_user, "Ana Reyes")
    b = _candidate(db_session, job, make_user, "Ben Santos")
    c = _candidate(db_session, job, make_user, "Carla Cruz")
    _interview_fully(client, a, panel, [4, 4, 5], "highly_recommended")
    _interview_fully(client, b, panel, [5, 5, 2])
    _interview_fully(client, c, panel, [3, 3, 3], "not_recommended")

    report = _report(client, job)
    assert report["ready"] is True
    assert [(e["applicant_name"], e["rank"], e["final_score"]) for e in report["entries"]] == [
        ("Ana Reyes", 1, 4.33),
        ("Ben Santos", 2, 4.0),
        ("Carla Cruz", 3, 3.0),
    ]
    profile = client.get(f"/hr/applications/{b.id}/profile", headers=_hr(client)).json()
    assert profile["evaluator_consensus_score"] == 3.8

    top = report["entries"][0]
    assert [cell["score"] for cell in top["cells"]] == [4.0, 4.0, 5.0]
    assert [cell["tier_label"] for cell in top["cells"]] == ["Qualified", "Qualified", "Highly Qualified"]
    assert top["cells"][0]["recommendation_label"] == "Highly Recommended"
    assert top["partial"] is False
    # one person ran each round for everyone, so the report names them once
    assert [r["evaluator_name"] for r in report["rounds"]] == [p.full_name for p in panel]


def test_the_recommendation_is_the_interviewers_pick_not_the_score(
    client, db_session, make_job, make_user, hr_admin, evaluator
):
    """Straight 5s with "Not Recommended" on the form stay "Not
    Recommended" -- the form's three options decide it, whatever the
    score."""
    job = make_job(WORKFLOW)
    panel = _panel(db_session, job, make_user, evaluator)
    application = _candidate(db_session, job, make_user, "Ana Reyes")
    _interview_fully(client, application, panel, [5, 5, 5], "not_recommended")

    (entry,) = _report(client, job)["entries"]
    assert {cell["recommendation_label"] for cell in entry["cells"]} == {"Not Recommended"}
    resp = client.get(f"/hr/requisitions/{job.id}/interview-report/pdf", headers=_hr(client))
    text = "".join(page.extract_text() for page in PdfReader(BytesIO(resp.content)).pages)
    assert "5.00 Highly Qualified (Not Recommended)" in " ".join(text.split())


def test_waits_while_anyone_is_still_being_interviewed(
    client, db_session, make_job, make_user, hr_admin, evaluator
):
    job = make_job(WORKFLOW)
    panel = _panel(db_session, job, make_user, evaluator)
    done = _candidate(db_session, job, make_user, "Ana Reyes")
    _interview_fully(client, done, panel, [4, 4, 4])

    midway = _candidate(db_session, job, make_user, "Ben Santos")
    _advance_to(client, midway, "interview_round_1", _hr(client), WORKFLOW)
    _score(client, midway, panel[0], "interview_round_1", 4)
    resp = client.post(
        f"/applications/{midway.id}/transition",
        json={"target_stage": "interview_round_2"},
        headers=_hr(client),
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        f"/hr/applications/{midway.id}/interview-assignment",
        json={"stage_type": "interview_round_2", "evaluator_id": panel[1].id},
        headers=_hr(client),
    )
    assert resp.status_code == 200, resp.text

    report = _report(client, job)
    assert report["ready"] is False
    assert [p["applicant_name"] for p in report["pending"]] == ["Ben Santos"]
    assert report["pending"][0]["waiting_on"] == [
        f"Interview Round 2 ({panel[1].full_name})",
        "Interview Round 3 (no interviewer assigned yet)",
    ]
    resp = client.get(f"/hr/requisitions/{job.id}/interview-report/pdf", headers=_hr(client))
    assert resp.status_code == 409


def test_candidates_before_the_interviews_do_not_hold_it_up(
    client, db_session, make_job, make_user, hr_admin, evaluator
):
    job = make_job(WORKFLOW)
    panel = _panel(db_session, job, make_user, evaluator)
    _interview_fully(client, _candidate(db_session, job, make_user, "Ana Reyes"), panel, [4, 4, 4])
    still_at_exam = _candidate(db_session, job, make_user, "Ben Santos")
    _advance_to(client, still_at_exam, "examination", _hr(client), WORKFLOW)

    report = _report(client, job)
    assert report["ready"] is True
    assert [e["applicant_name"] for e in report["entries"]] == ["Ana Reyes"]
    assert report["pending"] == [] and report["excluded"] == []


def test_a_withdrawn_candidate_is_named_but_not_ranked(
    client, db_session, make_job, make_user, hr_admin, evaluator
):
    job = make_job(WORKFLOW)
    panel = _panel(db_session, job, make_user, evaluator)
    _interview_fully(client, _candidate(db_session, job, make_user, "Ana Reyes"), panel, [4, 4, 4])
    gone = _candidate(db_session, job, make_user, "Ben Santos")
    _advance_to(client, gone, "interview_round_1", _hr(client), WORKFLOW)
    gone.status = ApplicationStatus.withdrawn
    db_session.flush()

    report = _report(client, job)
    assert report["ready"] is True
    assert report["excluded"] == [{"applicant_name": "Ben Santos", "reason": "Withdrew their application."}]


def test_equal_scores_share_a_rank(client, db_session, make_job, make_user, hr_admin, evaluator):
    job = make_job(WORKFLOW)
    panel = _panel(db_session, job, make_user, evaluator)
    _interview_fully(client, _candidate(db_session, job, make_user, "Ben Santos"), panel, [4, 4, 4])
    _interview_fully(client, _candidate(db_session, job, make_user, "Ana Reyes"), panel, [4, 4, 4])
    _interview_fully(client, _candidate(db_session, job, make_user, "Carla Cruz"), panel, [3, 3, 3])

    report = _report(client, job)
    assert [(e["applicant_name"], e["rank"]) for e in report["entries"]] == [
        ("Ana Reyes", 1),
        ("Ben Santos", 1),
        ("Carla Cruz", 3),
    ]


def test_a_round_moved_past_without_a_scorecard_averages_the_rest(
    client, db_session, make_job, make_user, hr_admin, evaluator
):
    """A round with no scorecard is left out of the average rather than
    counted as a zero: (4 + 5) / 2 -- and the report marks it."""
    job = make_job(WORKFLOW)
    panel = _panel(db_session, job, make_user, evaluator)
    application = _candidate(db_session, job, make_user, "Ana Reyes")
    _advance_to(client, application, "interview_round_3", _hr(client), WORKFLOW)
    _score(client, application, panel[0], "interview_round_1", 4)
    _score(client, application, panel[1], "interview_round_2", 5)
    _advance_to(client, application, "final_decision", _hr(client), WORKFLOW)

    report = _report(client, job)
    assert report["ready"] is True
    (entry,) = report["entries"]
    assert entry["final_score"] == 4.5
    assert entry["partial"] is True
    assert entry["cells"][2]["no_scorecard"] is True


def test_the_pdf_prints_the_same_ranking(client, db_session, make_job, make_user, hr_admin, evaluator):
    job = make_job(WORKFLOW, title="Systems Administrator")
    panel = _panel(db_session, job, make_user, evaluator)
    _interview_fully(client, _candidate(db_session, job, make_user, "Carla Cruz"), panel, [3, 3, 3])
    _interview_fully(client, _candidate(db_session, job, make_user, "Ana Reyes"), panel, [4, 4, 5], "highly_recommended")

    resp = client.get(f"/hr/requisitions/{job.id}/interview-report/pdf", headers=_hr(client))
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert 'filename="interview-results-systems-administrator.pdf"' in resp.headers["content-disposition"]
    text = " ".join("\n".join(page.extract_text() for page in PdfReader(BytesIO(resp.content)).pages).split())
    assert "Systems Administrator" in text
    assert text.index("Ana Reyes") < text.index("Carla Cruz")
    assert "4.00 Qualified (Highly Recommended)" in text and "4.33" in text
    # a rating on each of the six interviewer scores and none on the final
    # score: Ana 4/4/5 is Qualified, Qualified, Highly Qualified; Carla
    # 3/3/3 is Qualified three times
    assert text.count("Qualified") == 6
    # the ranking and nothing else
    for gone in ("Prepared by", "Scores by area", "How to read"):
        assert gone not in text


def test_a_job_without_interview_rounds_has_no_report(client, make_job, hr_admin):
    job = make_job(["document_upload", "skill_matching", "final_decision"])
    report = _report(client, job)
    assert report["has_interviews"] is False and report["ready"] is False
    assert client.get(f"/hr/requisitions/{job.id}/interview-report/pdf", headers=_hr(client)).status_code == 409


def test_only_hr_can_read_the_report(client, make_job, applicant):
    job = make_job(WORKFLOW)
    headers = auth_headers(client, applicant.email)
    assert client.get(f"/hr/requisitions/{job.id}/interview-report", headers=headers).status_code == 403
    assert client.get(f"/hr/requisitions/{job.id}/interview-report/pdf", headers=headers).status_code == 403
