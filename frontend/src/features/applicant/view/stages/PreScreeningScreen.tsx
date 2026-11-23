import { useState } from "react";
import { AI_REQUEST_TIMEOUT_MS, apiFetch, ApiError } from "../../../../shared/api/client";
import type { ApplicationDetail } from "../../../../shared/api/applicant";
import { Button } from "../../../../shared/ui/Button";

/**
 * Real, HR-authored Pre-Screening questions — replaces the old hardcoded
 * 3-question array. Each free-text question from
 * application.pre_screening_questions is one step. The exam pick is not
 * here; it belongs to the Examination stage. Chat/text only for now;
 * voice is a deliberately separate, later phase.
 */
type Step = { id: string; text: string; required: boolean };

export function PreScreeningScreen({
  application,
  token,
  onAdvance,
}: {
  application: ApplicationDetail;
  token: string | null;
  onAdvance: (updated: ApplicationDetail) => void;
}) {
  const steps: Step[] = application.pre_screening_questions.map(
    (q): Step => ({ id: q.id, text: q.text, required: q.required })
  );

  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (steps.length === 0) {
    return (
      <div>
        <h2 style={heading}>Pre-Screening</h2>
        <p style={subtext}>
          This job has no pre-screening questions configured yet. Check back shortly, or contact HR.
        </p>
      </div>
    );
  }

  const current = steps[step];
  const isLast = step === steps.length - 1;

  function canAdvance(): boolean {
    return !current.required || (answers[current.id]?.trim().length ?? 0) > 0;
  }

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      const updated = await apiFetch<ApplicationDetail>(
        `/applicant/applications/${application.id}/pre-screening`,
        {
          method: "POST",
          token,
          timeoutMs: AI_REQUEST_TIMEOUT_MS,
          body: {
            answers: Object.entries(answers).map(([question_id, value]) => ({ question_id, value })),
          },
        }
      );
      onAdvance(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit pre-screening.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <h2 style={heading}>Pre-Screening</h2>
      <p style={subtext}>
        Step {step + 1} of {steps.length}
      </p>

      <p style={questionText}>
        {current.text}
        {!current.required && <span style={{ color: "var(--ink-400)", fontWeight: 400 }}> (optional)</span>}
      </p>
      <textarea
        value={answers[current.id] ?? ""}
        onChange={(e) => setAnswers((prev) => ({ ...prev, [current.id]: e.target.value }))}
        placeholder="Type your answer here"
        rows={4}
        style={textareaStyle}
      />

      {error && <p style={{ color: "crimson", fontSize: "var(--text-sm)", marginTop: 12 }}>{error}</p>}

      <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
        <Button variant="secondary" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
          Back
        </Button>
        {isLast ? (
          <Button variant="primary" onClick={handleSubmit} disabled={submitting || !canAdvance()}>
            {submitting ? "Submitting..." : "Submit"}
          </Button>
        ) : (
          <Button variant="primary" onClick={() => setStep((s) => s + 1)} disabled={!canAdvance()}>
            Next
          </Button>
        )}
      </div>
    </div>
  );
}

const heading: React.CSSProperties = { fontFamily: "var(--arkive-font)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--ink-900)", margin: 0 };
const subtext: React.CSSProperties = { fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", marginTop: 6 };
const questionText: React.CSSProperties = { fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", fontWeight: 700, color: "var(--ink-900)", marginTop: 20 };
const textareaStyle: React.CSSProperties = {
  display: "block",
  width: "100%",
  marginTop: 12,
  padding: 12,
  borderRadius: "var(--radius)",
  border: "1px solid var(--surface-border)",
  background: "var(--surface)",
  fontFamily: "var(--arkive-font)",
  fontSize: "var(--text-base)",
  color: "var(--ink-900)",
  boxSizing: "border-box",
  resize: "vertical",
};
