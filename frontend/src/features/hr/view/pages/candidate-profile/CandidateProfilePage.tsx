import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useAuth } from "../../../../auth/controller/AuthContext";
import { apiFetch, ApiError } from "../../../../../shared/api/client";
import type {
  ApplicationListItem,
  ApplicationStatus,
  CandidateProfile,
  DecisionBlocker,
  HeadlineSignal,
  IncompleteRecordDetail,
  RequisitionDetail,
  RequisitionEvaluator,
  StageType,
} from "../../../../../shared/api/pipeline";
import { stageLabel } from "../../../../../shared/lib/stageLabels";
import { useStageTransition } from "../../../controller/useStageTransition";
import { AppShell } from "../../components/AppShell";
import { DecisionDialog } from "../../components/DecisionDialog";
import { StageAdvanceDialog } from "../../components/StageAdvanceDialog";
import { AdvanceDialog } from "../../components/AdvanceDialog";
import { asksBeforeAdvancing } from "../../../model/stageAdvance";
import { DecisionRecordPanel } from "../../components/DecisionRecordPanel";
import { useLiveRefresh } from "../../../../../shared/hooks/useLiveRefresh";
import { ErrorState } from "../../../../../shared/ui/ErrorState";
import { PageHeader } from "../../../../../shared/ui/PageHeader";
import type {
  EvaluatorAssignment,
  ExamBookingResolver,
  ExamScoreEditor,
  RescheduleResolver,
  SlotSender,
  ScheduleEditor,
  ShortlistingEditor,
} from "./types";
import { SYNTHESIS_EVIDENCE_ID, type EvidenceView } from "../../components/synthesis/SynthesisEvidence";
import { CandidateSidebar } from "./CandidateSidebar";
import { CandidateStepper } from "./CandidateStepper";
import { ProfileTabs } from "./ProfileTabs";
import { DEFAULT_TAB, TABLIST_ID, TABS, type Tab } from "./tabModel";
import { StatusActionDialog } from "./StatusActionDialog";
import { SynthesisTab } from "./tabs/SynthesisTab";
import { PreScreeningTab } from "./tabs/PreScreeningTab";
import { ShortlistingTab } from "./tabs/ShortlistingTab";
import { ExaminationsTab } from "./tabs/ExaminationsTab";
import { InterviewsTab } from "./tabs/InterviewsTab";
import { DocumentsTab } from "./tabs/DocumentsTab";

/** Where each of the verdict's facts is argued in full. The resume gaps
 * have no tab of their own — they are in the Synthesis tab's evidence
 * panel — so that one lands on its section; the others only need the
 * tab bar in view, which it usually already is. */
const SIGNAL_TARGET: Record<HeadlineSignal["key"], { tab: Tab; anchor: string; block: ScrollLogicalPosition }> = {
  evaluators: { tab: "interviews", anchor: TABLIST_ID, block: "nearest" },
  exam_rank: { tab: "examinations", anchor: TABLIST_ID, block: "nearest" },
  requirement_gaps: { tab: "synthesis", anchor: SYNTHESIS_EVIDENCE_ID, block: "start" },
};

/** Anything but a current tab falls back to the default, old links
 * included: ?tab=overview (now part of Synthesis) and ?tab=checks
 * (reference and background checks are retired). */
function isTab(value: string | null): value is Tab {
  return value !== null && (TABS as readonly string[]).includes(value);
}

/** The Pipelines List tab's order: best match first, unscored last. The
 *  step to the next candidate follows the list HR came from. */
function byMatchScore(a: ApplicationListItem, b: ApplicationListItem): number {
  if (a.match_score == null && b.match_score == null) return 0;
  if (a.match_score == null) return 1;
  if (b.match_score == null) return -1;
  return b.match_score - a.match_score;
}

/** Keyed by the application, so stepping to the next candidate starts
 *  from a clean page. Every inline editor here (a half-typed exam score,
 *  a schedule, the hire dialog) holds its state on this component; kept
 *  across a change of candidate, it would submit to the wrong person. */
