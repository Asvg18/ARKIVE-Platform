"""What every AI step is sent, locked to the character.

Cleaning ARKIVE's own text (taking the long dashes out) must not change
how the AI reads, matches, scores or analyses anything, above all resume
skill matching. The instructions themselves contain long dashes, and
they stay exactly as they are.

Each AI step is called here with fixed sample input, and what it would
have sent to OpenAI is caught before it leaves: the model and its
settings, the instructions, the message built from the input, the answer
format, and for skill matching every text it embeds. That is compared,
character for character, with ai_instruction_lock.json, recorded from
the code before the text cleanup changed anything.

If this fails, something now reaches the AI differently. When that is
deliberate, record the new text with

    ARKIVE_RECORD_AI_LOCK=1 venv/bin/python -m pytest tests/test_ai_instruction_lock.py

and commit the lock file with it, so the difference shows in review.

test_no_long_dashes.py reads the same file: text the AI is sent is the one
place a long dash may stay.
"""

from __future__ import annotations

import difflib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.domain.insights import aspect_scores, evaluator_agreement
from app.domain.scorecard import SCORECARD_CATEGORIES, compute_score, compute_tier
from app.infra.config import settings
from app.schemas.applicant import PreScreeningAnswer
from app.schemas.decision_brief import DecisionBriefResult
from app.schemas.interview_analysis import InterviewAnalysisResult
from app.schemas.interview_synthesis import InterviewSynthesisResult
from app.schemas.pipeline import JDExtractionCandidate, JDImageReading
from app.schemas.resume import ResumeExtractionResult, ResumeImageReading
from app.schemas.skill_match import (
    AuditVerdict,
    QueryExpansion,
    RecheckResult,
    RequirementCheck,
    RequirementProbes,
    SkillMatchAnalysis,
    VerdictAuditResult,
    VerdictObjection,
)
from app.services import (
    decision_brief,
    interview_analysis,
    interview_synthesis,
    jd_extraction,
    jd_text,
    resume_extraction,
    resume_text,
    skill_matching,
)
from app.services.agents import rag_catalog

LOCK_FILE = Path(__file__).with_name("ai_instruction_lock.json")
APP_DIR = Path(__file__).resolve().parents[1] / "app"

_HOW_TO_RECORD = (
    "If the change is deliberate, record it with "
    "ARKIVE_RECORD_AI_LOCK=1 venv/bin/python -m pytest tests/test_ai_instruction_lock.py "
    "and commit ai_instruction_lock.json with it."
)

#: Every file that talks to a model. A new one has to be added to the
#: capture below before it ships, or this lock would quietly not cover it.
_FILES_THAT_CALL_THE_AI = {
    "services/agents/rag_catalog.py",
    "services/decision_brief.py",
    "services/interview_analysis.py",
    "services/interview_synthesis.py",
    "services/jd_extraction.py",
    "services/jd_text.py",
    "services/resume_extraction.py",
    "services/resume_text.py",
    "services/skill_matching/__init__.py",
    "services/skill_matching/retrieval.py",
}
_AI_CALL_MARKERS = ("with_structured_output(", "ChatOpenAI(", "OpenAIEmbeddings(", ".embed_query(", ".embed_documents(")


# ---------------------------------------------------------------- catching


def _vector(text: str) -> list[float]:
    """A stand-in embedding: fixed for a given text, so retrieval, and so
    what reaches each prompt, comes out the same on every run."""
    return [1.0 + sum(map(ord, text)) % 13, 1.0 + len(text) % 7, 1.0 + text.count(" ") % 5]


class _Caught:
    """The requests the AI steps made, in order. Structured-output
    requests are answered from `answers`: each schema's replies are used
    in turn, and the last one repeats."""

    def __init__(self, answers: dict[type, list]):
        self.requests: list[dict] = []
        self._answers = {schema: list(replies) for schema, replies in answers.items()}

    def answer(self, schema: type):
        replies = self._answers[schema]
        return replies.pop(0) if len(replies) > 1 else replies[0]


