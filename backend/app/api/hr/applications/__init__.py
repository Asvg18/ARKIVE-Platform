"""A candidate application as HR works it: reading and reviewing it
(review), recording outcomes (outcomes), scheduling interviews
(scheduling), and the decisions that write to the candidate (decisions).
"""

from fastapi import APIRouter

from . import decisions, outcomes, review, scheduling
from .decisions import _DECISION_NOTIFICATIONS

__all__ = ["router", "_DECISION_NOTIFICATIONS"]  # the decision wording is read by tests

router = APIRouter(tags=["applications"])

# registered in the same order the routes had in the single module
router.include_router(review.router)
router.include_router(outcomes.router)
router.include_router(scheduling.router)
router.include_router(decisions.router)
