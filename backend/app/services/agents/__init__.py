"""The agents: `base` defines them, `catalog` declares the eight of the
hiring process, `rag_catalog` the Skill Matching Agent's sub-agents.
"""

from app.services.agents.base import Agent, AgentKind, PipelineAgent, SubAgent
from app.services.agents.catalog import (
    AGENTS,
    BY_NAME,
    DECISION_BRIEF,
    DECISION_SUPPORT,
    DOCUMENT_PARSING,
    EVALUATOR_SCORECARD,
    EXAM_SCHEDULING,
    INTERVIEW_ANALYSIS,
    INTERVIEW_SYNTHESIS,
    SKILL_MATCHING,
)

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
    "Agent",
    "AgentKind",
    "PipelineAgent",
    "SubAgent",
]