def _catch(monkeypatch: pytest.MonkeyPatch, answers: dict[type, list] | None = None) -> _Caught:
    caught = _Caught(answers or {})

    def with_structured_output(self, schema, **options):
        def invoke(messages, *args, **kwargs):
            caught.requests.append(
                {
                    "model": self.model_name,
                    "temperature": self.temperature,
                    "answer_format": schema.__name__,
                    "options": options,
                    "messages": messages,
                }
            )
            return caught.answer(schema)

        return SimpleNamespace(invoke=invoke)

    def invoke(self, prompt, *args, **kwargs):
        caught.requests.append({"model": self.model_name, "temperature": self.temperature, "prompt": prompt})
        return SimpleNamespace(content="OK")

    def embed_documents(self, texts, *args, **kwargs):
        caught.requests.append({"embedding_model": self.model, "embed_documents": list(texts)})
        return [_vector(text) for text in texts]

    def embed_query(self, text, *args, **kwargs):
        caught.requests.append({"embedding_model": self.model, "embed_query": text})
        return _vector(text)

    monkeypatch.setattr(ChatOpenAI, "with_structured_output", with_structured_output)
    monkeypatch.setattr(ChatOpenAI, "invoke", invoke)
    monkeypatch.setattr(OpenAIEmbeddings, "embed_documents", embed_documents)
    monkeypatch.setattr(OpenAIEmbeddings, "embed_query", embed_query)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    # skill matching keeps one client of each for the whole process; built
    # fresh here, so what they are built with is caught too
    monkeypatch.setattr(skill_matching, "_llm_client", None)
    monkeypatch.setattr(skill_matching, "_embeddings_client", None)
    return caught


# ---------------------------------------------------------------- sample input

_JOB = SimpleNamespace(
    id=7,
    title="Instructor I",
    department="College of Computing and Multimedia Studies",
    description="Teaches undergraduate programming courses and advises student research projects.",
    qualifications=(
        "Master's degree in Computer Science, Information Technology, or a related field\n"
        "At least two years of teaching experience"
    ),
    requirements=(
        "- Proficiency in Python and Java\n"
        "* Strong communication skills\n"
        "3. Experience supervising capstone projects"
    ),
    embedding=None,
)
_REQUIREMENTS = [
    "Master's degree in Computer Science, Information Technology, or a related field",
    "At least two years of teaching experience",
    "Proficiency in Python and Java",
    "Strong communication skills",
    "Experience supervising capstone projects",
]

_RESUME = SimpleNamespace(
    application_id=42,
    full_name="Maria Santos",
    email="maria.santos@example.com",
    phone="0917 555 0101",
    location="Lucena City",
    linkedin_url="",
    portfolio_url="",
    professional_summary="Computer science educator with six years of classroom and industry experience.",
    experience=[
        {
            "title": "Part-time Lecturer",
            "company": "Southern Luzon State University",
            "start_date": "2021",
            "end_date": "Present",
            "description": "Taught Python and Java programming to second-year students; supervised twelve capstone projects.",
        },
        {
            "title": "Software Developer",
            "company": "Quezon Digital Works",
            "start_date": "2018",
            "end_date": "2021",
            "description": "Built web applications in Java and presented progress reports to clients every week.",
        },
    ],
    education=[
        {
            "school": "Manuel S. Enverga University Foundation",
            "degree": "Master of Science",
            "field_of_study": "Computer Science",
            "start_date": "2019",
            "end_date": "2021",
            "honors": "",
        },
        {
            "school": "Lucena Polytechnic College",
            "degree": "Bachelor of Science",
            "field_of_study": "Information Technology",
            "start_date": "2012",
            "end_date": "2016",
            "honors": "Cum Laude",
        },
    ],
    skills=["Python", "Java", "Django", "Git", "Public speaking"],
    certifications=["Oracle Certified Professional, Java SE 11 Developer"],
    additional_sections=[
        {"title": "Awards", "content": "Best Capstone Adviser, 2023\nOutstanding Faculty Researcher, 2022"}
    ],
    raw_extracted_text="Maria Santos, the PDF's own text, which the reviewed form above stands in for.",
    embedding=None,
)

