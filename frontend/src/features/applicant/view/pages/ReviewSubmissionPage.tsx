import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type { ApplicationDetail, PreScreeningAnswer } from "../../../../shared/api/applicant";
import { ApplicantAppShell } from "../components/ApplicantAppShell";
import { Card } from "../../../../shared/ui/Card";
import { Tag } from "../../../../shared/ui/Tag";
import { ErrorState } from "../../../../shared/ui/ErrorState";
import { SectionLabel } from "../../../../shared/ui/SectionLabel";
import { PageHeader } from "../../../../shared/ui/PageHeader";

/**
 * Exactly what was submitted, read-only -- no field here can be edited
 * or resubmitted from this screen. Built entirely from the same GET
 * .../applications/{id} the stage page already reads; the letter of
 * intent and pre-screening answers just live inside stage_instances'
 * payload rather than as their own top-level fields, since that's
 * where they were written (see DocumentUploadScreen/PreScreeningScreen).
 */
export function ReviewSubmissionPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const [application, setApplication] = useState<ApplicationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    setError(null);
    apiFetch<ApplicationDetail>(`/applicant/applications/${id}`, { token })
      .then(setApplication)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load."))
      .finally(() => setLoading(false));
  }, [id, token, reloadKey]);

  const resume = application?.resume ?? null;

  const documentUploadPayload = application?.stage_instances.find(
    (s) => s.stage_type === "document_upload"
  )?.payload;
  const letterOfIntent = (documentUploadPayload?.letter_of_intent as string | undefined) || null;

  const skillMatchingPayload = application?.stage_instances.find(
    (s) => s.stage_type === "skill_matching"
  )?.payload;
  const answers = (skillMatchingPayload?.answers as PreScreeningAnswer[] | undefined) ?? [];

  function questionText(questionId: string): string {
    return (
      application?.pre_screening_questions.find((q) => q.id === questionId)?.text ??
      "(This question is no longer part of the job's pre-screening.)"
    );
  }

  return (
    <ApplicantAppShell>
      <PageHeader
        above={
          <Link to={`/applicant/applications/${id}`} className="ark-back">
            &larr; Back to Application
          </Link>
        }
        title="Review My Submission"
        description={
          <>
            {application ? `Everything you submitted for ${application.job_title}, exactly as it was sent.` : "Loading..."}
            {" "}This is a read-only view. Nothing here can be changed.
          </>
        }
      />

      {loading && <p style={{ fontFamily: "var(--arkive-font)", color: "var(--ink-600)" }}>Loading...</p>}
      {error && <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {application && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 720 }}>
          {!resume && (
            <Card padding={20}>
              <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", fontStyle: "italic", margin: 0 }}>
                You haven't uploaded a resume yet.
              </p>
            </Card>
          )}

          {resume && (
            <>
              <Card padding={20}>
                <SectionLabel>Contact</SectionLabel>
                <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 4 }}>
                  <DetailRow label="Full Name" value={resume.full_name} />
                  <DetailRow label="Email" value={resume.email} />
                  <DetailRow label="Phone" value={resume.phone} />
                  <DetailRow label="Location" value={resume.location} />
                  <DetailRow label="LinkedIn" value={resume.linkedin_url} />
                  <DetailRow label="Portfolio" value={resume.portfolio_url} />
                </div>
              </Card>

              {resume.professional_summary && (
                <Card padding={20}>
                  <SectionLabel>Professional Summary</SectionLabel>
                  <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-900)", marginTop: 8, marginBottom: 0, lineHeight: 1.6 }}>
                    {resume.professional_summary}
                  </p>
                </Card>
              )}

              {(resume.skills.length > 0 || resume.certifications.length > 0) && (
                <Card padding={20}>
                  {resume.skills.length > 0 && (
                    <div>
                      <SectionLabel>Skills</SectionLabel>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
                        {resume.skills.map((skill) => (
                          <Tag key={skill}>{skill}</Tag>
                        ))}
                      </div>
                    </div>
                  )}
                  {resume.certifications.length > 0 && (
                    <div style={{ marginTop: resume.skills.length > 0 ? 16 : 0 }}>
                      <SectionLabel>Certifications</SectionLabel>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
                        {resume.certifications.map((cert) => (
                          <Tag key={cert} tone="violet">
                            {cert}
                          </Tag>
                        ))}
                      </div>
                    </div>
                  )}
                </Card>
              )}

              {resume.education.length > 0 && (
                <Card padding={20}>
                  <SectionLabel>Education</SectionLabel>
                  <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 10 }}>
                    {resume.education.map((entry, i) => (
                      <div key={i} style={{ paddingBottom: 10, borderBottom: i < resume.education.length - 1 ? "1px solid var(--surface-border)" : "none" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
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

              {resume.experience.length > 0 && (
                <Card padding={20}>
                  <SectionLabel>Work Experience</SectionLabel>
                  <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 10 }}>
                    {resume.experience.map((entry, i) => (
                      <div key={i} style={{ paddingBottom: 10, borderBottom: i < resume.experience.length - 1 ? "1px solid var(--surface-border)" : "none" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
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

              {(resume.additional_sections ?? []).map((section, i) => (
                <Card key={i} padding={20}>
                  <SectionLabel>{section.title || "Other"}</SectionLabel>
                  <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-900)", marginTop: 8, marginBottom: 0, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                    {section.content}
                  </p>
                </Card>
              ))}
            </>
          )}

          {letterOfIntent && (
            <Card padding={20}>
              <SectionLabel>Letter of Intent</SectionLabel>
              <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-900)", marginTop: 8, marginBottom: 0, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                {letterOfIntent}
              </p>
            </Card>
          )}

          {answers.length > 0 && (
            <Card padding={20}>
              <SectionLabel>Pre-Screening Answers</SectionLabel>
              <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 10 }}>
                {answers.map((answer) => (
                  <div key={answer.question_id}>
                    <div style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--ink-900)" }}>
                      {questionText(answer.question_id)}
                    </div>
                    <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-base)", color: "var(--ink-600)", margin: "4px 0 0", whiteSpace: "pre-wrap" }}>
                      {answer.value || "(no answer provided)"}
                    </p>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}
    </ApplicantAppShell>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div style={{ display: "flex", gap: 8, fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)" }}>
      <span style={{ color: "var(--ink-400)", minWidth: 90 }}>{label}</span>
      <span style={{ color: "var(--ink-900)" }}>{value}</span>
    </div>
  );
}
