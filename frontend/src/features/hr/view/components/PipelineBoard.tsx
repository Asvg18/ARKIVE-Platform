/**
 * One job's pipeline as a column per stage, with candidates as cards HR
 * drags between them.
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { ApplicationListItem, StageType } from "../../../../shared/api/pipeline";
import { STATUS_LABELS } from "../../../../shared/lib/stageLabels";
import { Tag } from "../../../../shared/ui/Tag";
import { applicationStatusTone } from "../../../../shared/lib/statusTags";
import { Avatar } from "../../../../shared/ui/Avatar";

export interface BoardStage {
  stage_type: StageType;
  label: string;
}

/** A candidate on a closed application is shown where they stopped, but
 * cannot be dragged — there is no transition to request. */
function isMovable(application: ApplicationListItem): boolean {
  return application.status === "active" || application.status === "flagged";
}

function CandidateCard({
  application,
  dragging,
  onDragStart,
  onDragEnd,
  onOpen,
}: {
  application: ApplicationListItem;
  dragging: boolean;
  onDragStart: () => void;
  onDragEnd: () => void;
  onOpen: () => void;
}) {
  const movable = isMovable(application);
  return (
    <div
      draggable={movable}
      onDragStart={(e) => {
        // The id travels in the drag payload as well as in component
        // state — state alone is enough here, but a drag that carries no
        // data is rejected outright by some browsers.
        e.dataTransfer.setData("text/plain", String(application.id));
        e.dataTransfer.effectAllowed = "move";
        onDragStart();
      }}
      onDragEnd={onDragEnd}
      onClick={onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      className={[
        "ark-card-candidate",
        movable ? "ark-card-candidate--draggable" : "",
        dragging ? "ark-card-candidate--dragging" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 9, minWidth: 0 }}>
        <Avatar name={application.applicant_name} size={26} src={application.applicant_avatar_url} />
        <div
          className="ark-truncate"
          style={{
            fontSize: "var(--text-sm)",
            fontWeight: 600,
            letterSpacing: "var(--track-snug)",
            color: "var(--ink-900)",
          }}
        >
          {application.applicant_name}
        </div>
      </div>
      {/* No AI-match % on the card: it crowded the card and read as a
          verdict on the applicant when it is only one input. It is on the
          candidate profile, where the decision is made. Only a non-active
          status badge shows here. */}
      {application.status !== "active" && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
          <Tag tone={applicationStatusTone(application.status)} dot>
            {STATUS_LABELS[application.status] ?? application.status}
          </Tag>
        </div>
      )}
    </div>
  );
}

/** A board shows where everyone is at a glance, which a table cannot. It
 * is also where the workflow automaton is visible: dragging a card
 * requests a transition, the server checks it against the job's own
 * workflow (the DFA allows exactly one next stage), and a drop two
 * columns ahead is refused on screen with the reason, in the job's own
 * stage names.
 *
 * Scoped to one job on purpose: workflows differ in length (Software
 * Engineer I has ten stages, Library Assistant six), so a board across
 * jobs would have no shared columns. */