_CHECKS = [
    RequirementCheck(requirement=_REQUIREMENTS[0], verdict="met", evidence_quote="Master of Science in Computer Science"),
    RequirementCheck(requirement=_REQUIREMENTS[1], verdict="met", evidence_quote="Taught Python and Java programming"),
    RequirementCheck(requirement=_REQUIREMENTS[2], verdict="met", evidence_quote="Python, Java"),
    RequirementCheck(requirement=_REQUIREMENTS[3], verdict="not_met", evidence_quote=""),
    RequirementCheck(requirement=_REQUIREMENTS[4], verdict="partial", evidence_quote="supervised twelve capstone projects"),
]


def _skill_matching_answers() -> dict[type, list]:
    """A first draft the Critic rejects, a rewrite it accepts, and one
    verdict the Verdict Auditor disputes, so every prompt of the
    pipeline is sent at least once, retries included."""
    return {
        SkillMatchAnalysis: [
            SkillMatchAnalysis(
                strengths=["Taught Python and Java at university level.", "Supervised twelve capstone projects."],
                gaps=["No evidence of communication skills."],
                summary="A strong fit on teaching and programming; communication is not evidenced.",
                requirement_checks=_CHECKS,
            ),
            SkillMatchAnalysis(
                strengths=["Taught Python and Java at university level.", "Supervised twelve capstone projects."],
                gaps=[],
                summary="A strong fit on teaching and programming.",
                requirement_checks=_CHECKS,
            ),
        ],
        AuditVerdict: [
            AuditVerdict(
                is_grounded=False,
                unsupported_claims=["No evidence of communication skills."],
                needs_more_context=[_REQUIREMENTS[3]],
                note="One gap is contradicted by the evidence.",
            ),
            AuditVerdict(is_grounded=True, note="Every claim traces to the evidence."),
        ],
        VerdictAuditResult: [
            VerdictAuditResult(
                objections=[
                    VerdictObjection(
                        requirement=_REQUIREMENTS[3],
                        objection="The résumé says she presented progress reports to clients every week.",
                    )
                ]
            )
        ],
        RecheckResult: [
            RecheckResult(
                requirement_checks=[
                    RequirementCheck(
                        requirement=_REQUIREMENTS[3],
                        verdict="partial",
                        evidence_quote="presented progress reports to clients every week",
                    )
                ]
            )
        ],
        QueryExpansion: [
            QueryExpansion(
                expansions=[
                    RequirementProbes(requirement=requirement, probes=[f"{requirement} probe {n}" for n in (1, 2, 3)])
                    for requirement in _REQUIREMENTS
                ]
            )
        ],
    }


def _round(label: str, evaluator: str, by_category: dict[str, int | None], recommendation: str) -> dict:
    """One interview round as build_candidate_profile hands it to the
    insights: every item of a category rated the same."""
    ratings = {
        item.code: by_category[category.code] for category in SCORECARD_CATEGORIES for item in category.items
    }
    score = compute_score(ratings)
    return {
        "label": label,
        "assigned_evaluator_name": evaluator,
        "item_ratings": ratings,
        "computed_score": score,
        "tier": compute_tier(score),
        "recommendation": recommendation,
    }


