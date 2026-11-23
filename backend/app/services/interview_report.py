"""The interview results report for one job (build_interview_report)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.dfa import is_interview_stage
from app.domain.scorecard import RECOMMENDATION_LABELS, TIER_LABELS, compute_tier
from app.models.candidate_application import CandidateApplication
from app.models.enums import ApplicationStatus, StageStatus, StageType
from app.models.job_requisition import JobRequisition
from app.models.stage_instance import StageInstance
from app.models.user import User
from app.schemas.interview_report import (
    InterviewReport,
    InterviewReportCell,
    InterviewReportEntry,
    InterviewReportExcluded,
    InterviewReportPending,
    InterviewReportRound,
)
from app.services.stage_labels import resolve_stage_label

__all__ = ["PH_TIME", "build_interview_report", "report_filename"]

# The report is read in Lucena. The Philippines keeps one offset all year,
# so a fixed zone is exact and needs no tz database in the container.
PH_TIME = timezone(timedelta(hours=8), "PHT")

# still moving through the pipeline -- the only statuses that can still
# finish a round
_OPEN_STATUSES = {ApplicationStatus.active, ApplicationStatus.flagged}


def report_filename(job_title: str) -> str:
    """A safe filename, not the title verbatim -- HR may name a job
    anything, including characters a download can't carry."""
    safe = "".join(c if c.isalnum() else "-" for c in job_title).strip("-") or "job"
    while "--" in safe:
        safe = safe.replace("--", "-")
    return f"interview-results-{safe.lower()}.pdf"


def _evaluation(instance: StageInstance | None) -> dict | None:
    """The submitted scorecard on a round, or None."""
    evaluation = (instance.payload or {}).get("evaluation") if instance else None
    if isinstance(evaluation, dict) and evaluation.get("submitted_at") is not None:
        return evaluation
    return None


def _submitted(instance: StageInstance) -> bool:
    return _evaluation(instance) is not None


def _round_state(instance: StageInstance | None) -> str:
    """"scored", "passed" (behind the candidate with no scorecard) or
    "open". A round is left only through the transition, which records
    it `skipped` when no scorecard was in; `complete` without one is an
    older record, and it is just as finished."""
    if instance is None:
        return "open"
    if _submitted(instance):
        return "scored"
    if instance.status in (StageStatus.skipped, StageStatus.complete):
        return "passed"
    return "open"


