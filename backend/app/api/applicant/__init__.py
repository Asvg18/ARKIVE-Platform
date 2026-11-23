"""Applicant-facing routes: apply, view own applications, and submit each
pipeline stage's screen. Every route checks the role, then ownership
(common.own_application): someone else's application is a 404.
"""

from fastapi import APIRouter

from . import applications, documents, scheduling, stages

router = APIRouter(tags=["applicant"])

# registered in the same order the routes had in the single module
router.include_router(applications.router)
router.include_router(documents.router)
router.include_router(stages.router)
router.include_router(scheduling.router)
