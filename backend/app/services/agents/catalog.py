"""The eight agents of the hiring process, declared once."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.agents.base import Agent, PipelineAgent

__all__ = [
    "AGENTS",
    "BY_NAME",
    "DECISION_BRIEF",
    "DECISION_SUPPORT",
    "DOCUMENT_PARSING",
    "EVALUATOR_SCORECARD",
    "EXAM_SCHEDULING",
    "INTERVIEW_ANALYSIS",
    "INTERVIEW_SYNTHESIS",
    "SKILL_MATCHING",
]


class DocumentParsingAgent(Agent):
    """Runs in the applicant's upload route, not the pre-screening graph —
    it has to finish before the application row exists in a usable state."""

    name = "document_parsing_agent"
    label = "Document Parsing Agent"
    duty = "Normalizes the uploaded resume PDF into structured fields."


class SkillMatchingAgent(PipelineAgent):
    """Hybrid RAG — BM25 keyword scoring and dense-embedding retrieval,
    combined by reciprocal-rank fusion — scoring the resume against the
    requisition. Its `flagged` verdict is what freezes the DFA downstream,
    though applying the freeze is the router's job, not the agent's."""

    name = "matching_agent"
    label = "Skill Matching Agent"
    duty = "Scores the candidate against the requisition (RAG + BM25) and flags weak fits."

    def run(self, state: Mapping[str, Any], ctx: Mapping[str, Any]) -> dict[str, Any]:
        from app.services.skill_matching import run_skill_matching

        return {
            "match": run_skill_matching(
                ctx["db"], resume=ctx["resume"], target_requisition=ctx["requisition"]
            )
        }


class InterviewAnalysisAgent(PipelineAgent):
    """Reads the applicant's own answers to HR's pre-screening questions.
    Skipped entirely for a job that asks none — see the graph's conditional
    edge, which is why this is a `PipelineAgent` and not just an `Agent`."""

    name = "interview_analysis_agent"
    label = "Interview Analysis Agent"
    duty = "Reads the applicant's pre-screening answers for strengths and gaps."

    def run(self, state: Mapping[str, Any], ctx: Mapping[str, Any]) -> dict[str, Any]:
        from app.services.interview_analysis import run_interview_analysis

        return {
            "analysis": run_interview_analysis(
                ctx["db"],
                application_id=state["application_id"],
                questions=ctx["requisition"].pre_screening_questions,
                answers=ctx["answers"],
            )
        }


class ExamSchedulingAgent(Agent):
    """Deliberately not an LLM: booking a seat under a capacity limit is
    arithmetic, not language. Logged when an applicant books an exam
    session (services/exam_scheduling.book_session), in the Examination
    stage -- not a Pre-Screening graph node."""

    name = "exam_scheduling_agent"
    label = "Exam Scheduling Agent"
    duty = "Validates and assigns examination slot bookings."


class EvaluatorScorecardAgent(Agent):
    """Arithmetic over the HRD-F-APIEF form, run when an evaluator submits.
    Logged as an agent because the Synthesis tab's audit trail should show
    every automated step that touched the record, not only the AI ones."""

    name = "evaluator_scorecard_agent"
    label = "Evaluator Scorecard Agent"
    duty = "Computes each interview round's rubric total and qualification tier."


class InterviewSynthesisAgent(Agent):
    """Judges how well each evaluator's written remarks substantiate the
    ratings they gave — grading the documentation, not the candidate."""

    name = "interview_synthesis_agent"
    label = "Interview Synthesis Agent"
    duty = "Judges how thoroughly each evaluator's remarks substantiate their ratings."


class DecisionBriefAgent(Agent):
    """Turns the computed fact sheet into prose HR can read. Writes only
    when the facts have actually changed, keyed on their fingerprint."""

    name = "decision_brief_agent"
    label = "Decision Brief Agent"
    duty = "Writes the plain-language justification from the computed facts."


class DecisionSupportAgent(Agent):
    """The only `derived` agent: never runs and writes no AgentRun row. It
    is the Weighted Sum Model applied to the other agents' outputs, listed
    so the final score is attributable; its status is always "derived"."""

    name = "decision_support_agent"
    label = "Decision Support Agent"
    duty = "Aggregates the four criteria below into the weighted final synthesis score."
    kind = "derived"


DOCUMENT_PARSING = DocumentParsingAgent()
SKILL_MATCHING = SkillMatchingAgent()
INTERVIEW_ANALYSIS = InterviewAnalysisAgent()
EXAM_SCHEDULING = ExamSchedulingAgent()
EVALUATOR_SCORECARD = EvaluatorScorecardAgent()
INTERVIEW_SYNTHESIS = InterviewSynthesisAgent()
DECISION_BRIEF = DecisionBriefAgent()
DECISION_SUPPORT = DecisionSupportAgent()

#: The single list: synthesis.py builds the coverage panel from it, in
#: this order (the candidate's journey), and each agent's module imports
#: its singleton from here to log a run.
AGENTS: tuple[Agent, ...] = (
    DOCUMENT_PARSING,
    SKILL_MATCHING,
    INTERVIEW_ANALYSIS,
    EXAM_SCHEDULING,
    EVALUATOR_SCORECARD,
    INTERVIEW_SYNTHESIS,
    DECISION_BRIEF,
    DECISION_SUPPORT,
)

BY_NAME: dict[str, Agent] = {agent.name: agent for agent in AGENTS}
