"""Tests for the notifications inbox -- the bell's list, and the
Notifications page's folders, search, counts and reading pane (panel
revision list, 15 Oct 2026; revisions 2.0, 16 Oct 2026)."""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.models.enums import ApplicationStatus, StageType
from app.models.notification import Notification
from app.models.stage_instance import StageInstance
from app.services.account_erasure import erase_applicant
from app.services.notifications import (
    DELETED_SENDER,
    OFFICE_SENDER,
    SYSTEM_SENDER,
    notify,
)
from tests.conftest import auth_headers

HR = "hr-test@arkivetesting.com"
APPLICANT = "applicant-test@arkivetesting.com"
EVALUATOR = "evaluator-test@arkivetesting.com"


def _seed(db_session, user, kinds, *, actor=None, application=None):
    made = [
        notify(
            db_session,
            user_id=user.id,
            actor_id=actor.id if actor else None,
            application_id=application.id if application else None,
            title=f"title {i}",
            message=f"notice {i}",
            kind=kind,
        )
        for i, kind in enumerate(kinds)
    ]
    db_session.flush()
    return made


def _inbox(client, email, **params):
    resp = client.get("/notifications", params=params, headers=auth_headers(client, email))
    assert resp.status_code == 200, resp.text
    return resp.json()


# ------------------------------------------------------------------ list


def test_the_list_carries_each_notice_kind_and_title(client, db_session, hr_admin):
    _seed(db_session, hr_admin, ["schedule", "decision"])

    body = _inbox(client, HR)

    by_message = {item["message"]: item for item in body["items"]}
    assert by_message["notice 0"]["kind"] == "schedule"
    assert by_message["notice 0"]["title"] == "title 0"
    assert by_message["notice 1"]["kind"] == "decision"


def test_filters_by_kind_and_the_unread_folder(client, db_session, hr_admin):
    made = _seed(db_session, hr_admin, ["schedule", "schedule", "decision"])
    made[0].read_at = datetime.now(timezone.utc)
    db_session.flush()

    schedule = _inbox(client, HR, kind="schedule")
    unread_schedule = _inbox(client, HR, kind="schedule", folder="unread")

    assert {i["message"] for i in schedule["items"]} >= {"notice 0", "notice 1"}
    assert all(i["kind"] == "schedule" for i in schedule["items"])
    assert all(i["read_at"] is None for i in unread_schedule["items"])
    assert "notice 0" not in {i["message"] for i in unread_schedule["items"]}


def test_pages_back_with_before_id(client, db_session, hr_admin):
    _seed(db_session, hr_admin, ["system"] * 5)

    first = _inbox(client, HR, limit=3)
    assert len(first["items"]) == 3
    assert first["has_more"] is True

    oldest = first["items"][-1]["id"]
    second = _inbox(client, HR, limit=3, before_id=oldest)
    assert all(item["id"] < oldest for item in second["items"])
    assert not {i["id"] for i in first["items"]} & {i["id"] for i in second["items"]}


def test_an_unknown_kind_or_folder_is_refused(client, hr_admin):
    headers = auth_headers(client, HR)
    assert client.get("/notifications", params={"kind": "gossip"}, headers=headers).status_code == 422
    assert client.get("/notifications", params={"folder": "spam"}, headers=headers).status_code == 422


# ---------------------------------------------------------------- sender


def test_an_applicant_sees_the_hr_office_never_the_staff_member(client, db_session, hr_admin, applicant):
    hr_admin.full_name = "Maria Santos"
    hr_admin.avatar_file = "maria.png"
    _seed(db_session, applicant, ["decision"], actor=hr_admin)

    resp = client.get("/notifications", headers=auth_headers(client, APPLICANT))

    item = resp.json()["items"][0]
    assert item["sender"] == {"kind": "office", "name": OFFICE_SENDER, "role": None, "avatar_url": None}
    # nowhere in the response, not just not in `sender`
    assert "Maria" not in resp.text
    assert "maria.png" not in resp.text
    assert HR not in resp.text


def test_a_notice_nobody_sent_comes_from_arkive(client, db_session, hr_admin, applicant):
    _seed(db_session, hr_admin, ["decision"])
    _seed(db_session, applicant, ["schedule"], actor=applicant)  # booked their own exam

    assert _inbox(client, HR)["items"][0]["sender"]["name"] == SYSTEM_SENDER
    assert _inbox(client, APPLICANT)["items"][0]["sender"] == {
        "kind": "system",
        "name": SYSTEM_SENDER,
        "role": None,
        "avatar_url": None,
    }


