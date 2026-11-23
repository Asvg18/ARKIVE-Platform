/**
 * Shortlisting: HR's call on whether this candidate moves on to
 * Examination, shortlisted or not, with notes.
 *
 * A plain outcome HR records once, no scheduling concept. State stays
 * on the page, same reason as every other tab here -- see ../types.ts.
 */

import { Card } from "../../../../../../shared/ui/Card";
import { Tag } from "../../../../../../shared/ui/Tag";
import { Button } from "../../../../../../shared/ui/Button";
import { SectionLabel } from "../../../../../../shared/ui/SectionLabel";
import type { ShortlistingEditor } from "../types";

import { Pending } from "../atoms";
import { capitalize } from "../display";
import type { CandidateProfile } from "../../../../../../shared/api/pipeline";

interface ShortlistingTabProps {
  profile: CandidateProfile;
  shortlistingStageKeys: string[];
  editor: ShortlistingEditor;
}

export function ShortlistingTab({ profile, shortlistingStageKeys, editor }: ShortlistingTabProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {shortlistingStageKeys.length === 0 && <Pending />}
      {shortlistingStageKeys.map((stageType) => {
        const entry = profile.shortlisting[stageType];
        return (
          <Card key={stageType} padding={16}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <span style={{ fontFamily: "var(--arkive-font)", fontWeight: 700, fontSize: "var(--text-base)", color: "var(--ink-900)" }}>
                {entry.label}
              </span>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Tag dot>{capitalize(entry.status)}</Tag>
                {entry.outcome != null && (
                  <Tag tone={entry.outcome === "shortlisted" ? "green" : "amber"} dot>
                    {capitalize(entry.outcome)}
                  </Tag>
                )}
              </div>
            </div>

            {entry.notes && (
              <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", marginTop: 10 }}>
                {entry.notes}
              </p>
            )}

            <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--surface-border)" }}>
              <SectionLabel>Shortlisting Decision</SectionLabel>
              <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xs)", color: "var(--ink-600)", margin: "8px 0 12px" }}>
                Decide once the Pre-Screening read is in. This candidate needs a shortlisted or not call
                before moving on to Examination.
                {entry.outcome != null && " You can update it if it was entered in error."}
              </p>
              {editor.editingStage === stageType ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 480 }}>
                  <div style={{ display: "flex", gap: 8 }}>
                    {(["shortlisted", "not_shortlisted"] as const).map((option) => (
                      <button
                        key={option}
                        type="button"
                        onClick={() => editor.setOutcome(option)}
                        style={{
                          padding: "8px 16px",
                          borderRadius: "var(--radius)",
                          border: `1px solid ${editor.outcome === option ? "var(--accent)" : "var(--surface-border)"}`,
                          background: editor.outcome === option ? "var(--accent-bg)" : "var(--surface)",
                          color: editor.outcome === option ? "var(--accent)" : "var(--ink-900)",
                          fontFamily: "var(--arkive-font)",
                          fontSize: "var(--text-sm)",
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        {capitalize(option)}
                      </button>
                    ))}
                  </div>
                  <textarea
                    value={editor.notes}
                    onChange={(e) => editor.setNotes(e.target.value)}
                    placeholder="Notes (optional)"
                    rows={2}
                    style={{
                      padding: "8px 10px",
                      borderRadius: "var(--radius)",
                      border: "1px solid var(--surface-border)",
                      background: "var(--surface)",
                      fontFamily: "var(--arkive-font)",
                      fontSize: "var(--text-sm)",
                      color: "var(--ink-900)",
                      boxSizing: "border-box",
                      resize: "vertical",
                    }}
                  />
                  <div style={{ display: "flex", gap: 8 }}>
                    <Button variant="primary" onClick={() => editor.submit(stageType)} disabled={editor.submitting} style={{ padding: "8px 16px" }}>
                      {editor.submitting ? "Saving..." : "Save Decision"}
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => editor.setEditingStage(null)}
                      disabled={editor.submitting}
                      style={{ padding: "8px 16px" }}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  variant="secondary"
                  onClick={() => {
                    editor.setEditingStage(stageType);
                    editor.setOutcome(entry.outcome ?? "shortlisted");
                    editor.setNotes(entry.notes ?? "");
                    editor.setError(null);
                  }}
                  style={{ padding: "6px 12px", fontSize: "var(--text-sm)" }}
                >
                  {entry.outcome != null ? "Update Decision" : "Record Decision"}
                </Button>
              )}
              {editor.error && editor.editingStage === stageType && (
                <p style={{ color: "crimson", fontSize: "var(--text-sm)", marginTop: 8 }}>{editor.error}</p>
              )}
            </div>
          </Card>
        );
      })}
    </div>
  );
}
