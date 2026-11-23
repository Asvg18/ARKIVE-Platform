import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { EvaluateRequestBody, InterviewDetail } from "../../../../shared/api/evaluator";
import { AvailabilityPanel } from "../components/AvailabilityPanel";
import { EvaluatorAppShell } from "../components/EvaluatorAppShell";
import { Alert } from "../../../../shared/ui/Alert";
import { ErrorState } from "../../../../shared/ui/ErrorState";
import { CalendarIcon, CheckIcon } from "../../../../shared/ui/icons";
import {
  RECOMMENDATION_OPTIONS,
  SCORECARD_CATEGORIES,
  SCORECARD_ITEM_CODES,
} from "../../../../shared/lib/scorecard";
import type { EvaluatorRecommendation } from "../../../../shared/lib/scorecard";
import {
  RATING_WORD,
  RECOMMENDATION_ICON,
  emptyItemRatings,
  scrollBehavior,
  useElapsedSeconds,
  type ItemRatingsState,
} from "./interview-detail/interviewFormat";
import { CandidatePanel, InterviewHero } from "./interview-detail/InterviewHero";
import { ResultPanel, SubmittedRecord } from "./interview-detail/ResultPanel";
import { RatingScale, ScaleKey, ScalePanel } from "./interview-detail/RatingScale";
import { SchedulePanel } from "./interview-detail/SchedulePanel";
import { ProgressPanel } from "./interview-detail/ProgressPanel";

/** One interview round, for the evaluator who runs it.
 *
 * Laid out like the applicant's application page: a dark banner saying
 * who and for what, then the work on the left and a rail on the right,
 * so the form starts above the fold rather than below a stack of
 * candidate details.
 *
 * The rail holds what an evaluator needs *while* rating: how much is
 * left (each line of the checklist jumps to it) with Submit always in
 * reach, the rating scale's words, and the interview's time, place and
 * resume. It stays in view as the form scrolls. */