def test_staff_see_the_real_person_with_their_role_and_photo(client, db_session, hr_admin, evaluator):
    evaluator.full_name = "Dr. Jose Reyes"
    evaluator.job_title = "Dean, College of Engineering"
    evaluator.avatar_file = "jose.png"
    _seed(db_session, hr_admin, ["schedule"], actor=evaluator)

    sender = _inbox(client, HR)["items"][0]["sender"]

    assert sender == {
        "kind": "person",
        "name": "Dr. Jose Reyes",
        "role": "Evaluator · Dean, College of Engineering",
        "avatar_url": "/avatars/jose.png",
    }


def test_an_erased_sender_is_a_deleted_user_with_no_photo(client, db_session, hr_admin, applicant):
    applicant.avatar_file = "old.png"
    _seed(db_session, hr_admin, ["schedule"], actor=applicant)
    erase_applicant(db_session, applicant)
    db_session.flush()

    sender = _inbox(client, HR)["items"][0]["sender"]

    assert sender == {"kind": "person", "name": DELETED_SENDER, "role": None, "avatar_url": None}


def test_a_deactivated_sender_is_still_named_and_marked(client, db_session, hr_admin, evaluator):
    evaluator.full_name = "Ana Cruz"
    evaluator.is_active = False
    _seed(db_session, hr_admin, ["schedule"], actor=evaluator)

    sender = _inbox(client, HR)["items"][0]["sender"]

    assert sender["name"] == "Ana Cruz"
    assert sender["role"] == "Evaluator · Deactivated"


# ----------------------------------------------------------------- about


def test_a_notice_carries_the_candidate_and_job_it_is_about(
    client, db_session, hr_admin, applicant, make_job, make_application
):
    applicant.full_name = "Liza Ramos"
    job = make_job(["document_upload", "final_decision"], title="Librarian", department="Library")
    application = make_application(job)
    _seed(db_session, hr_admin, ["schedule"], actor=applicant, application=application)

    item = _inbox(client, HR)["items"][0]

    assert item["about"] == {
        "application_id": application.id,
        "requisition_id": job.id,
        "candidate_name": "Liza Ramos",
        "candidate_avatar_url": None,
        "job_title": "Librarian",
        "department": "Library",
    }
    assert item["available"] is True


def test_a_notice_whose_job_was_deleted_is_no_longer_available(
    client, db_session, hr_admin, applicant, make_job, make_application
):
    job = make_job(["document_upload", "final_decision"], title="Typo Role")
    application = make_application(job)
    notice = notify(
        db_session,
        user_id=hr_admin.id,
        actor_id=applicant.id,
        application_id=application.id,
        title="Reschedule request",
        message="…",
        link=f"/hr/applications/{application.id}",
    )
    application.status = ApplicationStatus.withdrawn
    db_session.flush()
    headers = auth_headers(client, HR)

    assert client.delete(f"/hr/requisitions/{job.id}", headers=headers).status_code == 204

    item = client.get(f"/notifications/{notice.id}", headers=headers).json()
    assert item["about"] is None
    assert item["available"] is False


def test_a_notice_without_a_link_is_available(client, db_session, hr_admin):
    _seed(db_session, hr_admin, ["system"])
    assert _inbox(client, HR)["items"][0]["available"] is True


# ---------------------------------------------------------------- search


def test_search_matches_title_message_and_sender_name(client, db_session, hr_admin, evaluator):
    evaluator.full_name = "Ramon Bautista"
    notify(db_session, user_id=hr_admin.id, actor_id=None, application_id=None, title="Offer declined", message="a")
    notify(db_session, user_id=hr_admin.id, actor_id=None, application_id=None, title="b", message="Room 204 moved")
    notify(db_session, user_id=hr_admin.id, actor_id=evaluator.id, application_id=None, title="c", message="d")
    notify(db_session, user_id=hr_admin.id, actor_id=None, application_id=None, title="nothing", message="here")
    db_session.flush()

    def titles(q):
        return {i["title"] for i in _inbox(client, HR, q=q)["items"]}

    assert titles("offer DECLINED") == {"Offer declined"}
    assert titles("room 204") == {"b"}
    assert titles("bautista") == {"c"}


