import { useMemo, useState } from "react";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { ApplicationListItem, ShortlistResult } from "../../../../shared/api/pipeline";
import { Button } from "../../../../shared/ui/Button";
import { Card } from "../../../../shared/ui/Card";
import { AlertIcon } from "../../../../shared/ui/icons";

/** HR's shortlist for one job, and the two letters that go with it.
 *
 * The decision this replaces was the same one typed out N times: open a
 * profile, mark shortlisted or not, repeat, and hope everyone who missed
 * out eventually heard something. Doing it for the whole field at once is
 * what makes the second half — writing to the people who did not make it
 * — something that actually happens.
 *
 * **HR picks. The system does not.** This was a cutoff once ("the top N
 * by match score"), which quietly made the model the decision-maker and
 * HR the person choosing how far down to trust it. The score reads a
 * resume against a job description; it cannot see the things that decide
 * a shortlist. So the list is *sorted* by score, because that is useful
 * guidance, and nothing starts selected.
 *
 * **The counts move as you pick**, on the group headers and on both
 * message labels, so "who am I writing this to" is answered while you
 * write it rather than after you send.
 *
 * **Already-decided candidates are shown and held back.** Recording an
 * outcome does not advance the stage, so someone HR has already marked
 * sits in the same pool as someone nobody has looked at. Including them
 * would overwrite a call made by hand — and mail them a letter
 * contradicting it.
 *
 * The letters have no default text. A message about someone's
 * application is the university speaking to a person, and a prefilled
 * template is the thing most likely to go out unread and unchanged. */
export function ShortlistDialog({
  requisitionId,
  jobTitle,
  candidates,
  token,
  onClose,
  onDone,
}: {
  requisitionId: number;
  jobTitle: string;
  /** Everyone in this job currently sitting on the shortlisting stage. */
  candidates: ApplicationListItem[];
  token: string | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [shortlistedLetter, setShortlistedLetter] = useState("");
  const [notShortlistedLetter, setNotShortlistedLetter] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ShortlistResult | null>(null);

  /** The candidates still waiting on a call, and the ones already
   *  settled.
   *
   *  A decision recorded on a candidate's own profile is final here:
   *  they leave the list rather than being re-decided in bulk. Sorted by
   *  match score as guidance; an unscored candidate sorts last but is
   *  still choosable, since without a cutoff there is no ranking for
   *  them to be missing from. */
  const { pool, decided } = useMemo(() => {
    const undecided = candidates.filter((c) => !c.shortlisting_outcome);
    undecided.sort((a, b) => {
      if (a.match_score == null && b.match_score == null) return a.id - b.id;
      if (a.match_score == null) return 1;
      if (b.match_score == null) return -1;
      return b.match_score - a.match_score || a.id - b.id;
    });
    return { pool: undecided, decided: candidates.filter((c) => c.shortlisting_outcome) };
  }, [candidates]);

  const chosen = pool.filter((c) => picked.has(c.id));
  const rejected = pool.filter((c) => !picked.has(c.id));

  // Each letter is only demanded when it has somebody to go to --
  // requiring a "you did not make it" note when everybody made it is
  // busywork that teaches people to type a placeholder.
  const needsShortlistedLetter = chosen.length > 0 && shortlistedLetter.trim() === "";
  const needsRejectedLetter = rejected.length > 0 && notShortlistedLetter.trim() === "";
  const canSend = !submitting && pool.length > 0 && !needsShortlistedLetter && !needsRejectedLetter;

  function toggle(id: number) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function send() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiFetch<ShortlistResult>(`/hr/requisitions/${requisitionId}/shortlist`, {
        method: "POST",
        token,
        body: {
          stage_type: "shortlisting",
          shortlisted_application_ids: chosen.map((c) => c.id),
          shortlisted_letter: shortlistedLetter,
          not_shortlisted_letter: notShortlistedLetter,
        },
      });
      setResult(res);
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send. Nothing was recorded.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="presentation"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15, 23, 42, 0.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        zIndex: 100,
      }}
    >
      <div role="dialog" aria-modal="true" aria-label={`Shortlist for ${jobTitle}`} onClick={(e) => e.stopPropagation()}>
        <Card padding={24} elevation="md" style={{ width: 680, maxWidth: "92vw", maxHeight: "88vh", overflowY: "auto" }}>
          {result ? (
            <SentSummary result={result} jobTitle={jobTitle} onClose={onClose} />
          ) : (
            <>
              <h2 style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--ink-900)", margin: 0 }}>
                Shortlist for {jobTitle}
              </h2>
              <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", marginTop: 8, lineHeight: 1.55 }}>
                Tick the candidates you want to shortlist. Everyone else here is recorded as not
                shortlisted, and both groups get the message you write below. The list is ordered by
                match score as a guide. The choice is yours.
              </p>

              <PickList pool={pool} picked={picked} onToggle={toggle} chosenCount={chosen.length} />

              {decided.length > 0 && <DecidedNote decided={decided} />}

              <label style={labelStyle}>
                Message to the {chosen.length} you shortlisted
                <textarea
                  rows={5}
                  value={shortlistedLetter}
                  onChange={(e) => setShortlistedLetter(e.target.value)}
                  disabled={chosen.length === 0}
                  placeholder={
                    chosen.length === 0
                      ? "Nobody is ticked yet, so this message has no one to go to."
                      : "They'll be asked to confirm they'd still like to go ahead. Tell them what comes next."
                  }
                  style={{ ...inputStyle, marginTop: 6, resize: "vertical", opacity: chosen.length === 0 ? 0.55 : 1 }}
                />
              </label>

              <label style={labelStyle}>
                Message to the {rejected.length} you did not
                <textarea
                  rows={5}
                  value={notShortlistedLetter}
                  onChange={(e) => setNotShortlistedLetter(e.target.value)}
                  disabled={rejected.length === 0}
                  placeholder={
                    rejected.length === 0
                      ? "Everyone is ticked, so this message has no one to go to."
                      : "Their application stays open. You might tell them they can wait or browse other openings."
                  }
                  style={{ ...inputStyle, marginTop: 6, resize: "vertical", opacity: rejected.length === 0 ? 0.55 : 1 }}
                />
              </label>

              <div
                style={{
                  display: "flex",
                  gap: 10,
                  alignItems: "flex-start",
                  marginTop: 16,
                  padding: "11px 12px",
                  background: "var(--warning-bg)",
                  borderLeft: "3px solid var(--warning-text)",
                  borderRadius: "var(--radius-xs)",
                }}
              >
                <AlertIcon width={17} height={17} style={{ color: "var(--warning-text)", flexShrink: 0, marginTop: 1 }} />
                <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-900)", lineHeight: 1.5 }}>
                  Both letters send as soon as you confirm, and emails cannot be recalled. Nobody here is
                  rejected: the applications of those you do not shortlist stay open.
                </span>
              </div>

              {error && (
                <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "crimson", marginTop: 12 }}>{error}</p>
              )}

              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
                <Button variant="secondary" onClick={onClose} disabled={submitting}>
                  Cancel
                </Button>
                <Button variant="primary" onClick={send} disabled={!canSend}>
                  {submitting
                    ? "Sending..."
                    : `Shortlist ${chosen.length} and write to ${chosen.length + rejected.length}`}
                </Button>
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}

