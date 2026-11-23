/**
 * The resume and any supplemental documents the applicant uploaded.
 * State stays on the page (see ../types.ts).
 */

import { openFile } from "../../../../../../shared/api/client";
import { openResumeFile } from "../../../../../../shared/api/resume";
import { Card } from "../../../../../../shared/ui/Card";
import { Tag } from "../../../../../../shared/ui/Tag";
import { Button } from "../../../../../../shared/ui/Button";
import { SectionLabel } from "../../../../../../shared/ui/SectionLabel";
import { DocumentIcon, DownloadIcon } from "../../../../../../shared/ui/icons";
import { PdfPreview } from "../../../../../../shared/components/PdfPreview";

import { DetailRow, Pending } from "../atoms";
import type { CandidateProfile } from "../../../../../../shared/api/pipeline";

interface DocumentsTabProps {
  profile: CandidateProfile;
  applicationId: string | undefined;
  token: string | null;
}

export function DocumentsTab({ profile, applicationId, token }: DocumentsTabProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {!profile.resume && profile.documents.length === 0 && (
                  <Card padding={16}>
                    <Pending />
                  </Card>
                )}
                {profile.resume && (
                  <>
                    <Card padding={16}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <div
                            style={{
                              width: 32,
                              height: 32,
                              borderRadius: "var(--radius)",
                              background: "var(--accent-bg)",
                              color: "var(--accent)",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                            }}
                          >
                            <DocumentIcon width={16} height={16} />
                          </div>
                          <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-900)", fontWeight: 600 }}>
                            {profile.resume.original_filename}
                          </span>
                        </div>
                        <Button
                          variant="secondary"
                          onClick={() => openResumeFile(`/hr/applications/${applicationId}/resume-file`, token)}
                          style={{ padding: "6px 12px", fontSize: "var(--text-sm)" }}
                        >
                          <DownloadIcon width={14} height={14} />
                          Download Original
                        </Button>
                      </div>
                      <div style={{ marginTop: 10 }}>
                        <PdfPreview path={`/hr/applications/${applicationId}/resume-file`} token={token} />
                      </div>
                    </Card>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                      <Card padding={16}>
                        <SectionLabel>Contact</SectionLabel>
                        <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                          <DetailRow value={profile.resume.full_name} />
                          <DetailRow value={profile.resume.email} />
                          <DetailRow value={profile.resume.phone} />
                          <DetailRow value={profile.resume.location} />
                          <DetailRow value={profile.resume.linkedin_url} />
                          <DetailRow value={profile.resume.portfolio_url} />
                        </div>
                      </Card>
                      <Card padding={16}>
                        <SectionLabel>Skills</SectionLabel>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
                          {profile.resume.skills.length > 0 ? (
                            profile.resume.skills.map((skill) => <Tag key={skill}>{skill}</Tag>)
                          ) : (
                            <Pending />
                          )}
                        </div>
                        {profile.resume.certifications.length > 0 && (
                          <>
                            <div style={{ marginTop: 14 }}>
                              <SectionLabel>Certifications</SectionLabel>
                            </div>
                            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
                              {profile.resume.certifications.map((cert) => (
                                <Tag key={cert} tone="violet">
                                  {cert}
                                </Tag>
                              ))}
                            </div>
                          </>
                        )}
                      </Card>
                    </div>

                    {profile.resume.professional_summary && (
                      <Card padding={16}>
                        <SectionLabel>Professional Summary</SectionLabel>
                        <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-900)", marginTop: 8, marginBottom: 0, lineHeight: 1.6 }}>
                          {profile.resume.professional_summary}
                        </p>
                      </Card>
                    )}

                    {profile.resume.education.length > 0 && (
                      <Card padding={16}>
                        <SectionLabel>Education</SectionLabel>
                        <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 10 }}>
                          {profile.resume.education.map((entry, i) => (
                            <div key={i} style={{ paddingBottom: 10, borderBottom: i < profile.resume!.education.length - 1 ? "1px solid var(--surface-border)" : "none" }}>
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                                <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", fontWeight: 700, color: "var(--ink-900)" }}>
                                  {entry.school}
                                </span>
                                <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xs)", color: "var(--ink-400)" }}>
                                  {[entry.start_date, entry.end_date].filter(Boolean).join(" – ")}
                                </span>
                              </div>
                              <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", margin: "2px 0 0" }}>
                                {[entry.degree, entry.field_of_study, entry.honors].filter(Boolean).join(", ")}
                              </p>
                            </div>
                          ))}
                        </div>
                      </Card>
                    )}

                    {profile.resume.experience.length > 0 && (
                      <Card padding={16}>
                        <SectionLabel>Work Experience</SectionLabel>
                        <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 10 }}>
                          {profile.resume.experience.map((entry, i) => (
                            <div key={i} style={{ paddingBottom: 10, borderBottom: i < profile.resume!.experience.length - 1 ? "1px solid var(--surface-border)" : "none" }}>
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                                <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", fontWeight: 700, color: "var(--ink-900)" }}>
                                  {[entry.title, entry.company].filter(Boolean).join(", ")}
                                </span>
                                <span style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xs)", color: "var(--ink-400)" }}>
                                  {[entry.start_date, entry.end_date].filter(Boolean).join(" – ")}
                                </span>
                              </div>
                              {entry.description && (
                                <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", margin: "4px 0 0", lineHeight: 1.5 }}>
                                  {entry.description}
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
                      </Card>
                    )}

                    {/* The resume's own extra headings (projects, awards...),
                        each as its own card, in the order they appeared. */}
                    {(profile.resume.additional_sections ?? []).map((section, i) => (
                      <Card key={i} padding={16}>
                        <SectionLabel>{section.title || "Other"}</SectionLabel>
                        <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-900)", marginTop: 8, marginBottom: 0, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                          {section.content}
                        </p>
                      </Card>
                    ))}

                    {profile.letter_of_intent && (
                      <Card padding={16}>
                        <SectionLabel>Letter of Intent</SectionLabel>
                        <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-900)", marginTop: 8, marginBottom: 0, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                          {profile.letter_of_intent}
                        </p>
                      </Card>
                    )}

                  </>
                )}

                {profile.documents.length > 0 && (
                  <Card padding={16}>
                    <SectionLabel>Additional Documents</SectionLabel>
                    <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 10 }}>
                      {profile.documents.map((doc) => (
                        <div key={doc.id}>
                          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                              <div
                                style={{
                                  width: 28,
                                  height: 28,
                                  borderRadius: "var(--radius)",
                                  background: "var(--accent-bg)",
                                  color: "var(--accent)",
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                  flexShrink: 0,
                                }}
                              >
                                <DocumentIcon width={14} height={14} />
                              </div>
                              <div style={{ minWidth: 0 }}>
                                <div style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--ink-900)" }}>
                                  {doc.label}
                                </div>
                                <div style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-xs)", color: "var(--ink-400)" }}>
                                  {doc.original_filename}
                                </div>
                              </div>
                            </div>
                            <Button
                              variant="ghost"
                              onClick={() =>
                                openFile(
                                  `/hr/applications/${applicationId}/documents/${doc.id}/file`,
                                  token,
                                  "Could not download this document."
                                )
                              }
                              style={{ padding: "4px 8px", fontSize: "var(--text-xs)", flexShrink: 0 }}
                            >
                              <DownloadIcon width={13} height={13} />
                              Download
                            </Button>
                          </div>
                          <div style={{ marginTop: 8 }}>
                            <PdfPreview
                              path={`/hr/applications/${applicationId}/documents/${doc.id}/file`}
                              token={token}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}
              </div>
  );
}
