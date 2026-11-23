import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { ApplicationDetail } from "../../../../shared/api/applicant";
import { isExamStage, isInterviewStage } from "../../../../shared/lib/stageLabels";
import { ApplicantAppShell } from "../components/ApplicantAppShell";
import { useLiveRefresh } from "../../../../shared/hooks/useLiveRefresh";
import { ErrorState } from "../../../../shared/ui/ErrorState";
import { StageLayout } from "../components/StageLayout";
import { DocumentUploadScreen } from "../stages/DocumentUploadScreen";
import { FlaggedReviewScreen } from "../stages/FlaggedReviewScreen";
import { PreScreeningScreen } from "../stages/PreScreeningScreen";
import { ScheduleScreen } from "../stages/ScheduleScreen";
import { FinalSelectionScreen } from "../stages/FinalSelectionScreen";
import { ShortlistingResponseScreen } from "../stages/ShortlistingResponseScreen";
import { OnboardingScreen } from "../stages/OnboardingScreen";
import { OfferResponseScreen } from "../stages/OfferResponseScreen";
import { ClosedApplicationScreen } from "../stages/ClosedApplicationScreen";

export function ApplicationStagePage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const [application, setApplication] = useState<ApplicationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  function load(options: { silent?: boolean } = {}) {
    if (!options.silent) {
      setLoading(true);
      setError(null);
    }
    apiFetch<ApplicationDetail>(`/applicant/applications/${id}`, { token })
      .then(setApplication)
      .catch((err) => {
        if (!options.silent) setError(err instanceof ApiError ? err.message : "Failed to load.");
      })
      .finally(() => {
        if (!options.silent) setLoading(false);
      });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, token, reloadKey]);

  // Focus-only, deliberately. This is the one screen where the applicant
  // is typing — resume upload, pre-screening answers, exam booking — and
  // that form state lives inside whatever renderStageScreen returns,
  // which this page can't see into. No `enabled` flag to gate a timer
  // on, so the rule is: refresh only when they come back to the window,
  // since they can't be typing in a tab they aren't looking at. Their
  // own submissions already update the view directly via setApplication.
  useLiveRefresh(() => load({ silent: true }), { intervalMs: null });

  if (loading || error || !application) {
    return (
      <ApplicantAppShell wide>
        {loading && <p style={{ fontFamily: "var(--arkive-font)", color: "var(--ink-600)" }}>Loading...</p>}
        {error && <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />}
      </ApplicantAppShell>
    );
  }

  return (
    <StageLayout application={application} onUpdate={setApplication}>
      {application.status === "flagged" ? (
        <FlaggedReviewScreen application={application} />
      ) : application.status === "hired" ? (
        // Accepted used to fall straight through to the closed-status
        // line below, which left an accepted applicant with no way to
        // confirm, no way to decline, and no onboarding checklist — the
        // gap round-2 items 1a/1b/1c were raised about. `hired` is the
        // one non-active status that still has something for them to do.
        <OfferResponseScreen application={application} token={token} onUpdate={setApplication} />
      ) : application.status !== "active" ? (
        <ClosedApplicationScreen application={application} />
      ) : (
        renderStageScreen(application, token, setApplication)
      )}
    </StageLayout>
  );
}

function renderStageScreen(
  application: ApplicationDetail,
  token: string | null,
  setApplication: (a: ApplicationDetail) => void
) {
  const stage = application.current_stage;
  if (!stage) return <p>No active stage.</p>;

  if (stage === "document_upload") {
    return <DocumentUploadScreen application={application} token={token} onAdvance={setApplication} />;
  }
  if (stage === "skill_matching") {
    return <PreScreeningScreen application={application} token={token} onAdvance={setApplication} />;
  }
  // Read-only while HR is still deciding; once they shortlist, this is
  // the one stage that asks the applicant something rather than telling
  // them -- they confirm before an examination is booked in their name.
  // ShortlistingResponseScreen falls back to the same read-only screen
  // when there is nothing to answer.
  if (stage === "shortlisting") {
    return <ShortlistingResponseScreen application={application} token={token} onUpdate={setApplication} />;
  }
  // isExamStage/isInterviewStage, not a bare === "examination": jobs use
  // the generic examination_1..4 and interview_round_1..6 slots now, and
  // an exact match against the legacy singular string dropped every
  // numbered exam through to the "No screen for stage..." placeholder —
  // so an exam candidate couldn't see their own schedule.
  if (isExamStage(stage) || isInterviewStage(stage)) {
    return <ScheduleScreen application={application} token={token} onUpdate={setApplication} />;
  }
  if (stage === "final_decision") {
    return <FinalSelectionScreen application={application} />;
  }
  if (stage === "onboarding") {
    return <OnboardingScreen application={application} token={token} onUpdate={setApplication} />;
  }
  return <p>No screen for stage "{stage}" yet.</p>;
}