/** The field, as a list of choices. Rank is shown as a hint, not as an
 *  order of merit — it is where the score put them, which is why it is
 *  greyed and sits behind the name rather than leading the row. */
function PickList({
  pool,
  picked,
  onToggle,
  chosenCount,
}: {
  pool: ApplicationListItem[];
  picked: Set<number>;
  onToggle: (id: number) => void;
  chosenCount: number;
}) {
  if (pool.length === 0) {
    return (
      <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", marginTop: 16 }}>
        Nobody on this job is waiting on a shortlisting decision.
      </p>
    );
  }
  return (
    <div style={{ marginTop: 16, border: "1px solid var(--surface-border)", borderRadius: "var(--radius)", overflow: "hidden" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          padding: "8px 12px",
          background: "var(--surface-bg-alt)",
          fontFamily: "var(--arkive-font)",
          fontSize: "var(--text-xs)",
          fontWeight: 700,
          color: "var(--ink-600)",
          letterSpacing: "var(--track-snug)",
        }}
      >
        <span>WAITING ON A DECISION</span>
        <span>
          {chosenCount} of {pool.length} shortlisted
        </span>
      </div>
      {pool.map((row, i) => {
        const on = picked.has(row.id);
        return (
          <label
            key={row.id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "9px 12px",
              borderTop: "1px solid var(--surface-border)",
              background: on ? "var(--success-bg)" : "transparent",
              cursor: "pointer",
              fontFamily: "var(--arkive-font)",
              fontSize: "var(--text-sm)",
            }}
          >
            <input type="checkbox" checked={on} onChange={() => onToggle(row.id)} style={{ cursor: "pointer" }} />
            <span className="ark-num" style={{ color: "var(--ink-300)", minWidth: 18 }}>
              {row.match_score != null ? i + 1 : "–"}
            </span>
            <span className="ark-truncate" style={{ flex: 1, color: "var(--ink-900)", fontWeight: on ? 650 : 500 }}>
              {row.applicant_name}
            </span>
            <span
              className="ark-num"
              style={{ color: row.match_score != null ? "var(--ink-600)" : "var(--ink-300)", whiteSpace: "nowrap" }}
            >
              {row.match_score != null ? `${row.match_score}%` : "no score yet"}
            </span>
          </label>
        );
      })}
    </div>
  );
}