def test_an_applicant_cannot_find_notices_by_a_staff_members_name(client, db_session, hr_admin, applicant):
    hr_admin.full_name = "Maria Santos"
    notify(db_session, user_id=applicant.id, actor_id=hr_admin.id, application_id=None, title="Exam booked", message="x")
    notify(db_session, user_id=applicant.id, actor_id=None, application_id=None, title="Job closed", message="y")
    db_session.flush()

    def titles(q):
        return {i["title"] for i in _inbox(client, APPLICANT, q=q)["items"]}

    # searching the name would tell them who acted
    assert titles("Maria") == set()
    # the name they are shown is what they can search by
    assert titles("hr office") == {"Exam booked"}
    assert titles("arkive") == {"Job closed"}


def test_search_treats_wildcards_as_text(client, db_session, hr_admin):
    notify(db_session, user_id=hr_admin.id, actor_id=None, application_id=None, title="Scored 100%", message="a")
    notify(db_session, user_id=hr_admin.id, actor_id=None, application_id=None, title="Scored 1000", message="b")
    db_session.flush()

    assert {i["title"] for i in _inbox(client, HR, q="100%")["items"]} == {"Scored 100%"}


# --------------------------------------------------------------- folders


def test_archiving_moves_a_notice_out_of_the_inbox_and_reads_it(client, db_session, hr_admin):
    notice = _seed(db_session, hr_admin, ["schedule"])[0]
    headers = auth_headers(client, HR)

    archived = client.post(f"/notifications/{notice.id}/archive", headers=headers).json()

    assert archived["archived_at"] is not None
    assert archived["read_at"] is not None
    assert notice.id not in {i["id"] for i in _inbox(client, HR)["items"]}
    assert notice.id in {i["id"] for i in _inbox(client, HR, folder="archived")["items"]}


def test_unarchiving_brings_it_back_to_the_inbox_as_read(client, db_session, hr_admin):
    notice = _seed(db_session, hr_admin, ["schedule"])[0]
    headers = auth_headers(client, HR)
    client.post(f"/notifications/{notice.id}/archive", headers=headers)

    back = client.post(f"/notifications/{notice.id}/unarchive", headers=headers).json()

    assert back["archived_at"] is None
    assert back["read_at"] is not None
    assert notice.id in {i["id"] for i in _inbox(client, HR)["items"]}
    assert notice.id not in {i["id"] for i in _inbox(client, HR, folder="archived")["items"]}


def test_mark_unread_and_read_again(client, db_session, hr_admin):
    notice = _seed(db_session, hr_admin, ["schedule"])[0]
    headers = auth_headers(client, HR)

    assert client.post(f"/notifications/{notice.id}/read", headers=headers).json()["read_at"] is not None
    assert client.post(f"/notifications/{notice.id}/unread", headers=headers).json()["read_at"] is None
    assert notice.id in {i["id"] for i in _inbox(client, HR, folder="unread")["items"]}


def test_the_unread_count_leaves_out_the_archive(client, db_session, hr_admin):
    made = _seed(db_session, hr_admin, ["schedule", "schedule"])
    made[1].archived_at = datetime.now(timezone.utc)  # archived while unread, as an old row could be
    db_session.flush()

    assert _inbox(client, HR)["unread_count"] == 1


def test_mark_all_read_reads_the_inbox(client, db_session, hr_admin):
    _seed(db_session, hr_admin, ["schedule", "decision"])
    headers = auth_headers(client, HR)

    assert client.post("/notifications/read-all", headers=headers).status_code == 204

    assert _inbox(client, HR)["unread_count"] == 0


def test_counts_cover_the_inbox_each_kind_and_the_archive(client, db_session, hr_admin):
    made = _seed(db_session, hr_admin, ["schedule", "schedule", "decision", "decision"])
    made[0].read_at = datetime.now(timezone.utc)
    made[3].archived_at = made[3].read_at = datetime.now(timezone.utc)
    db_session.flush()

    counts = client.get("/notifications/counts", headers=auth_headers(client, HR)).json()

    assert counts["inbox"] == {"total": 3, "unread": 2}
    assert counts["archived"] == {"total": 1, "unread": 0}
    assert counts["kinds"]["schedule"] == {"total": 2, "unread": 1}
    assert counts["kinds"]["decision"] == {"total": 1, "unread": 1}
    assert counts["kinds"]["application"] == {"total": 0, "unread": 0}


def test_someone_elses_notice_is_not_found(client, db_session, hr_admin, applicant):
    notice = _seed(db_session, hr_admin, ["schedule"])[0]
    headers = auth_headers(client, APPLICANT)

    assert client.get(f"/notifications/{notice.id}", headers=headers).status_code == 404
    for action in ("read", "unread", "archive", "unarchive"):
        assert client.post(f"/notifications/{notice.id}/{action}", headers=headers).status_code == 404


