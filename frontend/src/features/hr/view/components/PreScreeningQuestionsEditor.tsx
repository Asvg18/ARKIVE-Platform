import type { Dispatch, ReactNode, SetStateAction } from "react";
import type { PreScreeningQuestion } from "../../../../shared/api/pipeline";
import { Card } from "../../../../shared/ui/Card";
import { Button } from "../../../../shared/ui/Button";
import { makeQuestion } from "../../model/preScreeningQuestions";

/**
 * A job's pre-screening questions, edited: the text of each, whether it
 * is required, add and remove. Shared by the Pre-Screening Questions page
 * (an existing job) and Create Job Opening (a job not yet saved). It
 * saves nothing itself; `footer` sits at
 * the right end of the "+ Add Question" row for the page's own controls.
 */
export function PreScreeningQuestionsEditor({
  questions,
  onChange,
  locked = false,
  footer,
}: {
  questions: PreScreeningQuestion[];
  onChange: Dispatch<SetStateAction<PreScreeningQuestion[]>>;
  locked?: boolean;
  footer?: ReactNode;
}) {
  function updateQuestion(qId: string, patch: Partial<PreScreeningQuestion>) {
    onChange((prev) => prev.map((q) => (q.id === qId ? { ...q, ...patch } : q)));
  }

  function removeQuestion(qId: string) {
    onChange((prev) => prev.filter((q) => q.id !== qId));
  }

  function addQuestion() {
    onChange((prev) => [...prev, makeQuestion()]);
  }

  return (
    <>
      <Card padding={0} elevation="md" style={{ maxWidth: 780 }}>
        <div style={{ display: "flex", flexDirection: "column" }}>
          {questions.map((q, index) => (
            <div
              key={q.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 16,
                padding: "16px 20px",
                borderBottom: index < questions.length - 1 ? "1px solid var(--surface-border)" : "none",
              }}
            >
              <span
                style={{
                  width: 24,
                  height: 24,
                  borderRadius: "var(--radius-full)",
                  background: "var(--surface-bg-alt)",
                  color: "var(--ink-600)",
                  fontSize: "var(--text-xs)",
                  fontWeight: 700,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                {index + 1}
              </span>

              <input
                value={q.text}
                onChange={(e) => updateQuestion(q.id, { text: e.target.value })}
                disabled={locked}
                placeholder="e.g. Why are you interested in this role?"
                aria-label={`Question ${index + 1}`}
                style={{ ...fieldStyle, flex: "1 1 auto", color: "var(--ink-900)" }}
              />

              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  fontFamily: "var(--arkive-font)",
                  fontSize: "var(--text-sm)",
                  color: "var(--ink-600)",
                  flex: "0 0 90px",
                  cursor: locked ? "default" : "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={q.required}
                  onChange={(e) => updateQuestion(q.id, { required: e.target.checked })}
                  disabled={locked}
                  style={{ border: "none", padding: 0 }}
                />
                Required
              </label>

              {!locked && (
                <button
                  type="button"
                  onClick={() => removeQuestion(q.id)}
                  aria-label="Remove question"
                  style={{
                    border: "none",
                    background: "transparent",
                    color: "var(--ink-400)",
                    fontSize: "var(--text-xl)",
                    lineHeight: 1,
                    cursor: "pointer",
                    padding: 4,
                    flexShrink: 0,
                  }}
                >
                  &times;
                </button>
              )}
            </div>
          ))}

          {questions.length === 0 && (
            <div style={{ padding: 24, textAlign: "center", color: "var(--ink-600)", fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)" }}>
              No questions yet. Add one below.
            </div>
          )}
        </div>
      </Card>

      {(!locked || footer) && (
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 16, maxWidth: 780, flexWrap: "wrap" }}>
          {!locked && (
            <Button variant="outline" onClick={addQuestion}>
              + Add Question
            </Button>
          )}
          <div style={{ flex: 1 }} />
          {footer}
        </div>
      )}
    </>
  );
}

const fieldStyle: React.CSSProperties = {
  padding: "8px 10px",
  borderRadius: "var(--radius)",
  border: "1px solid var(--surface-border)",
  fontSize: "var(--text-sm)",
  fontFamily: "var(--arkive-font)",
  background: "var(--surface)",
  boxSizing: "border-box",
};
