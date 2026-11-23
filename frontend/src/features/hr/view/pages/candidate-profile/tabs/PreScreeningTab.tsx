/**
 * The applicant's own answers to HR's pre-screening questions, beside the
 * Skill Matching Agent's reading of them.
 * State stays on the page (see ../types.ts).
 */

import { shownText } from "../../../../../../shared/lib/displayText";
import { ReasonList } from "../../../../../../shared/ui/ReasonList";
import { Card } from "../../../../../../shared/ui/Card";
import { SectionLabel } from "../../../../../../shared/ui/SectionLabel";

import { NoneFound, Pending } from "../atoms";
import type { CandidateProfile } from "../../../../../../shared/api/pipeline";

interface PreScreeningTabProps {
  profile: CandidateProfile;
}

export function PreScreeningTab({ profile }: PreScreeningTabProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {profile.pre_screening_qa.length === 0 ? (
                  <Card padding={16}>
                    <Pending />
                  </Card>
                ) : (
                  <>
                    <Card padding={16} elevation="none" style={{ background: "var(--accent-bg)", borderLeft: "3px solid var(--accent)" }}>
                      <div style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--accent)", marginBottom: 6 }}>
                        Interview Analysis Agent
                      </div>
                      <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-900)", margin: 0, lineHeight: 1.6 }}>
                        {shownText(profile.interview_analysis_summary) ?? "Not yet available."}
                      </p>
                    </Card>

                    {/* minmax(0, 1fr) rather than 1fr: a grid track's
                        default min-width is auto, so a long finding used
                        to widen the column past the viewport instead of
                        wrapping inside it. */}
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 24 }}>
                      <div style={{ minWidth: 0 }}>
                        {profile.interview_analysis_strengths.length > 0 ? (
                          <ReasonList
                            title="Core Strengths"
                            items={profile.interview_analysis_strengths.map((item) => shownText(item))}
                            tone="success"
                          />
                        ) : (
                          <>
                            <SectionLabel>Core Strengths</SectionLabel>
                            {profile.interview_analysis_summary != null ? <NoneFound /> : <Pending />}
                          </>
                        )}
                      </div>
                      <div style={{ minWidth: 0 }}>
                        {profile.interview_analysis_gaps.length > 0 ? (
                          <ReasonList
                            title="Areas of Concern"
                            items={profile.interview_analysis_gaps.map((item) => shownText(item))}
                            tone="warning"
                          />
                        ) : (
                          <>
                            <SectionLabel>Areas of Concern</SectionLabel>
                            {profile.interview_analysis_summary != null ? <NoneFound /> : <Pending />}
                          </>
                        )}
                      </div>
                    </div>

                    <div>
                      <SectionLabel>Questions &amp; Answers</SectionLabel>
                      <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 8 }}>
                        {profile.pre_screening_qa.map((entry) => (
                          <Card key={entry.question_id} padding={16}>
                            <div style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--ink-900)" }}>
                              {entry.question_text}
                            </div>
                            <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", marginTop: 6, marginBottom: 0, whiteSpace: "pre-wrap" }}>
                              {entry.answer || "(no answer provided)"}
                            </p>
                          </Card>
                        ))}
                      </div>
                    </div>
                  </>
                )}
              </div>
  );
}