#: One set of facts per skill-match band, with the fact sentences each
#: kind of interview record produces.
_BRIEF_CASES = {
    "split panel, match just over the line": dict(
        match_score=65.0,
        match_gaps=["A master's degree in Computer Science.", "Three years of university teaching"],
        interview_ratings={
            "interview_round_1": _round("HR Interview", "Ana Reyes", {"A": 4, "B": 4, "C": 3, "D": 4}, "recommended"),
            "interview_round_2": _round("Panel Interview", "Ben Cruz", {"A": 4, "B": 5, "C": 4, "D": 4}, "highly_recommended"),
            "interview_round_3": _round("Dean's Interview", "Carla Diaz", {"A": 2, "B": 2, "C": 2, "D": 3}, "not_recommended"),
        },
        exam_score=82.0,
        exam_rank=2,
        exam_cohort=5,
    ),
    "even ratings, strong match": dict(
        match_score=85.0,
        match_gaps=[],
        interview_ratings={
            "interview_round_1": _round("HR Interview", "Ana Reyes", {"A": 4, "B": 4, "C": 4, "D": 4}, "recommended"),
            "interview_round_2": _round("Panel Interview", "Ben Cruz", {"A": 4, "B": 4, "C": 4, "D": 4}, "recommended"),
        },
        exam_score=90.0,
        exam_rank=1,
        exam_cohort=1,
    ),
    "below the threshold, no interviews yet": dict(
        match_score=45.0,
        match_gaps=["Proficiency in Python and Java."],
        interview_ratings={},
        exam_score=None,
        exam_rank=None,
        exam_cohort=None,
    ),
    "solid match, one round of two in": dict(
        match_score=75.0,
        match_gaps=[],
        interview_ratings={
            "interview_round_1": _round("HR Interview", "Ana Reyes", {"A": 3, "B": 4, "C": 3, "D": None}, "recommended"),
            "interview_round_2": {"label": "Panel Interview", "assigned_evaluator_name": "Ben Cruz", "computed_score": None},
        },
        exam_score=None,
        exam_rank=None,
        exam_cohort=None,
    ),
}


# ---------------------------------------------------------------- the AI steps


def _skill_matching(monkeypatch: pytest.MonkeyPatch, *, query_expansion: bool) -> list[dict]:
    """The whole of run_skill_matching: the arithmetic half's embeddings
    and the retrieval pipeline's seven agents, then the verdict audit and
    re-check. Only the two database reads are stood in for."""
    caught = _catch(monkeypatch, _skill_matching_answers())
    monkeypatch.setattr(settings, "rag_query_expansion", query_expansion)
    monkeypatch.setattr(skill_matching, "current_version_number", lambda db, requisition_id: 1)
    monkeypatch.setattr(skill_matching, "_suggest_other_openings", lambda *args, **kwargs: [])
    skill_matching.run_skill_matching(MagicMock(), resume=_RESUME, target_requisition=_JOB)
    return caught.requests


