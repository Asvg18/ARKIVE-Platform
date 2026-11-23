"""Seed one candidate who has been all the way through the pipeline, so
the Candidate Profile's Synthesis tab has a *complete* WSM to show.

Why this exists: every application in the dev database is partway
through, or was hired having skipped most of it. None has all four WSM
criteria, so final_synthesis_score is null everywhere and the synthesis
breakdown has never been seen fully populated.

Deliberately NOT a fixture-injection script. It drives the real routers
through FastAPI's TestClient against the real dev database, so every
agent fires for real -- resume parsed by GPT-4o-mini, a genuine hybrid
RAG+BM25 match, each scorecard triggering the real Interview Synthesis
Agent. The AgentRun trail that comes out is authentic, which is the
whole point -- a demo that fakes its own audit log proves nothing.

Costs a handful of OpenAI calls (~8, all gpt-4o-mini) and takes about a
minute. Safe to re-run: skips entirely if the requisition already
exists.

Usage (from backend/):
    venv/bin/python -m scripts.seed_golden_path
"""

import json
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infra.db import SessionLocal
from app.domain.scorecard import SCORECARD_ITEM_CODES
from app.infra.security import hash_password
from app.main import app
from app.models.enums import UserRole
from app.models.job_requisition import JobRequisition
from app.models.user import User
from scripts._mini_pdf import text_pdf

JOB_TITLE = "IT Systems Administrator"
HR_EMAIL = "hr@arkive.demo"
DEMO_PASSWORD = "demo-password-123"

# written to genuinely match the primary candidate's resume below --
# the match score has to clear _FLAG_THRESHOLD (60.0) or the DFA freezes
# at skill_matching and the candidate never reaches the interview
# rounds, defeating the whole point of this script
JOB = dict(
    title=JOB_TITLE,
    department="Computing",
    description=(
        "Maintains and secures the campus server, network, and identity "
        "infrastructure at MSEUF Lucena, supporting academic and "
        "administrative systems across all departments."
    ),
    qualifications=(
        "Bachelor's degree in Computer Science, Information Technology, or a "
        "related field. At least three years of hands-on systems "
        "administration experience in an enterprise or campus environment."
    ),
    requirements=(
        "Linux server administration (Ubuntu, CentOS). Windows Server and "
        "Active Directory. Virtualization with VMware or Proxmox. Network "
        "configuration including VLANs, firewalls, and DNS. Backup and "
        "disaster recovery planning. Shell scripting and infrastructure "
        "automation. Monitoring with Zabbix, Nagios, or equivalent. "
        "Experience with Docker containers is an advantage."
    ),
)

QUESTIONS = [
    {"id": "q1", "text": "Describe a server outage you resolved end to end.", "required": True},
    {"id": "q2", "text": "How do you approach patching production systems?", "required": True},
    {"id": "q3", "text": "What monitoring stack have you run, and why?", "required": True},
]

