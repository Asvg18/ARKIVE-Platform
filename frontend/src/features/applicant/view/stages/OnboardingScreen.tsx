import { useState } from "react";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { ApplicationDetail } from "../../../../shared/api/applicant";
import { ProgressBar } from "../../../../shared/ui/ProgressBar";
import { CheckIcon } from "../../../../shared/ui/icons";

/** The onboarding checklist as a numbered step tracker, each item saying
 * what it involves, so "Submit Pre-201 requirements" is not a phrase the
 * applicant must already know. Only the checklist: OfferResponseScreen
 * owns the welcome. Reached through that screen after the offer is
 * accepted, or directly for an active application on an `onboarding`
 * stage. */

const CHECKLIST_ITEMS = [
  {
    key: "signed_offer",
    label: "Sign and return the offer letter",
    detail: "HR will email the letter. Sign it and send it back to complete your acceptance on paper.",
  },
  {
    key: "submitted_pre201",
    label: "Submit pre-employment requirements",
    detail: "Your personal records file: IDs, clearances, and credentials. HR will list exactly what's needed.",
  },
  {
    key: "attended_orientation",
    label: "Attend HR orientation",
    detail: "A short session covering policies, benefits and your department.",
  },
  {
    key: "it_account_setup",
    label: "Set up institutional email and accounts",
    detail: "IT will issue your MSEUF address and system access before your first day.",
  },
];

export function OnboardingScreen({
  application,
  token,
  onUpdate,
}: {
  application: ApplicationDetail;
  token: string | null;
  onUpdate: (updated: ApplicationDetail) => void;
}) {
  const instance = application.stage_instances.find((s) => s.stage_type === "onboarding");
  const savedChecklist = (instance?.payload?.checklist as Record<string, boolean>) ?? {};
  const [checklist, setChecklist] = useState<Record<string, boolean>>(savedChecklist);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle(key: string) {
    const next = { ...checklist, [key]: !checklist[key] };
    setChecklist(next);
    setSaving(true);
    setError(null);
    try {
      const updated = await apiFetch<ApplicationDetail>(
        `/applicant/applications/${application.id}/onboarding`,
        { method: "PATCH", token, body: { checklist: next } }
      );
      onUpdate(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save checklist.");
      // Roll the optimistic tick back — leaving it on would tell the
      // applicant a step is recorded when the server refused it (the
      // offer gate returns 409 until the offer is answered).
      setChecklist(checklist);
    } finally {
      setSaving(false);
    }
  }

  const doneCount = CHECKLIST_ITEMS.filter((i) => checklist[i.key]).length;
  const progress = Math.round((doneCount / CHECKLIST_ITEMS.length) * 100);
  const allDone = doneCount === CHECKLIST_ITEMS.length;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <span
          style={{
            fontFamily: "var(--arkive-font)",
            fontSize: "var(--text-xs)",
            fontWeight: 700,
            color: "var(--ink-600)",
            textTransform: "uppercase",
            letterSpacing: "0.04em",
          }}
        >
          Onboarding Checklist
        </span>
        <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", fontWeight: 600, color: allDone ? "var(--success-text)" : "var(--ink-600)" }}>
          {doneCount} of {CHECKLIST_ITEMS.length} complete
        </span>
      </div>

      <div style={{ marginTop: 10 }}>
        <ProgressBar value={progress} />
      </div>

      <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", margin: "12px 0 0", lineHeight: 1.55 }}>
        {allDone
          ? "That's everything on your side. HR will be in touch about your start date."
          : "Tick each step as you finish it. HR can see your progress, so there's nothing to send back here."}
      </p>

      <ol style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 18, padding: 0, listStyle: "none" }}>
        {CHECKLIST_ITEMS.map((item, index) => {
          const done = !!checklist[item.key];
          return (
            <li key={item.key}>
              <label
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 12,
                  padding: "12px 14px",
                  borderRadius: "var(--radius)",
                  border: `1px solid ${done ? "var(--success-text)" : "var(--surface-border)"}`,
                  background: done ? "var(--success-bg)" : "var(--surface)",
                  cursor: saving ? "default" : "pointer",
                }}
              >
                <span
                  style={{
                    width: 22,
                    height: 22,
                    borderRadius: "50%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                    marginTop: 1,
                    background: done ? "var(--success-text)" : "var(--surface-bg-alt)",
                    color: done ? "white" : "var(--ink-600)",
                    fontFamily: "var(--arkive-font)",
                    fontSize: "var(--text-xs)",
                    fontWeight: 700,
                  }}
                >
                  {done ? <CheckIcon width={12} height={12} /> : index + 1}
                </span>
                <input
                  type="checkbox"
                  checked={done}
                  disabled={saving}
                  onChange={() => toggle(item.key)}
                  style={{ display: "none" }}
                />
                <span style={{ minWidth: 0 }}>
                  <span
                    style={{
                      display: "block",
                      fontFamily: "var(--arkive-font)",
                      fontSize: "var(--text-base)",
                      fontWeight: 600,
                      color: done ? "var(--success-text)" : "var(--ink-900)",
                      textDecoration: done ? "line-through" : "none",
                    }}
                  >
                    {item.label}
                  </span>
                  <span
                    style={{
                      display: "block",
                      fontFamily: "var(--arkive-font)",
                      fontSize: "var(--text-xs)",
                      color: "var(--ink-600)",
                      marginTop: 2,
                      lineHeight: 1.5,
                    }}
                  >
                    {item.detail}
                  </span>
                </span>
              </label>
            </li>
          );
        })}
      </ol>

      {error && <p style={{ fontFamily: "var(--arkive-font)", color: "crimson", fontSize: "var(--text-sm)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