# ------------------------------------------------------- real call sites


def test_closing_a_job_tells_applicants_from_the_hr_office(
    client, db_session, hr_admin, applicant, make_job, make_application
):
    hr_admin.full_name = "Maria Santos"
    job = make_job(["document_upload", "final_decision"], title="Registrar")
    application = make_application(job)
    db_session.flush()

    client.patch(f"/hr/requisitions/{job.id}/status", json={"status": "closed"}, headers=auth_headers(client, HR))

    item = _inbox(client, APPLICANT)["items"][0]
    assert item["title"] == "Job closed"
    assert item["sender"]["name"] == OFFICE_SENDER
    assert item["about"]["application_id"] == application.id
    stored = db_session.get(Notification, item["id"])
    assert stored.actor_id == hr_admin.id  # the real person is kept, just not shown


# ------------------------------------------------------------- backfill


def _migration():
    path = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    [file] = path.glob("a7c3e9f15d28_*.py")
    spec = importlib.util.spec_from_file_location("notification_inbox_migration", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_old_notices_get_their_application_from_their_link(
    db_session, hr_admin, evaluator, applicant, make_job, make_application
):
    job = make_job(["document_upload", "interview_hr_director", "final_decision"])
    application = make_application(job)
    interview = db_session.scalar(
        select(StageInstance).where(
            StageInstance.application_id == application.id,
            StageInstance.stage_type == StageType.interview_hr_director,
        )
    )
    links = {
        "hr": (hr_admin, f"/hr/applications/{application.id}"),
        "applicant": (applicant, f"/applicant/applications/{application.id}?tab=exams"),
        "evaluator": (evaluator, f"/evaluator/interviews/{interview.id}"),
        "gone": (hr_admin, "/hr/applications/987654321"),
        "elsewhere": (hr_admin, f"/hr/requisitions/{job.id}"),
    }
    rows = {
        key: notify(db_session, user_id=u.id, actor_id=None, application_id=None, title="t", message=key, link=link)
        for key, (u, link) in links.items()
    }
    db_session.flush()

    for statement in _migration().APPLICATION_BACKFILL:
        db_session.execute(text(statement))
    for row in rows.values():
        db_session.refresh(row)

    assert rows["hr"].application_id == application.id
    assert rows["applicant"].application_id == application.id
    assert rows["evaluator"].application_id == application.id
    assert rows["gone"].application_id is None
    assert rows["elsewhere"].application_id is None


# ------------------------------------------------- long dashes (phase 3)

_D = "\u2014"

#: Each sentence ARKIVE has sent with a long dash (or " -- " standing in
#: for one), as saved, and as the code words it now.
_SAVED_AND_NOW = [
    (
        f"HR denied your reschedule request {_D} the original schedule stands.",
        "HR denied your reschedule request. The original schedule stands.",
    ),
    (
        f"HR approved your reschedule request {_D} now set for 2026-10-20 at 09:00.",
        "HR approved your reschedule request. It's now set for 2026-10-20 at 09:00.",
    ),
    (
        f"Congratulations {_D} you've been selected for Software Engineer I.",
        "Congratulations, you've been selected for Software Engineer I.",
    ),
    (
        f"You've been shortlisted for Instructor I {_D} your application is moving forward.",
        "You've been shortlisted for Instructor I. Your application is moving forward.",
    ),
    (
        f"You've been shortlisted for Instructor I {_D} please confirm to continue.",
        "You've been shortlisted for Instructor I. Please confirm to continue.",
    ),
    (
        f"Your Panel Interview has been scheduled for 2026-10-20 at 09:00 {_D} please confirm you can attend.",
        "Your Panel Interview has been scheduled for 2026-10-20 at 09:00. Please confirm you can attend.",
    ),
    (
        f"Pick a time for your Panel Interview {_D} 3 times to choose from.",
        "Pick a time for your Panel Interview: 3 times to choose from.",
    ),
    (
        f"Val Veep added their free times for Ben Cruz's Panel Interview {_D} ready to send to the applicant.",
        "Val Veep added their free times for Ben Cruz's Panel Interview, ready to send to the applicant.",
    ),
    (
        f"Ana Reyes did not respond within 7 days {_D} the offer has lapsed and the application is now "
        "withdrawn for Instructor I.",
        "Ana Reyes did not respond within 7 days, so the offer has lapsed and the application is now "
        "withdrawn for Instructor I.",
    ),
    (
        f"You're in a queue for Examination {_D} every currently scheduled slot is full, and 2 candidates "
        "are ahead of you. You're welcome to keep waiting, or withdraw this application from your "
        "Applications page and pursue other open positions.",
        "You're in a queue for Examination. Every currently scheduled slot is full, and 2 candidates "
        "are ahead of you. You're welcome to keep waiting, or withdraw this application from your "
        "Applications page and pursue other open positions.",
    ),
    (
        'Ana Reyes is not available for their Panel Interview on 2026-10-20 -- "I teach a class then"',
        'Ana Reyes is not available for their Panel Interview on 2026-10-20: "I teach a class then"',
    ),
    (
        'None of the times sent work for Ana Reyes\'s Panel Interview -- "Mornings are hard"',
        'None of the times sent work for Ana Reyes\'s Panel Interview: "Mornings are hard"',
    ),
    # what the workshop held on 17 Oct: the old names of the fixed rounds
    (
        f"You've been assigned to conduct Interview {_D} Dept. Head for Ben Blank-Slate (Software Engineer I).",
        "You've been assigned to conduct Department Head Interview for Ben Blank-Slate (Software Engineer I).",
    ),
    (
        f"Val Veep requested to reschedule Ben Blank-Slate's Interview {_D} Dept. Head to 2026-09-08 at 11:00.",
        "Val Veep requested to reschedule Ben Blank-Slate's Department Head Interview to 2026-09-08 at 11:00.",
    ),
]


def _rewording_migration():
    path = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    [file] = path.glob("b3d4f48f8df8_*.py")
    spec = importlib.util.spec_from_file_location("notice_rewording_migration", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(("saved", "now"), _SAVED_AND_NOW)
def test_a_saved_notice_takes_the_wording_the_code_writes_now(saved, now):
    assert _rewording_migration().reworded(saved) == now


def test_the_new_wording_is_the_one_the_code_sends():
    from app.api.hr.applications import _DECISION_NOTIFICATIONS

    saved = f"Congratulations {_D} you've been selected for Instructor I."
    assert _rewording_migration().reworded(saved) == _DECISION_NOTIFICATIONS["hired"][1].format(job="Instructor I")


def test_what_was_filled_in_is_carried_across_exactly():
    """A job title HR typed, or an applicant's own note, keeps every
    character, a long dash of its own included."""
    migration = _rewording_migration()
    assert migration.reworded(f"Congratulations {_D} you've been selected for Instructor {_D} CCMS.") == (
        f"Congratulations, you've been selected for Instructor {_D} CCMS."
    )
    note = f'Class {_D} sorry -- "really"'
    assert migration.reworded(f'Ana Reyes is not available for their Panel Interview on 2026-10-20 -- "{note}"') == (
        f'Ana Reyes is not available for their Panel Interview on 2026-10-20: "{note}"'
    )


def test_a_message_arkive_did_not_word_that_way_is_left_alone():
    migration = _rewording_migration()
    for message in (
        f"Something else {_D} entirely.",
        "HR denied your reschedule request. The original schedule stands.",
        "Your Panel Interview is booked for Tue, 20 Oct 2026, at Room 204.",
    ):
        assert migration.reworded(message) == message


def test_downgrade_puts_the_old_sentences_back_and_keeps_the_new_round_names():
    migration = _rewording_migration()
    for saved, now in _SAVED_AND_NOW:
        renamed = any(old in saved for old in migration.RENAMED_STAGES)
        # a renamed round stays renamed: HR may have typed "VP Interview" itself
        assert migration.restored(now) == (now if renamed else saved)


def test_the_migration_rewrites_saved_notices_and_their_titles(db_session, hr_admin):
    migration = _rewording_migration()
    denied, unrelated = (
        notify(db_session, user_id=hr_admin.id, actor_id=None, application_id=None, title=title, message=message)
        for title, message in (
            ("Reschedule denied", _SAVED_AND_NOW[0][0]),
            (f"Your Interview {_D} VP is booked", "Nothing to change here."),
        )
    )
    db_session.flush()

    migration.rewrite_saved_notices(db_session.connection(), migration.reworded, migration.renamed_title)
    db_session.refresh(denied)
    db_session.refresh(unrelated)

    assert denied.message == _SAVED_AND_NOW[0][1]
    assert denied.title == "Reschedule denied"
    assert unrelated.message == "Nothing to change here."
    assert unrelated.title == "Your VP Interview is booked"