# one strong candidate (the golden path, taken to hired) and two weaker
# ones -- the other two exist so the exam percentile is a real rank
# instead of a meaningless 50th against a field of one
CANDIDATES = [
    dict(
        email="marco.villanueva@arkive.demo",
        full_name="Marco Villanueva",
        exam_score=88.0,
        golden=True,
        resume=dict(
            full_name="Marco Villanueva",
            email="marco.villanueva@arkive.demo",
            phone="+63 917 555 0142",
            location="Lucena City, Quezon",
            linkedin_url="",
            portfolio_url="",
            professional_summary=(
                "Systems administrator with six years running campus server and "
                "network infrastructure. Specialises in Linux server hardening, "
                "virtualization, and monitoring, with a track record of cutting "
                "unplanned downtime through proactive alerting and tested backups."
            ),
            education=[
                dict(
                    school="Manuel S. Enverga University Foundation",
                    degree="Bachelor of Science",
                    field_of_study="Information Technology",
                    start_date="2014",
                    end_date="2018",
                    honors="Cum Laude",
                )
            ],
            experience=[
                dict(
                    company="Quezon Provincial IT Office",
                    title="Systems Administrator",
                    start_date="Jun 2021",
                    end_date="Present",
                    description=(
                        "Administer 40+ Ubuntu and CentOS servers and a Proxmox "
                        "virtualization cluster. Run Active Directory for 1,200 "
                        "staff accounts. Designed VLAN segmentation and firewall "
                        "rules across three campus buildings. Built a Zabbix "
                        "monitoring stack and an automated, regularly restore-"
                        "tested backup routine."
                    ),
                ),
                dict(
                    company="Southern Luzon Data Services",
                    title="Junior Network Engineer",
                    start_date="Aug 2018",
                    end_date="May 2021",
                    description=(
                        "Maintained DNS and DHCP infrastructure, configured "
                        "switches and firewalls, and wrote Bash and Python "
                        "automation for provisioning and log rotation."
                    ),
                ),
            ],
            skills=[
                "Linux server administration", "Ubuntu", "CentOS", "Windows Server",
                "Active Directory", "Proxmox", "VMware", "VLAN configuration",
                "Firewall administration", "DNS", "Backup and disaster recovery",
                "Bash scripting", "Python", "Zabbix", "Nagios", "Docker",
            ],
            certifications=["CompTIA Server+", "Cisco CCNA", "Red Hat RHCSA"],
        ),
    ),
    dict(
        email="celine.roxas@arkive.demo",
        full_name="Celine Roxas",
        exam_score=71.0,
        golden=False,
        resume=dict(
            full_name="Celine Roxas", email="celine.roxas@arkive.demo", phone="",
            location="Lucena City, Quezon", linkedin_url="", portfolio_url="",
            professional_summary="IT support specialist moving into systems administration.",
            education=[dict(school="MSEUF", degree="Bachelor of Science",
                            field_of_study="Computer Science", start_date="2017",
                            end_date="2021", honors="")],
            experience=[dict(company="Lucena City Hall", title="IT Support Technician",
                             start_date="2021", end_date="Present",
                             description="Desktop support, basic Windows Server and printer administration, user account provisioning.")],
            skills=["Windows Server", "Active Directory", "Desktop support", "DNS", "Bash scripting"],
            certifications=["CompTIA A+"],
        ),
    ),
    dict(
        email="dante.ilagan@arkive.demo",
        full_name="Dante Ilagan",
        exam_score=64.0,
        golden=False,
        resume=dict(
            full_name="Dante Ilagan", email="dante.ilagan@arkive.demo", phone="",
            location="Tayabas, Quezon", linkedin_url="", portfolio_url="",
            professional_summary="Network technician with campus infrastructure exposure.",
            education=[dict(school="MSEUF", degree="Bachelor of Science",
                            field_of_study="Information Technology", start_date="2016",
                            end_date="2020", honors="")],
            experience=[dict(company="Tayabas Networks", title="Network Technician",
                             start_date="2020", end_date="Present",
                             description="Switch and router configuration, VLAN setup, cable plant maintenance, Linux basics.")],
            skills=["VLAN configuration", "Linux server administration", "DNS", "Firewall administration"],
            certifications=["Cisco CCNA"],
        ),
    ),
]

# remarks actually cover the HRD-F-APIEF rubric's four categories,
# because Interview Synthesis grades exactly that -- how well an
# evaluator's documentation substantiates their ratings. a first pass at
# this script used one generic paragraph for all three rounds and scored
# 27.5/100 -- the agent was right. each round is now written from its
# own evaluator's actual vantage point.
EVALUATORS = [
    ("golden.hr@arkive.demo", "Rosalie Mendoza", "interview_round_1", 5, (
        "Personal background: presented himself clearly, gave a complete account of his "
        "residence in Lucena and his six years in provincial IT without prompting. "
        "Educational qualifications: BS Information Technology from MSEUF, Cum Laude, and "
        "he connected specific coursework in networking to what this post needs rather "
        "than just naming the degree. Work background: walked through the Quezon "
        "Provincial IT Office role in detail — 40+ servers, the Proxmox cluster, Active "
        "Directory for 1,200 accounts. Reason for leaving is growth into a campus-scale "
        "environment, which is consistent and non-defensive; offered two named referees, "
        "his current IT head and a former network lead. Job expectations: knows MSEUF as "
        "his alma mater and spoke concretely about wanting the infrastructure to be "
        "dependable for students. Salary expectation stated plainly and within band.")),
    ("golden.dept@arkive.demo", "Armando Bautista", "interview_round_2", 4, (
        "Assessed primarily on technical depth for the department. Work background is the "
        "strongest area: he described the RAID controller failure end to end — the Zabbix "
        "alert that paged him, failing over to the standby node, rebuilding from a "
        "verified backup, and the monthly restore drill he introduced afterwards so the "
        "team was never trusting an untested backup. That is a concrete, checkable "
        "example, not a general principle. Patching discipline was equally specific: "
        "staged rollout through a mirrored Proxmox test VM, documented snapshot rollback, "
        "and a rule never to patch identity infrastructure and file services in the same "
        "window. Educational qualifications are appropriate but he leans on experience "
        "over formal study, which is why I rated that category slightly lower. Job "
        "expectations: clear on scope, though his answer on career development was "
        "thinner than his technical answers — he has not thought far past this role.")),
    ("golden.vp@arkive.demo", "Teresita Alvarez", "interview_round_3", 5, (
        "Executive view. Personal background and bearing are appropriate for a role that "
        "deals with every department; he was composed and direct. Educational "
        "qualifications meet the vacancy. Work background: independently corroborated the "
        "scale he claims — sole administrator for a provincial office, which is the same "
        "shape of responsibility this post carries, and he was candid that being the only "
        "administrator is why he built monitoring and automation rather than relying on "
        "heroics. Job expectations: his reason for applying to MSEUF is specific and "
        "credible rather than generic loyalty to his alma mater, he understands that "
        "campus infrastructure serves teaching first, and his salary expectation is "
        "realistic. On leadership potential he described mentoring a junior technician "
        "and writing runbooks so the office was not dependent on him alone, which is the "
        "answer I most wanted to hear for a single-administrator post.")),
]

