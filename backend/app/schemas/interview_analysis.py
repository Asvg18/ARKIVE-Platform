"""Interview Analysis Agent's output shape -- a qualitative, grounded
GPT-4o-mini read of an applicant's AI Pre-Screening answers. See
services/interview_analysis.py."""

from pydantic import BaseModel


class InterviewAnalysisResult(BaseModel):
    """No numeric score alongside this, unlike SkillMatchAnalysis's
    sibling SkillMatchResult -- no retrieval/ranking metadata to carry,
    since this agent reads a handful of already-enumerable Q&A pairs
    directly instead of chunking a document."""

    strengths: list[str]
    gaps: list[str]
    summary: str
