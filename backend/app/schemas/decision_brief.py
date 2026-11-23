"""The Decision Brief Agent's output shape (services/decision_brief.py)."""

from pydantic import BaseModel


class DecisionBriefResult(BaseModel):
    """`verdict` is one short sentence HR can read at a glance;
    `rationale` is the two-to-four-sentence justification underneath.

    Both are written from a fixed list of already-computed facts and
    nothing else, so every claim is checkable against a number on the
    same screen. The model never sees the resume, JD, or interview
    remarks -- that's what keeps this a summary, not a second,
    unaccountable opinion."""

    verdict: str
    rationale: str