ANSWERS = [
    {"question_id": "q1", "value": (
        "A RAID controller failed on our primary file server at 2am. Zabbix "
        "paged me, I failed services over to the standby node, replaced the "
        "controller, rebuilt the array from the previous night's verified "
        "backup, and had users back on the primary by 7am. I then added a "
        "monthly restore drill so we were never trusting an untested backup.")},
    {"question_id": "q2", "value": (
        "Staged. Patches go to a Proxmox test VM that mirrors production, then "
        "to low-traffic servers during a declared window, then to the rest. "
        "Every window has a documented rollback via snapshot, and I never patch "
        "identity infrastructure and file services in the same window.")},
    {"question_id": "q3", "value": (
        "Zabbix, mostly. I chose it over Nagios because its templating and "
        "auto-discovery made adding new hosts cheap, which matters when you "
        "are the only administrator. I alert on symptoms users would notice, "
        "not on raw CPU, to keep the on-call signal-to-noise usable.")},
]


def _resume_to_lines(r: dict) -> list[str]:
    """Renders the structured resume as plain text for the uploaded PDF.

    The PDF is generated *from* this same dict, not an unrelated file, so
    the résumé HR opens says what the record says. The match score reads
    the fields (skill_matching._resume_scoring_text); the PDF text is only
    its fallback when every field is blank."""
    lines = [r["full_name"].upper()]
    contact = " | ".join(x for x in (r.get("email"), r.get("phone"), r.get("location")) if x)
    if contact:
        lines.append(contact)
    lines += ["", "PROFESSIONAL SUMMARY", r["professional_summary"], "", "SKILLS",
              ", ".join(r["skills"]), ""]
    if r.get("certifications"):
        lines += ["CERTIFICATIONS", ", ".join(r["certifications"]), ""]
    lines.append("EXPERIENCE")
    for job in r["experience"]:
        lines.append(f"{job['title']} — {job['company']} ({job['start_date']} – {job['end_date']})")
        # Wrapped at ~95 characters: the mini PDF writer does no wrapping
        # of its own, so an over-long line would run off the page edge and
        # its tail would be lost to text extraction.
        words, current = job["description"].split(), ""
        for word in words:
            if len(current) + len(word) + 1 > 95:
                lines.append(f"  {current}")
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            lines.append(f"  {current}")
        lines.append("")
    lines.append("EDUCATION")
    for school in r["education"]:
        honors = f" ({school['honors']})" if school.get("honors") else ""
        lines.append(
            f"{school['degree']} in {school['field_of_study']} — {school['school']} "
            f"({school['start_date']} – {school['end_date']}){honors}"
        )
    return lines


def _rate(base: int) -> dict[str, int | None]:
    return {code: base for code in SCORECARD_ITEM_CODES}


def _login(client: TestClient, email: str) -> dict[str, str]:
    resp = client.post("/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    resp.raise_for_status()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _ensure_user(db, email: str, full_name: str, role: UserRole) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            full_name=full_name,
            hashed_password=hash_password(DEMO_PASSWORD),
            role=role,
            auth_provider="local",
            provisioning_source="seed",
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"    created {role.value}: {email}")
    return user