export function CandidateProfilePage() {
  const { id } = useParams<{ id: string }>();
  return <CandidateProfileView key={id} id={id ?? ""} />;
}

function CandidateProfileView({ id }: { id: string }) {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);
  // The open tab lives in the URL rather than in state, so a link to what
  // you are looking at can be pasted to someone else and a refresh keeps
  // the tab. An unknown or absent value falls back to the default rather
  // than rendering nothing.
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const tab: Tab = isTab(tabParam) ? tabParam : DEFAULT_TAB;
  const setTab = (next: Tab) => {
    const params = new URLSearchParams(searchParams);
    // The default stays out of the URL, so the plain profile link is the
    // one people share.
    if (next === DEFAULT_TAB) params.delete("tab");
    else params.set("tab", next);
    // Replace rather than push: switching tabs is a change of view, not
    // navigation, and stacking every one of them would make Back mean
    // "undo a tab" instead of "return to the pipeline".
    setSearchParams(params, { replace: true });
  };
  const [shortlistEditingStage, setShortlistEditingStage] = useState<string | null>(null);
  const [shortlistOutcomeInput, setShortlistOutcomeInput] = useState<"shortlisted" | "not_shortlisted">("shortlisted");
  const [shortlistNotesInput, setShortlistNotesInput] = useState("");
  const [shortlistSubmitting, setShortlistSubmitting] = useState(false);
  const [shortlistError, setShortlistError] = useState<string | null>(null);
  const [examScoreEditingStage, setExamScoreEditingStage] = useState<string | null>(null);
  const [examScoreInput, setExamScoreInput] = useState("");
  const [examTakenOn, setExamTakenOn] = useState("");
  const [examSubmitting, setExamSubmitting] = useState(false);
  const [examError, setExamError] = useState<string | null>(null);
  const [scheduleEditingStage, setScheduleEditingStage] = useState<string | null>(null);
  const [scheduleDate, setScheduleDate] = useState("");
  const [scheduleTime, setScheduleTime] = useState("");
  const [scheduleMode, setScheduleMode] = useState<"in_person" | "online">("in_person");
  const [scheduleLocation, setScheduleLocation] = useState("");
  const [scheduleMeetingLink, setScheduleMeetingLink] = useState("");
  const [scheduleSubmitting, setScheduleSubmitting] = useState(false);
  const [scheduleError, setScheduleError] = useState<string | null>(null);
  const [pool, setPool] = useState<RequisitionEvaluator[]>([]);
  const [assigningStage, setAssigningStage] = useState<string | null>(null);
  const [assignError, setAssignError] = useState<{ stage: string; message: string } | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  // The hire/reject confirmation. `decisionBlockers` stays empty until
  // the server answers with a 409 — the completeness rules deliberately
  // live only on the server, so the dialog shows what the API actually
  // enforces rather than a client-side re-derivation of it.
  const [decisionMode, setDecisionMode] = useState<"hire" | "reject" | null>(null);
  const [decisionBlockers, setDecisionBlockers] = useState<DecisionBlocker[]>([]);
  const [decisionMessage, setDecisionMessage] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  // Advancing from here. The pipeline could always do this and this page
  // could not, so reading a candidate and then moving them meant going
  // back to find them in a list — the one screen that knows enough to
  // justify the move was the one screen that couldn't make it. Same
  // controller as the pipeline's own Advance button, and the same dialogs.
  const transition = useStageTransition(() => load());
  const advancing = transition.movingId !== null;
  const [advanceError, setAdvanceError] = useState<string | null>(null);
  // Reopen and the flag's two answers also ask first -- each changes
  // where a real person stands.
  const [confirmingAction, setConfirmingAction] = useState<"reopen" | "continue" | "reject_flagged" | null>(null);

  function load(options: { silent?: boolean } = {}) {
    if (!options.silent) {
      setLoading(true);
      setError(null);
    }
    apiFetch<CandidateProfile>(`/hr/applications/${id}/profile`, { token })
      .then(setProfile)
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

  // This page carries more in-progress input than any other — inline
  // editors for exam scores, shortlisting calls and interview schedules, the
  // evaluator assignment dropdown, and the hire/reject dialog. A
  // background refresh while any of them is open would re-render the
  // section underneath the person using it and throw away what they had
  // typed, which is worse than the stale data it was meant to fix. So
  // the poll pauses for all of them, and the explicit load() every one of
  // those actions already performs on success brings the page current
  // the moment it closes.
  const userIsEditing =
    shortlistEditingStage !== null ||
    examScoreEditingStage !== null ||
    scheduleEditingStage !== null ||
    assigningStage !== null ||
    decisionMode !== null ||
    transition.pendingSkip !== null ||
    advancing ||
    updating;

  useLiveRefresh(() => load({ silent: true }), { enabled: !userIsEditing });

  // The evaluator pool is job-wide, not per-application — fetched once
  // the profile tells us which requisition this candidate applied to.
  useEffect(() => {
    if (!profile) return;
    apiFetch<RequisitionEvaluator[]>(`/hr/requisitions/${profile.requisition_id}/evaluators`, { token })
      .then(setPool)
      .catch(() => {});
  }, [profile?.requisition_id, token]);

  async function assignEvaluator(stageType: string, evaluatorId: number | null) {
    setAssigningStage(stageType);
    setAssignError(null);
    try {
      await apiFetch(`/hr/applications/${id}/interview-assignment`, {
        method: "POST",
        token,
        body: { stage_type: stageType, evaluator_id: evaluatorId },
      });
      load();
    } catch (err) {
      setAssignError({
        stage: stageType,
        message: err instanceof ApiError ? err.message : "Could not assign the evaluator.",
      });
    } finally {
      setAssigningStage(null);
    }
  }

  const [resolvingRequestId, setResolvingRequestId] = useState<number | null>(null);
  const [resolveError, setResolveError] = useState<string | null>(null);

  async function resolveReschedule(
    requestId: number,
    decision: "approve" | "deny",
    date?: string,
    time?: string
  ) {
    setResolvingRequestId(requestId);
    setResolveError(null);
    try {
      await apiFetch(`/hr/applications/${id}/reschedule-requests/${requestId}/resolve`, {
        method: "POST",
        token,
        body: { decision, date: date ?? null, time: time ?? null },
      });
      load();
    } catch (err) {
      setResolveError(err instanceof ApiError ? err.message : "Could not resolve the request.");
    } finally {
      setResolvingRequestId(null);
    }
  }

  // Sending the evaluator's free slots to the applicant.
  const [slotStage, setSlotStage] = useState<string | null>(null);
  const [slotTicked, setSlotTicked] = useState<string[]>([]);
  const [slotMode, setSlotMode] = useState<"in_person" | "online">("in_person");
  const [slotLocation, setSlotLocation] = useState("");
  const [slotLink, setSlotLink] = useState("");
  const [slotSending, setSlotSending] = useState(false);
  const [slotError, setSlotError] = useState<string | null>(null);

  function openSlotSender(stageType: string) {
    const entry = profile?.interview_ratings[stageType];
    if (!entry) return;
    const where = entry.slot_offer ?? entry.schedule;
    setSlotTicked(entry.slot_choices.filter((c) => !c.taken).map((c) => `${c.date}|${c.time}`));
    setSlotMode(where?.mode ?? "in_person");
    setSlotLocation(where?.location ?? "");
    setSlotLink(where?.meeting_link ?? "");
    setSlotError(null);
    setSlotStage(stageType);
  }

  async function sendSlots() {
    if (!slotStage) return;
    if (slotTicked.length === 0) {
      setSlotError("Tick at least one time to send.");
      return;
    }
    setSlotSending(true);
    setSlotError(null);
    try {
      await apiFetch(`/hr/applications/${id}/interview-slots`, {
        method: "POST",
        token,
        body: {
          stage_type: slotStage,
          slots: slotTicked.map((key) => {
            const [date, time] = key.split("|");
            return { date, time };
          }),
          mode: slotMode,
          location: slotMode === "in_person" ? slotLocation : null,
          meeting_link: slotMode === "online" ? slotLink : null,
        },
      });
      setSlotStage(null);
      load();
    } catch (err) {
      setSlotError(err instanceof ApiError ? err.message : "Could not send these times.");
    } finally {
      setSlotSending(false);
    }
  }

  const [resolvingBookingId, setResolvingBookingId] = useState<number | null>(null);
  const [bookingResolveError, setBookingResolveError] = useState<string | null>(null);
  const [bookingSlotOverride, setBookingSlotOverride] = useState<Record<number, number>>({});

  async function resolveExamBooking(bookingId: number, decision: "approve" | "deny", examSlotId?: number) {
    setResolvingBookingId(bookingId);
    setBookingResolveError(null);
    try {
      await apiFetch(`/hr/applications/${id}/exam-bookings/${bookingId}/resolve`, {
        method: "POST",
        token,
        body: { decision, exam_slot_id: examSlotId ?? null },
      });
      load();
    } catch (err) {
      setBookingResolveError(err instanceof ApiError ? err.message : "Could not resolve this exam booking.");
    } finally {
      setResolvingBookingId(null);
    }
  }

  /** Move this candidate to the stage the DFA says comes next. The target
   *  is the server's own `next_stage`, not a client-side walk of the
   *  workflow, so the button can only ever ask for the transition the
   *  automaton would allow. */
  async function advanceStage() {
    const target = profile?.next_stage;
    if (!target) return;
    if (asksBeforeAdvancing(target)) {
      transition.askFirst({ applicationId: id, target });
      return;
    }
    await requestAdvance(target);
  }

  async function requestAdvance(target: StageType) {
    setAdvanceError(null);
    await transition.send({ applicationId: id, target }, "Could not advance this candidate.", setAdvanceError);
  }

  async function setStatus(
    status: ApplicationStatus,
    options: { reason?: string; acknowledged?: boolean } = {}
  ) {
    setUpdating(true);
    setActionError(null);
    setDecisionError(null);
    try {
      await apiFetch(`/hr/applications/${id}/status`, {
        method: "PATCH",
        token,
        body: {
          status,
          reason: options.reason?.trim() ? options.reason.trim() : null,
          acknowledged_incomplete: options.acknowledged ?? false,
        },
      });
      closeDecisionDialog();
      load();
    } catch (err) {
      // A 409 here is not a failure — it is the gate answering with the
      // list of what is outstanding. Keep the dialog open and show it,
      // so the next click is an informed one rather than a blind retry.
      const detail =
        err instanceof ApiError ? (err.detail as IncompleteRecordDetail | undefined) : undefined;
      if (detail?.blockers) {
        setDecisionBlockers(detail.blockers);
        setDecisionMessage(detail.message);
        setDecisionError(detail.code === "reason_required" ? detail.message : null);
      } else if (decisionMode) {
        setDecisionError(err instanceof ApiError ? err.message : "Could not update status.");
      } else {
        setActionError(err instanceof ApiError ? err.message : "Could not update status.");
      }
    } finally {
      setUpdating(false);
    }
  }

  function openDecisionDialog(mode: "hire" | "reject") {
    setDecisionMode(mode);
    setDecisionBlockers([]);
    setDecisionMessage(null);
    setDecisionError(null);
  }

  function closeDecisionDialog() {
    setDecisionMode(null);
    setDecisionBlockers([]);
    setDecisionMessage(null);
    setDecisionError(null);
  }

  async function resolveFlag(decision: "continue" | "reject") {
    setUpdating(true);
    setActionError(null);
    try {
      await apiFetch(`/hr/applications/${id}/resolve-flag`, { method: "POST", token, body: { decision } });
      load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not resolve the flag.");
    } finally {
      setUpdating(false);
    }
  }

  async function submitShortlistingResult(stageType: string) {
    setShortlistSubmitting(true);
    setShortlistError(null);
    try {
      await apiFetch(`/hr/applications/${id}/shortlisting-result`, {
        method: "PATCH",
        token,
        body: { stage_type: stageType, outcome: shortlistOutcomeInput, notes: shortlistNotesInput },
      });
      setShortlistNotesInput("");
      setShortlistEditingStage(null);
      load();
    } catch (err) {
      setShortlistError(err instanceof ApiError ? err.message : "Could not save the decision.");
    } finally {
      setShortlistSubmitting(false);
    }
  }

  async function submitExamScore(stageType: string) {
    const score = Number(examScoreInput);
    if (examScoreInput.trim() === "" || Number.isNaN(score) || score < 0 || score > 100) {
      setExamError("Enter a score between 0 and 100.");
      return;
    }
    if (!examTakenOn) {
      setExamError("Enter the date the exam was taken.");
      return;
    }
    setExamSubmitting(true);
    setExamError(null);
    try {
      await apiFetch(`/hr/applications/${id}/examination-result`, {
        method: "PATCH",
        token,
        body: { stage_type: stageType, score, taken_on: examTakenOn },
      });
      setExamScoreInput("");
      setExamScoreEditingStage(null);
      load();
    } catch (err) {
      setExamError(err instanceof ApiError ? err.message : "Could not save the score.");
    } finally {
      setExamSubmitting(false);
    }
  }

  // Interview rounds only: an exam's time is always a seat in one of the
  // job's sessions (Examinations tab), never typed.
  function openScheduleEditor(stageType: string) {
    const existing = profile?.interview_ratings[stageType]?.schedule;
    setScheduleDate(existing?.date ?? "");
    setScheduleTime(existing?.time ?? "");
    setScheduleMode(existing?.mode ?? "in_person");
    setScheduleLocation(existing?.location ?? "");
    setScheduleMeetingLink(existing?.meeting_link ?? "");
    setScheduleError(null);
    setScheduleEditingStage(stageType);
  }

  async function submitSchedule() {
    if (!scheduleEditingStage || !scheduleDate || !scheduleTime) {
      setScheduleError("Date and time are required.");
      return;
    }

    if (scheduleMode === "in_person" && !scheduleLocation.trim()) {
      setScheduleError("Location is required for an in-person interview.");
      return;
    }
    if (scheduleMode === "online" && !scheduleMeetingLink.trim()) {
      setScheduleError("A meeting link is required for an online interview.");
      return;
    }
    setScheduleSubmitting(true);
    setScheduleError(null);
    try {
      await apiFetch(`/hr/applications/${id}/interview-schedule`, {
        method: "POST",
        token,
        body: {
          stage_type: scheduleEditingStage,
          date: scheduleDate,
          time: scheduleTime,
          mode: scheduleMode,
          location: scheduleMode === "in_person" ? scheduleLocation : null,
          meeting_link: scheduleMode === "online" ? scheduleMeetingLink : null,
        },
      });
      setScheduleEditingStage(null);
      load();
    } catch (err) {
      setScheduleError(err instanceof ApiError ? err.message : "Could not save the schedule.");
    } finally {
      setScheduleSubmitting(false);
    }
  }

  // Server-ordered (see backend _build_candidate_profile, which iterates
  // requisition.workflow_definition) — a job can use any subset of the
  // generic interview_round_k slots, so there's no fixed order to filter
  // against here.
  const interviewRatings = profile ? Object.keys(profile.interview_ratings) : [];

  // Same server-ordered iteration reasoning as interviewRatings above — a
  // job can now use several examination_k slots, not just the one legacy
  // examination stage.
  const examStageKeys = profile ? Object.keys(profile.examinations) : [];
  const shortlistingStageKeys = profile ? Object.keys(profile.shortlisting) : [];
  const scoredExams = examStageKeys.filter((s) => profile!.examinations[s].score != null);


  // The tab bodies live in ./tabs/. They are handed these groups rather
  // than thirty loose props; the state itself stays here so a half-typed
  // score or schedule survives a tab switch (see ./types.ts).
  const scheduleEditor: ScheduleEditor = {
    editingStage: scheduleEditingStage,
    setEditingStage: setScheduleEditingStage,
    date: scheduleDate,
    setDate: setScheduleDate,
    time: scheduleTime,
    setTime: setScheduleTime,
    mode: scheduleMode,
    setMode: setScheduleMode,
    location: scheduleLocation,
    setLocation: setScheduleLocation,
    meetingLink: scheduleMeetingLink,
    setMeetingLink: setScheduleMeetingLink,
    submitting: scheduleSubmitting,
    error: scheduleError,
    open: openScheduleEditor,
    submit: submitSchedule,
  };
  const shortlistingEditor: ShortlistingEditor = {
    editingStage: shortlistEditingStage,
    setEditingStage: setShortlistEditingStage,
    outcome: shortlistOutcomeInput,
    setOutcome: setShortlistOutcomeInput,
    notes: shortlistNotesInput,
    setNotes: setShortlistNotesInput,
    submitting: shortlistSubmitting,
    error: shortlistError,
    setError: setShortlistError,
    submit: submitShortlistingResult,
  };
  const scoreEditor: ExamScoreEditor = {
    editingStage: examScoreEditingStage,
    setEditingStage: setExamScoreEditingStage,
    input: examScoreInput,
    setInput: setExamScoreInput,
    takenOn: examTakenOn,
    setTakenOn: setExamTakenOn,
    submitting: examSubmitting,
    error: examError,
    setError: setExamError,
    submit: submitExamScore,
  };
  const bookingResolver: ExamBookingResolver = {
    resolvingId: resolvingBookingId,
    error: bookingResolveError,
    slotOverride: bookingSlotOverride,
    setSlotOverride: setBookingSlotOverride,
    resolve: resolveExamBooking,
  };
  const evaluatorAssignment: EvaluatorAssignment = {
    pool,
    assigningStage,
    error: assignError,
    assign: assignEvaluator,
  };
  const rescheduleResolver: RescheduleResolver = {
    resolvingId: resolvingRequestId,
    error: resolveError,
    resolve: resolveReschedule,
  };
  const slotSender: SlotSender = {
    editingStage: slotStage,
    open: openSlotSender,
    close: () => setSlotStage(null),
    ticked: slotTicked,
    toggle: (key) => setSlotTicked((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key])),
    mode: slotMode,
    setMode: setSlotMode,
    location: slotLocation,
    setLocation: setSlotLocation,
    meetingLink: slotLink,
    setMeetingLink: setSlotLink,
    sending: slotSending,
    error: slotError,
    send: sendSlots,
  };
  // Every route back to the pipeline from this page — the breadcrumb, the
  // job title — goes to the opening this candidate is actually in.
  const pipelineHref = profile ? `/hr/pipelines?job=${profile.requisition_id}` : "/hr/pipelines";

  // Everyone in this candidate's opening, in the Pipelines List order, so
  // HR reviewing a field can step through it from here instead of going
  // back to the list between every candidate. Fetched once per opening;
  // the list itself is the same one the Pipelines page reads.
  const [siblings, setSiblings] = useState<ApplicationListItem[]>([]);
  const [job, setJob] = useState<RequisitionDetail | null>(null);
  const requisitionId = profile?.requisition_id;
  // The job itself, for the stage bar (its own workflow and stage names)
  // and its department. Once per opening, like the list above.
  useEffect(() => {
    if (requisitionId == null) return;
    apiFetch<RequisitionDetail>(`/hr/requisitions/${requisitionId}`, { token })
      .then(setJob)
      .catch(() => setJob(null));
  }, [requisitionId, token]);
  useEffect(() => {
    if (requisitionId == null) return;
    apiFetch<ApplicationListItem[]>("/hr/applications", { token })
      .then((rows) => setSiblings(rows.filter((r) => r.requisition_id === requisitionId).sort(byMatchScore)))
      .catch(() => setSiblings([]));
  }, [requisitionId, token]);

  const position = useMemo(() => siblings.findIndex((s) => s.id === Number(id)), [siblings, id]);
  const previous = position > 0 ? siblings[position - 1] : null;
  const next = position >= 0 && position < siblings.length - 1 ? siblings[position + 1] : null;

  function goTo(candidate: ApplicationListItem) {
    // The open tab comes along: reviewing everyone's interviews, say,
    // should not snap back to Synthesis on every step.
    const query = searchParams.toString();
    navigate(`/hr/applications/${candidate.id}${query ? `?${query}` : ""}`);
  }

  // Which of the resume read's lists the Synthesis tab shows. Held here,
  // not in the panel, so the verdict's "unaddressed requirements" link can
  // open the gaps directly.
  const [evidenceView, setEvidenceView] = useState<EvidenceView>("evidenced");

  // A link to another tab (from a verdict fact or an evidence figure)
  // switches the tab, then — once it has rendered — brings its section
  // into view. On a narrow screen the rail stacks above the tabs, and from
  // low on the Synthesis tab the tab bar is off-screen; either way the tab
  // would otherwise change out of sight.
  const [scrollTarget, setScrollTarget] = useState<{ anchor: string; block: ScrollLogicalPosition } | null>(null);
  function openTab(next: Tab, anchor = TABLIST_ID, block: ScrollLogicalPosition = "nearest") {
    setTab(next);
    setScrollTarget({ anchor, block });
  }
  function openSignal(key: HeadlineSignal["key"]) {
    if (key === "requirement_gaps") setEvidenceView("gaps");
    const { tab: target, anchor, block } = SIGNAL_TARGET[key];
    openTab(target, anchor, block);
  }
  useEffect(() => {
    if (!scrollTarget) return;
    document.getElementById(scrollTarget.anchor)?.scrollIntoView({ behavior: "smooth", block: scrollTarget.block });
    setScrollTarget(null);
  }, [scrollTarget]);

  // J / K, as in a mail client — the step without reaching for the mouse.
  // Never while typing, and never under an open dialog or editor, where a
  // letter is input rather than a command.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey || userIsEditing) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
      if (document.querySelector("[role='dialog']")) return;
      const key = event.key.toLowerCase();
      if (key === "j" && next) goTo(next);
      if (key === "k" && previous) goTo(previous);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  /** A small count beside a tab, where there is one worth knowing before
   *  opening it — how much of it is done, or how much is in it. */
  function tabCount(t: Tab): string | null {
    if (!profile) return null;
    switch (t) {
      case "pre-screening":
        return profile.pre_screening_qa.length > 0 ? String(profile.pre_screening_qa.length) : null;
      case "examinations":
        return examStageKeys.length > 0 ? `${scoredExams.length}/${examStageKeys.length}` : null;
      case "interviews": {
        if (interviewRatings.length === 0) return null;
        const done = interviewRatings.filter((s) => profile.interview_ratings[s].computed_score != null).length;
        return `${done}/${interviewRatings.length}`;
      }
      case "documents": {
        const n = (profile.resume ? 1 : 0) + profile.documents.length;
        return n > 0 ? String(n) : null;
      }
      default:
        return null;
    }
  }

  return (
    <AppShell>
      <PageHeader
        above={
          // Back to *this candidate's* pipeline, not to whichever one the
          // Pipelines page would have picked for itself.
          <Link to={pipelineHref} className="ark-back">
            &larr; {profile ? `${profile.job_title} · HR Workflow` : "HR Workflow"}
          </Link>
        }
        title="Candidate Profile"
        actions={
          position >= 0 &&
          siblings.length > 1 && (
            <CandidateStepper position={position} siblings={siblings} previous={previous} next={next} goTo={goTo} />
          )
        }
      />

      {loading && !profile && <p style={{ fontFamily: "var(--arkive-font)", color: "var(--ink-600)" }}>Loading...</p>}
      {error && <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {profile && (
        <div className="ark-profile">
          <CandidateSidebar
            profile={profile}
            job={job}
            pipelineHref={pipelineHref}
            updating={updating}
            advancing={advancing}
            advanceError={advanceError}
            actionError={actionError}
            onAdvance={advanceStage}
            onDecide={openDecisionDialog}
            onResolveFlag={(decision) => setConfirmingAction(decision === "continue" ? "continue" : "reject_flagged")}
            onReopen={() => setConfirmingAction("reopen")}
            onOpenPackage={() => navigate(`/hr/applications/${id}/pre-201-package`)}
            onOpenSignal={openSignal}
          />

          <div className="ark-profile__main">
            <ProfileTabs tab={tab} setTab={setTab} tabCount={tabCount} />

            <div role="tabpanel" id="candidate-tabpanel" aria-labelledby={`tab-${tab}`}>
              {tab === "synthesis" && (
                <SynthesisTab
                  profile={profile}
                  evidenceView={evidenceView}
                  onEvidenceViewChange={setEvidenceView}
                  onOpenSource={(source) => openTab(source)}
                />
              )}

              {tab === "pre-screening" && <PreScreeningTab profile={profile} />}

              {tab === "shortlisting" && <ShortlistingTab profile={profile} shortlistingStageKeys={shortlistingStageKeys} editor={shortlistingEditor} />}

              {tab === "examinations" && (
                <ExaminationsTab
                  profile={profile}
                  job={job}
                  token={token}
                  examStageKeys={examStageKeys}
                  scoreEditor={scoreEditor}
                  bookingResolver={bookingResolver}
                  onProfile={setProfile}
                  onReload={() => load()}
                />
              )}

              {tab === "interviews" && <InterviewsTab profile={profile} interviewRatings={interviewRatings} scheduleEditor={scheduleEditor} assignment={evaluatorAssignment} reschedule={rescheduleResolver} slotSender={slotSender} />}

              {tab === "documents" && <DocumentsTab profile={profile} applicationId={id} token={token} />}
            </div>

            {/* Who decided, when and why — for a closed application, on
                every tab. Null for applications closed before decisions
                were recorded. */}
            {profile.status !== "active" && profile.status !== "flagged" && profile.decision && (
              <DecisionRecordPanel decision={profile.decision} />
            )}
          </div>

        </div>
      )}

      {profile && (
        <AdvanceDialog
          open={transition.confirming !== null}
          candidateName={profile.applicant_name}
          fromStageLabel={profile.current_stage_label ?? stageLabel(profile.current_stage)}
          targetStageLabel={
            transition.confirming ? profile.next_stage_label ?? stageLabel(transition.confirming.target) : ""
          }
          onConfirm={() => {
            const pending = transition.takeConfirming();
            if (pending) void requestAdvance(pending.target);
          }}
          onCancel={transition.cancelConfirming}
        />
      )}

      {profile && (
        <StatusActionDialog
          confirmingAction={confirmingAction}
          profile={profile}
          onConfirm={() => {
            const action = confirmingAction;
            setConfirmingAction(null);
            if (action === "reopen") void setStatus("active");
            else if (action === "continue") void resolveFlag("continue");
            else if (action === "reject_flagged") void resolveFlag("reject");
          }}
          onCancel={() => setConfirmingAction(null)}
        />
      )}

      {profile && (
        <StageAdvanceDialog
          open={transition.pendingSkip !== null}
          candidateName={profile.applicant_name}
          targetStageLabel={
            transition.pendingSkip ? profile.next_stage_label ?? stageLabel(transition.pendingSkip.target) : ""
          }
          blockers={transition.pendingSkip?.blockers ?? []}
          message={transition.pendingSkip?.message ?? null}
          submitting={transition.skipSubmitting}
          error={transition.skipError}
          onConfirm={transition.confirmSkip}
          onCancel={transition.cancelSkip}
        />
      )}

      {profile && (
        <DecisionDialog
          open={decisionMode !== null}
          mode={decisionMode ?? "hire"}
          applicantName={profile.applicant_name}
          blockers={decisionBlockers}
          message={decisionMessage}
          submitting={updating}
          error={decisionError}
          onConfirm={(reason, acknowledged) =>
            setStatus(decisionMode === "hire" ? "hired" : "rejected", { reason, acknowledged })
          }
          onCancel={closeDecisionDialog}
        />
      )}
    </AppShell>
  );
}