def _query_expansion(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Both probe prompts on their own: the first pass, and the retry
    that is told what the Critic could not support."""
    caught = _catch(monkeypatch, _skill_matching_answers())
    llm = skill_matching._get_llm()
    role = f"{_JOB.title}, {_JOB.department}"
    rag_catalog._expand_queries(llm, _REQUIREMENTS, role)
    rag_catalog._expand_queries(
        llm,
        _REQUIREMENTS[3:],
        role,
        objections=AuditVerdict(
            is_grounded=False,
            unsupported_claims=["No evidence of communication skills."],
            needs_more_context=[_REQUIREMENTS[3]],
        ),
    )
    return caught.requests


def _warm_up(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    caught = _catch(monkeypatch)
    skill_matching.warm_up()
    return caught.requests


def _decision_brief(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    caught = _catch(
        monkeypatch, {DecisionBriefResult: [DecisionBriefResult(verdict="A sound hire.", rationale="Because.")]}
    )
    for case in _BRIEF_CASES.values():
        facts = decision_brief.build_facts(
            job_title=_JOB.title,
            match_score=case["match_score"],
            match_gaps=case["match_gaps"],
            aspects=aspect_scores(case["interview_ratings"]),
            agreement=evaluator_agreement(case["interview_ratings"]),
            exam_score=case["exam_score"],
            exam_rank=case["exam_rank"],
            exam_cohort=case["exam_cohort"],
        )
        decision_brief.run_decision_brief(MagicMock(), application_id=42, stage_type="final_decision", facts=facts)
    return caught.requests


def _interview_analysis(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    caught = _catch(
        monkeypatch,
        {InterviewAnalysisResult: [InterviewAnalysisResult(strengths=["Clear."], gaps=["Thin."], summary="Mixed.")]},
    )
    interview_analysis.run_interview_analysis(
        MagicMock(),
        application_id=42,
        questions=[
            {"id": "q1", "text": "Why do you want to teach at MSEUF?"},
            {"id": "q2", "text": "Describe a capstone project you supervised."},
            {"id": "q3", "text": "How do you handle a student who falls behind?"},
        ],
        answers=[
            PreScreeningAnswer(question_id="q1", value="I studied here and want to give back to the college."),
            PreScreeningAnswer(question_id="q2", value="A library system built by four students in Django."),
            PreScreeningAnswer(question_id="q3", value="   "),
        ],
    )
    return caught.requests


def _interview_synthesis(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    caught = _catch(
        monkeypatch,
        {InterviewSynthesisResult: [InterviewSynthesisResult(rubric_coverage_score=70.0, summary="Documented.")]},
    )
    ratings = {item.code: 4 for category in SCORECARD_CATEGORIES for item in category.items}
    interview_synthesis.run_interview_synthesis(
        MagicMock(),
        application_id=42,
        stage_type="interview_round_1",
        item_ratings=ratings,
        remarks="Answered every question with concrete examples from her lecturing work.",
    )
    sparse = {**ratings, "C3": None, "D3": None, "A1": 2}
    interview_synthesis.run_interview_synthesis(
        MagicMock(), application_id=42, stage_type="interview_round_2", item_ratings=sparse, remarks=""
    )
    return caught.requests


def _jd_extraction(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    caught = _catch(
        monkeypatch,
        {
            JDExtractionCandidate: [
                JDExtractionCandidate(
                    department=_JOB.department,
                    description=_JOB.description,
                    qualifications=_JOB.qualifications,
                    requirements=_JOB.requirements,
                    additional_sections=[],
                    is_job_description=True,
                    document_kind="job description",
                    reason="",
                )
            ]
        },
    )

    def read_text(pdf_bytes, *, max_chars):
        caught.requests.append({"reads_jd_text": {"max_chars": max_chars}})
        return "INSTRUCTOR I\nCollege of Computing and Multimedia Studies\nQualifications: a master's degree."

    monkeypatch.setattr(jd_extraction, "read_job_description_text", read_text)
    jd_extraction.extract_job_description("Instructor I", b"%PDF-1.4 sample")
    return caught.requests


def _jd_image_reading(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    caught = _catch(
        monkeypatch,
        {
            JDImageReading: [
                JDImageReading(
                    is_job_description=True, document_kind="job description", reason="", text="INSTRUCTOR I"
                )
            ]
        },
    )
    jd_text._read_page_images(["data:image/jpeg;base64,AAAA", "data:image/jpeg;base64,BBBB"])
    return caught.requests


def _resume_extraction(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    caught = _catch(
        monkeypatch,
        {
            ResumeExtractionResult: [
                ResumeExtractionResult(
                    full_name="Maria Santos",
                    email="",
                    phone="",
                    location="",
                    linkedin_url="",
                    portfolio_url="",
                    professional_summary="",
                    education=[],
                    experience=[],
                    skills=["Python"],
                    certifications=[],
                )
            ]
        },
    )

    def read_text(pdf_bytes, *, max_chars):
        caught.requests.append({"reads_resume_text": {"max_chars": max_chars}})
        return "MARIA SANTOS\nPart-time Lecturer, Southern Luzon State University\nSkills: Python, Java"

    monkeypatch.setattr(resume_extraction, "read_resume_text", read_text)
    resume_extraction.extract_resume(b"%PDF-1.4 sample")
    return caught.requests


def _resume_image_reading(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    caught = _catch(
        monkeypatch,
        {ResumeImageReading: [ResumeImageReading(is_resume=True, reason="A CV.", text="MARIA SANTOS")]},
    )
    resume_text._read_page_images(["data:image/jpeg;base64,AAAA", "data:image/jpeg;base64,BBBB"])
    return caught.requests


_PARTS = {
    "skill_matching": lambda mp: _skill_matching(mp, query_expansion=False),
    "skill_matching_with_query_expansion": lambda mp: _skill_matching(mp, query_expansion=True),
    "query_expansion": _query_expansion,
    "skill_matching_warm_up": _warm_up,
    "decision_brief": _decision_brief,
    "interview_analysis": _interview_analysis,
    "interview_synthesis": _interview_synthesis,
    "jd_extraction": _jd_extraction,
    "jd_image_reading": _jd_image_reading,
    "resume_extraction": _resume_extraction,
    "resume_image_reading": _resume_image_reading,
}

_ANSWER_FORMATS = (
    AuditVerdict,
    DecisionBriefResult,
    InterviewAnalysisResult,
    InterviewSynthesisResult,
    JDExtractionCandidate,
    JDImageReading,
    QueryExpansion,
    RecheckResult,
    ResumeExtractionResult,
    ResumeImageReading,
    SkillMatchAnalysis,
    VerdictAuditResult,
)


def _pretty(value) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)


@pytest.fixture(scope="module")
def sent() -> dict:
    """What each AI step sends today, plus each answer format's schema
    (the schema, docstrings and field descriptions included, goes to the
    model as part of the request)."""
    current: dict = {}
    for part, run in _PARTS.items():
        with pytest.MonkeyPatch.context() as monkeypatch:
            # through JSON and back, so it compares exactly as the lock
            # file reads
            current[part] = json.loads(json.dumps(run(monkeypatch)))
    current["answer_formats"] = {schema.__name__: schema.model_json_schema() for schema in _ANSWER_FORMATS}
    if os.environ.get("ARKIVE_RECORD_AI_LOCK"):
        LOCK_FILE.write_text(_pretty(current) + "\n", encoding="utf-8")
    return current


@pytest.fixture(scope="module")
def locked(sent) -> dict:
    return json.loads(LOCK_FILE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("part", [*_PARTS, "answer_formats"])
def test_the_ai_is_sent_exactly_what_was_locked(part: str, sent: dict, locked: dict) -> None:
    assert part in locked, f"{part} is not in {LOCK_FILE.name} yet. {_HOW_TO_RECORD}"
    if sent[part] != locked[part]:
        diff = "\n".join(
            difflib.unified_diff(
                _pretty(locked[part]).splitlines(), _pretty(sent[part]).splitlines(), "locked", "now", lineterm=""
            )
        )
        pytest.fail(f"What the AI is sent for {part} has changed:\n{diff}\n\n{_HOW_TO_RECORD}")


def test_the_lock_has_nothing_the_capture_no_longer_makes(locked: dict) -> None:
    assert set(locked) == {*_PARTS, "answer_formats"}, _HOW_TO_RECORD


def test_every_ai_step_is_covered_by_the_lock() -> None:
    """A file that starts talking to a model must be added to the
    capture above, or this lock would quietly stop covering everything."""
    talking = {
        path.relative_to(APP_DIR).as_posix()
        for path in APP_DIR.rglob("*.py")
        if any(marker in path.read_text(encoding="utf-8") for marker in _AI_CALL_MARKERS)
    }
    assert talking == _FILES_THAT_CALL_THE_AI, (
        "These files call a model but the lock does not capture them, or no longer do: "
        f"{sorted(talking ^ _FILES_THAT_CALL_THE_AI)}"
    )