/** The candidates this action deliberately does not touch.
 *
 *  A call recorded on someone's own profile is final here -- remaking it
 *  in bulk would mean a decision changing without anyone opening the
 *  record it was made on. Shown rather than simply absent, so the count
 *  adds up and nobody appears to have vanished from the pipeline. */
function DecidedNote({ decided }: { decided: ApplicationListItem[] }) {
  return (
    <div
      style={{
        marginTop: 12,
        padding: "11px 12px",
        border: "1px solid var(--surface-border)",
        borderRadius: "var(--radius-xs)",
        background: "var(--surface-bg-alt)",
      }}
    >
      <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", fontWeight: 650, color: "var(--ink-900)", margin: 0 }}>
        {decided.length} already decided, not part of this shortlist
      </p>
      {decided.map((row) => (
        <p
          key={row.id}
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: 12,
            fontFamily: "var(--arkive-font)",
            fontSize: "var(--text-sm)",
            color: "var(--ink-600)",
            margin: "6px 0 0",
          }}
        >
          <span className="ark-truncate">{row.applicant_name}</span>
          <span style={{ whiteSpace: "nowrap" }}>
            {row.shortlisting_outcome === "shortlisted" ? "Shortlisted" : "Not shortlisted"}
          </span>
        </p>
      ))}
      <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xs)", color: "var(--ink-600)", margin: "8px 0 0", lineHeight: 1.5 }}>
        Their decision is already recorded, so they cannot be picked here and nothing is sent to them. Use
        Update Decision on their profile to change one.
      </p>
    </div>
  );
}

/** What actually happened, including the half that can fail quietly.
 *  A send that reports only "done" leaves HR to discover a bounced
 *  mail server from the candidate who never replied. */
function SentSummary({
  result,
  jobTitle,
  onClose,
}: {
  result: ShortlistResult;
  jobTitle: string;
  onClose: () => void;
}) {
  return (
    <>
      <h2 style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--ink-900)", margin: 0 }}>
        Shortlist recorded for {jobTitle}
      </h2>
      <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", marginTop: 8, lineHeight: 1.55 }}>
        {result.shortlisted.length} shortlisted, {result.not_shortlisted.length} not. Shortlisted candidates
        have been asked to confirm before their examination is arranged.
      </p>

      {result.emails_failed > 0 && (
        <div
          style={{
            display: "flex",
            gap: 10,
            alignItems: "flex-start",
            marginTop: 14,
            padding: "11px 12px",
            background: "var(--warning-bg)",
            borderLeft: "3px solid var(--warning-text)",
            borderRadius: "var(--radius-xs)",
          }}
        >
          <AlertIcon width={17} height={17} style={{ color: "var(--warning-text)", flexShrink: 0, marginTop: 1 }} />
          <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-900)", lineHeight: 1.5 }}>
            {result.emails_failed} {result.emails_failed === 1 ? "email" : "emails"} could not be sent. The
            decisions are recorded and every candidate has an in-app notification, but those people did not
            get a letter. You may want to contact them directly.
          </span>
        </div>
      )}

      {result.already_decided.length > 0 && (
        <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", marginTop: 14, lineHeight: 1.55 }}>
          {result.already_decided.length} candidate{result.already_decided.length === 1 ? "" : "s"} already had a
          decision recorded on their profile and {result.already_decided.length === 1 ? "was" : "were"} left
          untouched. Nothing was changed or sent for them.
        </p>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 20 }}>
        <Button variant="primary" onClick={onClose}>
          Done
        </Button>
      </div>
    </>
  );
}

const labelStyle: React.CSSProperties = {
  display: "block",
  fontFamily: "var(--arkive-font)",
  fontSize: "var(--text-sm)",
  fontWeight: 600,
  color: "var(--ink-900)",
  marginTop: 18,
};

const inputStyle: React.CSSProperties = {
  display: "block",
  width: "100%",
  boxSizing: "border-box",
  padding: "8px 10px",
  border: "1px solid var(--surface-border)",
  borderRadius: "var(--radius)",
  fontFamily: "var(--arkive-font)",
  fontSize: "var(--text-base)",
  color: "var(--ink-900)",
  background: "var(--surface)",
};