export function PipelineBoard({
  stages,
  applications,
  onMove,
  moveError,
  onDismissError,
  movingId,
  onDragActiveChange,
}: {
  stages: BoardStage[];
  applications: ApplicationListItem[];
  /** Requests the transition. The parent owns the API call so the board
   * stays a rendering concern. */
  onMove: (application: ApplicationListItem, target: StageType) => void;
  /** The server's rejection, shown against the column it was dropped on
   * — the refusal belongs where the attempt happened, not in a banner at
   * the top of the page. */
  moveError: { stage: StageType; message: string } | null;
  onDismissError: () => void;
  movingId: number | null;
  /** Fires as a drag starts and again as it ends, so the parent can
   * pause its background refresh for the duration. A poll landing
   * mid-drag re-renders the cards underneath the cursor and the browser
   * abandons the drag — the drop never arrives. */
  onDragActiveChange?: (active: boolean) => void;
}) {
  const navigate = useNavigate();
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [overStage, setOverStage] = useState<StageType | null>(null);

  // Derived from the state rather than called inside the handlers, so
  // every path that clears `draggingId` — dragend, a drop, a card
  // unmounting mid-drag — resumes the parent's polling. A handler-only
  // notification can be skipped on one of those paths and leave the
  // pipeline frozen for the rest of the session.
  const dragActive = draggingId !== null;
  useEffect(() => {
    onDragActiveChange?.(dragActive);
  }, [dragActive, onDragActiveChange]);

  /**
   * Brings a refused column into view.
   *
   * The board scrolls horizontally — ten stages do not fit — so a
   * rejection can land on a column that is off-screen by the time it
   * renders, and the refusal is the whole point of the interaction. A
   * callback ref rather than an effect: it fires exactly when the node
   * carrying the error mounts, with no dependency list to keep in sync.
   */
  const revealError = useCallback((node: HTMLDivElement | null) => {
    node?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
  }, []);

  const dragged = applications.find((a) => a.id === draggingId) ?? null;

  const byStage = (stage: StageType) =>
    applications.filter((a) => a.current_stage === stage);

  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        overflowX: "auto",
        // Room for the cards' hover lift and shadow, which the old
        // 8px bottom clipped.
        padding: "2px 2px 12px",
        alignItems: "flex-start",
      }}
    >
      {stages.map((stage, index) => {
        const cards = byStage(stage.stage_type);
        // A closed candidate is shown where they stopped, but they are
        // not *at* that stage — a rejected applicant sitting in the
        // AI Pre-Screening column made it read "1" when nobody was
        // waiting there. The number is the queue; the closed cards below
        // it are history, and are counted separately.
        const waiting = cards.filter(isMovable).length;
        const closed = cards.length - waiting;
        const isOver = overStage === stage.stage_type;
        // The DFA allows exactly one next stage from wherever the dragged
        // card currently sits. Highlighting it while dragging turns the
        // rule into something you can see before you act, rather than
        // only discovering it by being refused.
        const isLegalTarget = dragged != null && dragged.next_stage === stage.stage_type;
        const isOwnColumn = dragged != null && dragged.current_stage === stage.stage_type;
        const errorHere = moveError?.stage === stage.stage_type ? moveError.message : null;

        return (
          <div
            key={stage.stage_type}
            onDragOver={(e) => {
              // preventDefault unconditionally: a column that only opts
              // in once React state has caught up would reject the first
              // frames of every drag.
              e.preventDefault();
              e.dataTransfer.dropEffect = "move";
              setOverStage(stage.stage_type);
            }}
            onDragLeave={() => setOverStage((s) => (s === stage.stage_type ? null : s))}
            onDrop={(e) => {
              e.preventDefault();
              setOverStage(null);
              // The dropped card is identified from the drag payload
              // first and from React state only as a fallback. State is
              // set in onDragStart, and a drop that arrives before that
              // render commits would otherwise find nothing to move —
              // which is exactly what happens under synthetic events, and
              // is a race a fast real drag could lose too. The payload is
              // the platform's own answer to "what is being dragged".
              const carried = Number(e.dataTransfer.getData("text/plain"));
              const moving =
                applications.find((a) => a.id === carried) ?? dragged;
              // The drag is over the moment it lands, whatever happens
              // next. Waiting for dragend would hold the parent's
              // refresh paused across the whole transition request.
              setDraggingId(null);
              if (!moving || !isMovable(moving)) return;
              if (moving.current_stage === stage.stage_type) return;
              onMove(moving, stage.stage_type);
            }}
            className={[
              "ark-col",
              isLegalTarget && !isOwnColumn ? "ark-col--target" : "",
              isOver ? "ark-col--over" : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            <div className="ark-col__head">
              {/* The stage's position in this job's workflow. The board is
                  the one screen where the generated automaton is visible,
                  and a bare list of names does not say "these run in this
                  order" — a number does, and it survives the columns
                  being scrolled out of view. */}
              <span style={{ display: "flex", alignItems: "center", gap: 7, minWidth: 0 }}>
                <span
                  className="ark-num"
                  aria-hidden="true"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: 17,
                    height: 17,
                    flexShrink: 0,
                    borderRadius: "var(--radius-xs)",
                    background: "var(--surface)",
                    border: "1px solid var(--surface-border)",
                    fontSize: "var(--text-2xs)",
                    fontWeight: 700,
                    color: "var(--ink-400)",
                  }}
                >
                  {index + 1}
                </span>
                <span
                  className="ark-meta ark-truncate"
                  style={{ color: "var(--ink-700)" }}
                  title={stage.label}
                >
                  {stage.label}
                </span>
              </span>
              <span
                className="ark-num"
                style={{
                  fontSize: "var(--text-xs)",
                  fontWeight: 650,
                  color: waiting > 0 ? "var(--ink-700)" : "var(--ink-300)",
                  whiteSpace: "nowrap",
                }}
              >
                {waiting}
                {closed > 0 && (
                  <span
                    style={{ color: "var(--ink-300)", fontWeight: 500 }}
                    title={`${closed} closed application${closed === 1 ? "" : "s"} stopped here`}
                  >
                    {" +"}{closed}
                  </span>
                )}
              </span>
            </div>

            {isLegalTarget && !isOwnColumn && (
              <div
                className="ark-meta"
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  color: "var(--success-text)",
                  letterSpacing: "var(--track-wide)",
                }}
              >
                <span className="ark-dot" />
                Drop to advance
              </div>
            )}

            {errorHere && (
              <div
                ref={revealError}
                onClick={onDismissError}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && onDismissError()}
                style={{
                  fontSize: "var(--text-xs)",
                  lineHeight: 1.5,
                  color: "var(--danger-text)",
                  background: "var(--danger-bg)",
                  border: "1px solid rgba(180, 35, 24, 0.22)",
                  borderRadius: "var(--radius-sm)",
                  padding: "8px 10px",
                  cursor: "pointer",
                }}
              >
                {errorHere}
              </div>
            )}

            {cards.map((application) => (
              <div key={application.id} style={{ opacity: movingId === application.id ? 0.5 : 1 }}>
                <CandidateCard
                  application={application}
                  dragging={draggingId === application.id}
                  onDragStart={() => setDraggingId(application.id)}
                  onDragEnd={() => {
                    setDraggingId(null);
                    setOverStage(null);
                  }}
                  onOpen={() => navigate(`/hr/applications/${application.id}`)}
                />
              </div>
            ))}

            {/* A dashed well rather than the bare sentence that was here.
                An empty column still has to hold its shape — a board with
                three empty stages otherwise collapses into ragged strips
                of different heights — and a dashed outline says "this can
                receive something", which is the fact that matters mid-drag. */}
            {cards.length === 0 && <div className="ark-col__empty">Nobody at this stage</div>}
          </div>
        );
      })}
    </div>
  );
}
