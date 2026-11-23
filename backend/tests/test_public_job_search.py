"""Server-side search/filter/pagination on the public job board.

Covers GET /public/jobs's query params. The endpoint is unauthenticated, so
the page-size cap is part of the contract, not just an ergonomic default.

Per conftest, tests share the real Postgres instance (rolled back per
test), so whatever the dev database already holds is visible here.
Every assertion is scoped by MARK -- a nonsense token seeded into this
file's own rows -- rather than by global counts, which would break the
moment someone seeds another job.
"""

from datetime import date, timedelta

WORKFLOW = ["document_upload", "skill_matching", "final_decision"]

MARK = "Qzx7Marker"
DEPT_A = f"{MARK} Computing"
DEPT_B = f"{MARK} Library"
DEPT_C = f"{MARK} Sciences"


def _seed(make_job, db_session):
    make_job(
        WORKFLOW,
        title=f"{MARK} Network Administrator",
        department=DEPT_A,
        description="Manages campus network infrastructure.",
        requirements=f"A relevant certification (e.g. CCNA{MARK}) is a plus.",
    )
    make_job(
        WORKFLOW,
        title=f"{MARK} Reference Librarian",
        department=DEPT_B,
        description="Provides research assistance to students.",
        qualifications=f"Master's in LibraryScience{MARK}.",
    )
    make_job(
        WORKFLOW,
        title=f"{MARK} Data Science Professor",
        department=DEPT_C,
        description="Teaches statistics and machine learning.",
    )
    db_session.commit()


def _titles(body) -> list[str]:
    return [item["title"] for item in body["items"]]


def test_returns_items_total_and_department_options(client, make_job, db_session):
    _seed(make_job, db_session)

    body = client.get("/public/jobs", params={"q": MARK}).json()

    assert body["total"] == 3
    assert len(body["items"]) == 3
    # departments is global (not narrowed by q) so the filter controls stay
    # usable, and it's sorted + de-duplicated for a stable UI.
    assert {DEPT_A, DEPT_B, DEPT_C} <= set(body["departments"])
    assert body["departments"] == sorted(set(body["departments"]))


def test_q_matches_title_case_insensitively(client, make_job, db_session):
    _seed(make_job, db_session)

    body = client.get("/public/jobs", params={"q": f"{MARK.lower()} network"}).json()

    assert _titles(body) == [f"{MARK} Network Administrator"]


def test_q_searches_requirements_not_just_title(client, make_job, db_session):
    """The point of spanning requirements: a concrete skill finds the posting
    that asks for it even though the word appears nowhere in the title."""
    _seed(make_job, db_session)

    body = client.get("/public/jobs", params={"q": f"CCNA{MARK}"}).json()

    assert _titles(body) == [f"{MARK} Network Administrator"]


def test_q_searches_qualifications(client, make_job, db_session):
    _seed(make_job, db_session)

    body = client.get("/public/jobs", params={"q": f"LibraryScience{MARK}"}).json()

    assert _titles(body) == [f"{MARK} Reference Librarian"]


def test_q_with_no_match_returns_empty_but_keeps_department_options(client, make_job, db_session):
    _seed(make_job, db_session)

    body = client.get("/public/jobs", params={"q": f"{MARK}nosuchthing"}).json()

    assert body["total"] == 0
    assert body["items"] == []
    # The filter controls must not vanish just because this query matched
    # nothing — otherwise the user can't change their mind.
    assert {DEPT_A, DEPT_B, DEPT_C} <= set(body["departments"])


def test_like_wildcards_are_treated_literally(client, make_job, db_session):
    """Unescaped, "100%" would match every row via the LIKE wildcard."""
    _seed(make_job, db_session)
    make_job(WORKFLOW, title=f"{MARK} 100% Remote Role", department=DEPT_A)
    db_session.commit()

    body = client.get("/public/jobs", params={"q": "100%"}).json()

    assert _titles(body) == [f"{MARK} 100% Remote Role"]


def test_department_filter(client, make_job, db_session):
    _seed(make_job, db_session)

    body = client.get("/public/jobs", params={"department": DEPT_A}).json()

    assert _titles(body) == [f"{MARK} Network Administrator"]


def test_department_filter_accepts_multiple_values(client, make_job, db_session):
    _seed(make_job, db_session)

    body = client.get("/public/jobs", params=[("department", DEPT_A), ("department", DEPT_C)]).json()

    assert body["total"] == 2
    assert {item["department"] for item in body["items"]} == {DEPT_A, DEPT_C}


def test_q_and_department_combine_as_and(client, make_job, db_session):
    _seed(make_job, db_session)

    # "Network Administrator" matches q, but lives in DEPT_A, not DEPT_C.
    body = client.get("/public/jobs", params={"q": "Network", "department": DEPT_C}).json()

    assert body["total"] == 0


def test_pagination_slices_items_but_total_reflects_full_match(client, make_job, db_session):
    _seed(make_job, db_session)

    page = client.get("/public/jobs", params={"q": MARK, "limit": 2, "offset": 0}).json()
    assert page["total"] == 3, "total is the match count, not the page size"
    assert len(page["items"]) == 2

    rest = client.get("/public/jobs", params={"q": MARK, "limit": 2, "offset": 2}).json()
    assert rest["total"] == 3
    assert len(rest["items"]) == 1

    seen = [item["id"] for item in page["items"]] + [item["id"] for item in rest["items"]]
    assert len(set(seen)) == 3, "pages must not overlap or drop rows"


def test_limit_above_cap_is_rejected(client):
    assert client.get("/public/jobs", params={"limit": 10_000}).status_code == 422


def test_negative_offset_is_rejected(client):
    assert client.get("/public/jobs", params={"offset": -1}).status_code == 422


def test_expired_jobs_stay_excluded_when_searching(client, make_job, db_session):
    """Filtering must narrow the public set, never widen it."""
    _seed(make_job, db_session)
    expired = make_job(WORKFLOW, title=f"{MARK} Expired Network Role", department=DEPT_A)
    expired.application_deadline = date.today() - timedelta(days=1)
    db_session.commit()

    body = client.get("/public/jobs", params={"q": f"{MARK} Network"}).json()

    assert _titles(body) == [f"{MARK} Network Administrator"]


def test_job_detail_names_its_stages_in_the_jobs_own_words(client, db_session, make_job):
    """The applicant's job browser lists a role's hiring process from
    this -- so a custom interview-round name has to come through."""
    job = make_job(["document_upload", "interview_round_1", "final_decision"], title=f"{MARK} Custom Rounds")
    job.interview_round_labels = {"interview_round_1": "Teaching Demonstration"}
    db_session.commit()

    detail = client.get(f"/public/jobs/{job.id}").json()

    assert detail["workflow_definition"] == ["document_upload", "interview_round_1", "final_decision"]
    assert detail["stage_labels"][1] == "Teaching Demonstration"
    assert len(detail["stage_labels"]) == 3