def _advance(client, app_id: int, target: str, hr, workflow: list[str]) -> None:
    """Walk the DFA forward one legal step at a time until the application
    sits on `target`, and no-op if it is already there or past it.

    Necessary because some stages advance themselves: submitting
    pre-screening completes skill_matching and moves the application to
    the next stage on its own, so a blind transition to `examination`
    afterwards is rejected as an illegal same-stage move."""
    current = client.get(f"/hr/applications/{app_id}/profile", headers=hr).json()["current_stage"]
    if current is not None and workflow.index(current) >= workflow.index(target):
        return
    start = 0 if current is None else workflow.index(current) + 1
    for stage in workflow[start : workflow.index(target) + 1]:
        _ok(client.post(f"/applications/{app_id}/transition",
                        json={"target_stage": stage}, headers=hr), f"advance to {stage}")


def _ok(resp, what: str):
    if resp.status_code >= 400:
        raise SystemExit(f"FAILED at {what}: {resp.status_code} {resp.text}")
    return resp


def seed() -> None:
    db = SessionLocal()
    try:
        if db.scalar(select(JobRequisition).where(JobRequisition.title == JOB_TITLE)):
            print(f"skip (already exists): '{JOB_TITLE}' — nothing to do.")
            return
        if db.scalar(select(User).where(User.email == HR_EMAIL)) is None:
            raise SystemExit("Demo users missing — run `python -m scripts.seed_demo_users` first.")

        print("1. accounts")
        for email, name, *_ in EVALUATORS:
            _ensure_user(db, email, name, UserRole.evaluator)
        evaluator_ids = {
            email: db.scalar(select(User).where(User.email == email)).id
            for email, *_ in EVALUATORS
        }
    finally:
        db.close()

    client = TestClient(app)
    hr = _login(client, HR_EMAIL)

    print("2. requisition (standard preset -> interview_round_1/2/3)")
    job = _ok(
        client.post(
            "/hr/requisitions",
            json={**JOB, "workflow_preset": "standard", "publish": True,
                  # publishing now needs the questions up front (panel
                  # revisions, 15 Oct 2026)
                  "pre_screening_questions": QUESTIONS,
                  "application_deadline": str(date.today() + timedelta(days=45))},
            headers=hr,
        ),
        "create requisition",
    ).json()
    job_id = job["id"]
    workflow = job["workflow_definition"]
    print(f"    id={job_id}  stages={len(job['workflow_definition'])}")

    _ok(
        client.patch(f"/hr/requisitions/{job_id}/pre-screening-questions",
                     json={"questions": QUESTIONS}, headers=hr),
        "set questions",
    )
    slot = _ok(
        client.post(f"/hr/requisitions/{job_id}/exam-slots",
                    json={"stage_type": "examination",
                          "date": str(date.today() + timedelta(days=10)),
                          "time": "09:00",
                          "location": "MSEUF Lucena Campus, Computer Laboratory 2",
                          "capacity": 10},
                    headers=hr),
        "add exam slot",
    ).json()

    for email, *_ in EVALUATORS:
        _ok(client.post(f"/hr/requisitions/{job_id}/evaluators",
                        json={"evaluator_id": evaluator_ids[email]}, headers=hr),
            f"add evaluator {email}")
    print(f"    questions={len(QUESTIONS)}  exam slot={slot['id']}  evaluators={len(EVALUATORS)}")

    golden_app_id = None

    for spec in CANDIDATES:
        print(f"3. candidate: {spec['full_name']}")
        signup = client.post("/auth/signup", json={
            "email": spec["email"], "password": DEMO_PASSWORD, "full_name": spec["full_name"]})
        if signup.status_code >= 400:
            applicant = _login(client, spec["email"])
        else:
            applicant = {"Authorization": f"Bearer {signup.json()['access_token']}"}

        app_id = _ok(
            client.post("/applications", json={"requisition_id": job_id}, headers=applicant),
            "create application",
        ).json()["id"]

        pdf_bytes = text_pdf(_resume_to_lines(spec["resume"]))
        _ok(client.post(f"/applicant/applications/{app_id}/document-upload",
                            headers=applicant,
                            files={"resume_file": (
                                f"{spec['full_name'].replace(' ', '_')}_Resume.pdf",
                                pdf_bytes, "application/pdf")},
                            data={"resume_data": json.dumps(spec["resume"]),
                                  "letter_of_intent": (
                                      f"I am applying for the {JOB_TITLE} post because "
                                      "keeping campus infrastructure dependable is the work "
                                      "I find most worthwhile.")}),
                "document upload")
        print("    document upload done (Document Parsing Agent logged)")

        _ok(client.post(f"/applicant/applications/{app_id}/pre-screening",
                        json={"answers": ANSWERS,
                              "exam_availability": [
                                  {"stage_type": "examination", "exam_slot_ids": [slot["id"]]}]},
                        headers=applicant),
            "pre-screening")

        profile = client.get(f"/hr/applications/{app_id}/profile", headers=hr).json()
        print(f"    match={profile['match_score']}  status={profile['status']}")
        if profile["status"] == "flagged":
            raise SystemExit(
                f"{spec['full_name']} was flagged (match {profile['match_score']} < 60). "
                "The DFA is frozen at skill_matching, so this candidate can't reach the "
                "interview rounds. Strengthen the resume/JD wording and re-run."
            )

        booking = profile["examinations"]["examination"]["pending_booking"]
        _ok(client.post(f"/hr/applications/{app_id}/exam-bookings/{booking['id']}/resolve",
                        json={"decision": "approve"}, headers=hr),
            "approve exam booking")

        _advance(client, app_id, "examination", hr, workflow)
        _ok(client.patch(f"/hr/applications/{app_id}/examination-result",
                         json={"stage_type": "examination", "score": spec["exam_score"]},
                         headers=hr),
            "record exam score")
        print(f"    exam recorded: {spec['exam_score']}")

        if spec["golden"]:
            golden_app_id = app_id

    print("4. interview chain for the golden candidate")
    for email, name, stage, rating, remarks in EVALUATORS:
        # The evaluator's own call, kept consistent with the ratings this
        # seed sets. Derived rather than hardcoded per round so the two
        # cannot drift if a rating here is ever changed.
        recommendation = ("highly_recommended" if rating >= 5
                          else "recommended" if rating >= 4
                          else "not_recommended")
        _advance(client, golden_app_id, stage, hr, workflow)
        _ok(client.post(f"/hr/applications/{golden_app_id}/interview-assignment",
                        json={"stage_type": stage, "evaluator_id": evaluator_ids[email]},
                        headers=hr),
            f"assign {stage}")

        ev = _login(client, email)
        queue = _ok(client.get("/evaluator/interviews", headers=ev), "evaluator queue").json()
        # InterviewListItem carries stage_label, not stage_type -- each
        # evaluator here holds exactly one assignment for this candidate,
        # so the unevaluated row is unambiguous without matching stage
        sid = next(i["stage_instance_id"] for i in queue
                   if i["application_id"] == golden_app_id and not i["already_evaluated"])
        _ok(client.post(f"/evaluator/interviews/{sid}/evaluate",
                        json={"item_ratings": _rate(rating), "remarks": remarks,
                              "recommendation": recommendation},
                        headers=ev),
            f"submit scorecard {stage}")
        print(f"    {stage}: {name} rated {rating}, {recommendation} "
              f"(Scorecard + Synthesis agents fired)")

    print("5. close out")
    _advance(client, golden_app_id, "final_decision", hr, workflow)
    # no acknowledged_incomplete -- this record is genuinely complete,
    # so the hire gate lets it straight through. worth demonstrating:
    # this is the only application in the database that clears the gate
    # unassisted.
    _ok(client.patch(f"/hr/applications/{golden_app_id}/status",
                     json={"status": "hired",
                           "reason": "Unanimous recommendation across all three "
                                     "interview rounds; strongest exam percentile "
                                     "in the field."},
                     headers=hr), "hire")

    final = client.get(f"/hr/applications/{golden_app_id}/profile", headers=hr).json()
    s = final["synthesis"]
    print(f"\nGolden candidate: application {golden_app_id} — {final['applicant_name']}")
    print(f"  final_synthesis_score = {s['final_synthesis_score']}  tier={s['overall_tier']}")
    print(f"  criteria {s['criteria_available']}/{s['criteria_applicable']} available")
    for c in s["criteria"]:
        print(f"    {c['label']:<28} w={c['weight']:<6} {str(c['display_value']):<18} "
              f"contributes {c['contribution']}")
    print(f"  agent runs logged: {len(s['agent_trail'])}")
    d = final["decision"]
    print(f"  decision: {d['status']} by {d['decided_by_name']} at {d['decided_at_stage_label']}"
          f" (acknowledged_incomplete={d['acknowledged_incomplete']})")
    print(f"\n  View at /hr/applications/{golden_app_id}")


if __name__ == "__main__":
    seed()