export function InterviewDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const [interview, setInterview] = useState<InterviewDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [itemRatings, setItemRatings] = useState<ItemRatingsState>(emptyItemRatings());
  const [remarks, setRemarks] = useState("");
  const [recommendation, setRecommendation] = useState<EvaluatorRecommendation | null>(null);
  const [draftSavedAt, setDraftSavedAt] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const remarksRef = useRef<HTMLTextAreaElement>(null);

  // The candidate hasn't reached this round yet: it was assigned (and
  // announced by a notification) ahead of time. Nothing to evaluate, so
  // the form is withheld and the review timer does not run.
  const upcoming = interview?.status === "pending" && !interview.evaluation;
  // The candidate is on this round but hasn't confirmed a time: the form
  // is shown, disabled, and the
  // server refuses a scorecard until they do.
  const waiting = !!interview && !interview.evaluation && !upcoming && !interview.schedule_confirmed;
  const open = !!interview && !interview.evaluation && !upcoming && !waiting;
  const elapsed = useElapsedSeconds(open);

  useEffect(() => {
    setLoading(true);
    setError(null);
    apiFetch<InterviewDetail>(`/evaluator/interviews/${id}`, { token })
      .then(setInterview)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load."))
      .finally(() => setLoading(false));
  }, [id, token, reloadKey]);

  /**
   * Keep an unsubmitted scorecard on this device.
   *
   * The form is eleven required ratings, a recommendation and free-text
   * remarks — a couple of thousand pixels of work that an evaluator fills
   * in during or just after an interview. Losing it to a closed tab, a
   * flat battery or an expired session means asking someone to reconstruct
   * a judgement from memory, which is worse than losing typing: the second
   * attempt is not the same evaluation.
   *
   * Deliberately localStorage rather than a server draft. A server draft
   * means a new endpoint, a place to store partial evaluations, and a
   * question about who may read a half-formed opinion about a candidate.
   * This keeps it on the machine of the person writing it until they
   * choose to submit.
   */
  const draftKey = id ? `arkive_eval_draft_${id}` : null;

  useEffect(() => {
    if (!draftKey || interview?.evaluation) return;
    try {
      const raw = localStorage.getItem(draftKey);
      if (!raw) return;
      const saved = JSON.parse(raw);
      // A draft saved while N/A still existed may hold null for an item;
      // drop those so the item shows as unanswered and gets a real rating.
      if (saved.itemRatings) {
        const ratings: ItemRatingsState = {};
        for (const [code, rating] of Object.entries(saved.itemRatings)) {
          if (typeof rating === "number") ratings[code] = rating;
        }
        setItemRatings(ratings);
      }
      if (saved.remarks) setRemarks(saved.remarks);
      if (saved.recommendation) setRecommendation(saved.recommendation);
      if (saved.at) setDraftSavedAt(new Date(saved.at).toLocaleTimeString());
    } catch {
      // A corrupt or unreadable draft must never block the form itself.
    }
    // Restores once, when the interview loads and proves to be unsubmitted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftKey, interview?.evaluation]);

  useEffect(() => {
    if (!draftKey || interview?.evaluation) return;
    const touched =
      remarks.trim() !== "" ||
      recommendation !== null ||
      SCORECARD_ITEM_CODES.some((code) => itemRatings[code] !== undefined);
    if (!touched) return;
    const at = Date.now();
    try {
      localStorage.setItem(draftKey, JSON.stringify({ itemRatings, remarks, recommendation, at }));
      setDraftSavedAt(new Date(at).toLocaleTimeString());
    } catch {
      // Private browsing or a full quota — the form still works, it just
      // stops being recoverable. Not worth interrupting anyone over.
    }
  }, [draftKey, interview?.evaluation, itemRatings, remarks, recommendation]);

  const allItemsAnswered = SCORECARD_ITEM_CODES.every((code) => itemRatings[code] !== undefined);
  const ratedCount = SCORECARD_ITEM_CODES.filter((code) => itemRatings[code] !== undefined).length;
  const ready = allItemsAnswered && recommendation !== null && remarks.trim() !== "";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!allItemsAnswered || recommendation === null) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const body: EvaluateRequestBody = {
        item_ratings: itemRatings as Record<string, number>,
        remarks,
        recommendation,
      };
      const updated = await apiFetch<InterviewDetail>(`/evaluator/interviews/${id}/evaluate`, {
        method: "POST",
        token,
        body,
      });
      setInterview(updated);
      // The evaluation is now on the server and locked, so the local copy
      // has nothing left to protect — and leaving it would resurface a
      // stale draft over a submitted scorecard on the next visit.
      if (draftKey) {
        try { localStorage.removeItem(draftKey); } catch { /* nothing to clean up */ }
      }
      setDraftSavedAt(null);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Could not submit evaluation.");
    } finally {
      setSubmitting(false);
    }
  }

  /** The checklist's "Rate every item" takes you to the first item still
   * blank, rather than to the top of eleven rows to hunt for it. Focus
   * goes first (without scrolling), so it can't cut the scroll short. */
  function goToNextUnrated() {
    const code = SCORECARD_ITEM_CODES.find((c) => itemRatings[c] === undefined);
    const row = code ? document.getElementById(`rate-${code}`) : document.getElementById("eval-ratings");
    row?.querySelector<HTMLButtonElement>('[role="radio"][tabindex="0"]')?.focus({ preventScroll: true });
    row?.scrollIntoView({ behavior: scrollBehavior(), block: code ? "center" : "start" });
  }

  function goTo(sectionId: string) {
    document.getElementById(sectionId)?.scrollIntoView({ behavior: scrollBehavior(), block: "start" });
  }

  function goToRemarks() {
    remarksRef.current?.focus({ preventScroll: true });
    remarksRef.current?.scrollIntoView({ behavior: scrollBehavior(), block: "center" });
  }

  return (
    <EvaluatorAppShell>
      <div style={{ marginBottom: 12 }}>
        <Link to="/evaluator" className="ark-back">
          &larr; Review Queue
        </Link>
      </div>

      {loading && !interview && (
        <div aria-busy="true" aria-label="Loading the interview">
          <div className="ark-skeleton" style={{ height: 118, borderRadius: "var(--radius-xl)", marginBottom: 20 }} />
          <div className="ark-eval">
            <div className="ark-skeleton" style={{ height: 520, borderRadius: "var(--radius-lg)" }} />
            <div className="ark-skeleton" style={{ height: 280, borderRadius: "var(--radius-lg)" }} />
          </div>
        </div>
      )}
      {error && <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {interview && (
        <>
          <InterviewHero interview={interview} upcoming={upcoming} waiting={waiting} open={open} elapsed={elapsed} />

          <div className="ark-eval">
            <div className="ark-eval__main">
              {/* Free times for HR to send the applicant, until a time is
                  booked. */}
              {!interview.evaluation && !interview.schedule && (
                <AvailabilityPanel interview={interview} token={token} onUpdate={setInterview} />
              )}
              {waiting && (
                <Alert tone="warning" title="Waiting for schedule">
                  The form opens once {interview.applicant_name} has confirmed the interview time.
                  {interview.times_sent
                    ? " HR has sent your free times, and they're picking one."
                    : interview.schedule
                      ? " HR has set a time and asked them to confirm it."
                      : " Add your free times above so HR can send them."}
                </Alert>
              )}
              {upcoming ? (
                /* No form for a round the candidate hasn't reached — there
                   is nothing to record, and the server refuses a scorecard
                   on a pending stage anyway (evaluator.py). This is the
                   landing state when an evaluator follows the "you've been
                   assigned" notification early. */
                <section className="ark-panel">
                  <div className="ark-empty ark-empty--wide">
                    <span className="ark-empty__mark" aria-hidden="true">
                      <CalendarIcon width={20} height={20} />
                    </span>
                    <span className="ark-empty__title">Not open for evaluation yet</span>
                    <p className="ark-empty__body">
                      {interview.applicant_name} hasn't reached {interview.stage_label} yet. You've been assigned to
                      conduct it, and the form opens here once they advance to this round. It will move
                      to <strong>Awaiting your evaluation</strong> in your Review Queue then.
                    </p>
                  </div>
                </section>
              ) : interview.evaluation ? (
                <SubmittedRecord evaluation={interview.evaluation} />
              ) : (
                /* Shown but out of reach while waiting for a confirmed
                   time: `inert` takes the whole form out of clicking and
                   typing, and the notice above says why. */
                <form
                  id="evaluation-form"
                  onSubmit={handleSubmit}
                  className="ark-eval__form"
                  inert={waiting || undefined}
                  data-waiting={waiting || undefined}
                >
                  <section id="eval-ratings" className="ark-panel" aria-labelledby="eval-ratings-title">
                    <div className="ark-panel__head">
                      <div>
                        <h2 id="eval-ratings-title" className="ark-panel__title">Ratings</h2>
                        <p className="ark-panel__sub">Applicant Preliminary Interview Evaluation Form · HRD-F-APIEF</p>
                      </div>
                      <span className="ark-panel__count">
                        {ratedCount} of {SCORECARD_ITEM_CODES.length} rated
                      </span>
                    </div>

                    <div className="ark-panel__body">
                      {/* Stands in for the rail's scale card when the rail has
                          dropped below the form on a narrower window. */}
                      <div className="ark-eval__inline-key">
                        <ScaleKey compact />
                      </div>

                      <div className="ark-rubric">
                        {SCORECARD_CATEGORIES.map((category) => {
                          const answered = category.items.filter((item) => itemRatings[item.code] !== undefined).length;
                          const complete = answered === category.items.length;
                          return (
                            <section key={category.code} className="ark-rubric__area" aria-label={category.label}>
                              <header className="ark-rubric__head">
                                <span className="ark-rubric__code" aria-hidden="true">
                                  {category.code}
                                </span>
                                <span className="ark-rubric__title">{category.label}</span>
                                <span className="ark-rate-area__count" data-complete={complete || undefined}>
                                  {complete && <CheckIcon width={12} height={12} aria-hidden="true" />}
                                  {answered} of {category.items.length}
                                </span>
                              </header>
                              <ul className="ark-rate-items">
                                {category.items.map((item) => {
                                  const value = itemRatings[item.code];
                                  return (
                                    <li key={item.code} id={`rate-${item.code}`} className="ark-rate-item">
                                      {/* The chosen answer in the form's own words, under
                                          the question. Its line is held open before an
                                          answer too, so answering never pushes the rows
                                          below it down. */}
                                      <div className="ark-rate-item__text">
                                        <span id={`rate-${item.code}-label`} className="ark-rate-item__label">
                                          {item.label}
                                        </span>
                                        <span className="ark-rate-item__word" aria-hidden="true">
                                          {value === undefined ? "" : RATING_WORD[value]}
                                        </span>
                                      </div>
                                      <RatingScale
                                        value={value}
                                        labelledBy={`rate-${item.code}-label`}
                                        onChange={(next) => setItemRatings((prev) => ({ ...prev, [item.code]: next }))}
                                      />
                                    </li>
                                  );
                                })}
                              </ul>
                            </section>
                          );
                        })}
                      </div>
                    </div>
                  </section>

                  <section id="eval-recommendation" className="ark-panel" aria-labelledby="eval-recommendation-title">
                    <div className="ark-panel__head">
                      <div>
                        <h2 id="eval-recommendation-title" className="ark-panel__title">Overall recommendation</h2>
                        <p className="ark-panel__sub">
                          Your own call, recorded beside the score your ratings compute, and the two may differ.
                        </p>
                      </div>
                    </div>
                    <div className="ark-panel__body">
                      <div className="ark-choices ark-choices--3" role="radiogroup" aria-labelledby="eval-recommendation-title">
                        {RECOMMENDATION_OPTIONS.map((option) => {
                          const selected = recommendation === option.value;
                          const Icon = RECOMMENDATION_ICON[option.value];
                          return (
                            <button
                              key={option.value}
                              type="button"
                              role="radio"
                              aria-checked={selected}
                              className="ark-choice ark-choice--tile"
                              onClick={() => setRecommendation(option.value)}
                            >
                              <span className="ark-choice__top">
                                <span className="ark-choice__icon" aria-hidden="true">
                                  <Icon width={18} height={18} />
                                </span>
                                <span className="ark-choice__radio" aria-hidden="true" />
                              </span>
                              <span className="ark-choice__text">
                                <span className="ark-choice__title">{option.label}</span>
                                <span className="ark-choice__desc">{option.hint}</span>
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </section>

                  <section id="eval-remarks" className="ark-panel" aria-labelledby="eval-remarks-title">
                    <div className="ark-panel__head">
                      <div>
                        <h2 id="eval-remarks-title" className="ark-panel__title">Remarks</h2>
                        <p className="ark-panel__sub">What stood out: the candidate's strengths, and where they would need support.</p>
                      </div>
                    </div>
                    <div className="ark-panel__body">
                      <textarea
                        ref={remarksRef}
                        required
                        aria-labelledby="eval-remarks-title"
                        className="ark-input"
                        value={remarks}
                        onChange={(e) => setRemarks(e.target.value)}
                        rows={7}
                        placeholder="Detail the candidate's strengths and potential areas for development..."
                      />
                    </div>
                  </section>
                </form>
              )}
            </div>

            <aside className="ark-eval__rail" aria-label="Evaluation progress and interview details">
              {interview.evaluation && <ResultPanel evaluation={interview.evaluation} />}
              <SchedulePanel interview={interview} canReschedule={open || waiting} token={token} onUpdate={setInterview} />
              <CandidatePanel interview={interview} token={token} />
              {/* Last, so it is the part that stays: the cards above scroll
                  away with the page and this one pins to the top of the
                  window for the length of the form. */}
              {open && (
                <div className="ark-eval__sticky">
                  <ProgressPanel
                    itemRatings={itemRatings}
                    ratedCount={ratedCount}
                    recommendation={recommendation}
                    remarksWritten={remarks.trim() !== ""}
                    ready={ready}
                    submitting={submitting}
                    submitError={submitError}
                    draftSavedAt={draftSavedAt}
                    onRatings={goToNextUnrated}
                    onRecommendation={() => goTo("eval-recommendation")}
                    onRemarks={goToRemarks}
                  />
                  <ScalePanel />
                </div>
              )}
            </aside>
          </div>
        </>
      )}
    </EvaluatorAppShell>
  );
}
