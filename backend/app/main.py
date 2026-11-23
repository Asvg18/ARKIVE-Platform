from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.infra.config import settings
from app.infra.deps import RENEWED_TOKEN_HEADER
from app.api import account, applicant, auth, evaluator, invites, notifications, public, transitions
from app.api.hr import (
    applications,
    dashboard,
    decisions,
    evaluators,
    exam_slots,
    files,
    job_descriptions,
    requisitions,
    workflow,
)
from app.services.skill_matching import warm_up as warm_up_skill_matching


@asynccontextmanager
async def lifespan(app: FastAPI):
    # pays the AI clients' first-connection cost here, at boot, instead
    # of on whichever applicant's request happens to be first
    warm_up_skill_matching()
    yield


app = FastAPI(title="ARKIVE API", lifespan=lifespan)

# Vite and FastAPI are different origins, so CORS has to be opened
# explicitly. Configurable via CORS_ORIGINS so the API can be reached
# from a LAN address or deployed frontend without editing code.
#
# still an allow-list, never "*" -- allow_credentials=True with a
# wildcard origin is rejected by browsers outright, and this API carries
# bearer tokens
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # without this the browser hides X-Renewed-Token from JavaScript on
    # any cross-origin response -- exactly the local dev setup (Vite on
    # 5173, API on 8000) -- and sessions would silently keep expiring at
    # the hard 60-minute mark with no sign of why
    expose_headers=[RENEWED_TOKEN_HEADER],
)

app.include_router(auth.router)
app.include_router(account.router)
app.include_router(account.avatar_router)
app.include_router(public.router)
app.include_router(applicant.router)
app.include_router(evaluator.router)
app.include_router(notifications.router)
app.include_router(invites.router)
app.include_router(transitions.router)

# The former pipeline.py, split by resource. Order is irrelevant to
# routing (paths are literal and non-overlapping) but is kept in the
# order HR meets them: the dashboard, then a job, then its pipeline.
app.include_router(dashboard.router)
app.include_router(requisitions.router)
app.include_router(workflow.router)
app.include_router(evaluators.router)
app.include_router(exam_slots.router)
app.include_router(applications.router)
app.include_router(decisions.router)
app.include_router(files.router)
app.include_router(job_descriptions.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