def build_interview_report(db: Session, requisition: JobRequisition) -> InterviewReport:
    """The interview results report for `requisition`. Only reads.

    Final score: HR's own formula, the plain average of the submitted
    rounds' computed_score, e.g. (interviewer 1 + 2 + 3) / 3. Deliberately
    NOT the Candidate Profile's 30/30/40 consensus (Algorithm 04). Ties
    share a rank.

    A candidate enters once they reach the job's first interview round:
    - ranked: every round is behind them (_round_state) and at least one
      was scored;
    - pending: an open application with a round still to come; while
      anyone is pending, `ready` is False;
    - excluded: withdrew, closed before the rounds were done, or no round
      has a score.

    A job with no interview rounds gets an empty report with
    `has_interviews` False.
    """
    workflow = list(requisition.workflow_definition or [])
    round_stages = [stage for stage in workflow if is_interview_stage(stage)]

    def report(**fields) -> InterviewReport:
        defaults = dict(
            requisition_id=requisition.id,
            job_title=requisition.title,
            department=requisition.department,
            has_interviews=bool(round_stages),
            ready=False,
            rounds=[],
            entries=[],
            pending=[],
            excluded=[],
            generated_at=datetime.now(PH_TIME),
            filename=report_filename(requisition.title),
        )
        return InterviewReport(**{**defaults, **fields})

    if not round_stages:
        return report()

    first_round = workflow.index(round_stages[0])
    reached = [
        application
        for application in db.scalars(
            select(CandidateApplication)
            .where(CandidateApplication.requisition_id == requisition.id)
            .order_by(CandidateApplication.id)
        )
        if application.current_stage is not None
        and application.current_stage.value in workflow
        and workflow.index(application.current_stage.value) >= first_round
    ]

    instances: dict[int, dict[str, StageInstance]] = {}
    if reached:
        for instance in db.scalars(
            select(StageInstance).where(
                StageInstance.application_id.in_([a.id for a in reached]),
                StageInstance.stage_type.in_([StageType(s) for s in round_stages]),
            )
        ):
            instances.setdefault(instance.application_id, {})[instance.stage_type.value] = instance

    people_ids = {a.applicant_id for a in reached} | {
        i.assigned_evaluator_id
        for by_stage in instances.values()
        for i in by_stage.values()
        if i.assigned_evaluator_id
    }
    names: dict[int, str] = (
        dict(db.execute(select(User.id, User.full_name).where(User.id.in_(people_ids))).all())
        if people_ids
        else {}
    )

    ranked_ids: list[int] = []
    pending: list[InterviewReportPending] = []
    excluded: list[InterviewReportExcluded] = []
    for application in reached:
        name = names.get(application.applicant_id, "Unnamed applicant")
        by_stage = instances.get(application.id, {})
        states = {stage: _round_state(by_stage.get(stage)) for stage in round_stages}

        if application.status == ApplicationStatus.withdrawn:
            excluded.append(InterviewReportExcluded(applicant_name=name, reason="Withdrew their application."))
        elif "open" not in states.values():
            if "scored" in states.values():
                ranked_ids.append(application.id)
            else:
                excluded.append(
                    InterviewReportExcluded(
                        applicant_name=name, reason="Moved past the interviews without a scorecard in any round."
                    )
                )
        elif application.status in _OPEN_STATUSES:
            waiting_on = []
            for stage in round_stages:
                if states[stage] != "open":
                    continue
                instance = by_stage.get(stage)
                evaluator = names.get(instance.assigned_evaluator_id) if instance and instance.assigned_evaluator_id else None
                waiting_on.append(
                    f"{resolve_stage_label(stage, requisition)} ({evaluator or 'no interviewer assigned yet'})"
                )
            pending.append(
                InterviewReportPending(application_id=application.id, applicant_name=name, waiting_on=waiting_on)
            )
        else:
            excluded.append(
                InterviewReportExcluded(
                    applicant_name=name, reason="The application was closed before the interviews were finished."
                )
            )

    applications = {a.id: a for a in reached}
    entries: list[InterviewReportEntry] = []
    for application_id in ranked_ids:
        application = applications[application_id]
        by_stage = instances.get(application_id, {})
        cells = []
        for stage in round_stages:
            instance = by_stage.get(stage)
            evaluation = _evaluation(instance)
            # the interviewer's own pick on the form, never inferred from
            # the score -- a 4.70 can still be "Not Recommended"
            recommendation = evaluation.get("recommendation") if evaluation else None
            score = evaluation.get("computed_score") if evaluation else None
            # stored on the scorecard at submission; banded from the score
            # only for a scorecard that somehow lacks it
            tier = (evaluation.get("tier") or (compute_tier(score) if score is not None else None)) if evaluation else None
            cells.append(
                InterviewReportCell(
                    stage_type=stage,
                    score=score,
                    tier=tier,
                    tier_label=TIER_LABELS.get(tier) if tier else None,
                    recommendation=recommendation,
                    recommendation_label=RECOMMENDATION_LABELS.get(recommendation) if recommendation else None,
                    evaluator_name=names.get(instance.assigned_evaluator_id)
                    if instance and instance.assigned_evaluator_id
                    else None,
                    no_scorecard=evaluation is None,
                )
            )
        scores = [cell.score for cell in cells if cell.score is not None]
        name = names.get(application.applicant_id, "Unnamed applicant")
        if not scores:
            # every scorecard predates the current form, which has no
            # score to rank on -- see candidate_profile's legacy note
            excluded.append(
                InterviewReportExcluded(
                    applicant_name=name,
                    reason="Their scorecards predate the current form, so there is no score to rank.",
                )
            )
            continue
        entries.append(
            InterviewReportEntry(
                rank=0,
                application_id=application_id,
                applicant_name=name,
                cells=cells,
                # summed total / number of interviewers. a round with no
                # scorecard is left out rather than counted as a zero
                final_score=round(sum(scores) / len(scores), 2),
                partial=len(scores) < len(round_stages),
            )
        )

    # highest first; equal scores share a rank (1, 2, 2, 4), and are
    # listed alphabetically so the order is stable between downloads
    entries.sort(key=lambda e: (-e.final_score, e.applicant_name.casefold()))
    for position, entry in enumerate(entries):
        tied = position > 0 and entry.final_score == entries[position - 1].final_score
        entry.rank = entries[position - 1].rank if tied else position + 1

    rounds = []
    for stage in round_stages:
        evaluators = {cell.evaluator_name for entry in entries for cell in entry.cells if cell.stage_type == stage}
        rounds.append(
            InterviewReportRound(
                stage_type=stage,
                label=resolve_stage_label(stage, requisition),
                evaluator_name=next(iter(evaluators)) if len(evaluators) == 1 else None,
            )
        )

    return report(
        ready=bool(entries) and not pending,
        rounds=rounds,
        entries=entries,
        pending=pending,
        excluded=excluded,
    )
