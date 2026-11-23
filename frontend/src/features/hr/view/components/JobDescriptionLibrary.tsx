import { useEffect, useMemo, useState } from "react";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import {
  openJobDescriptionFile,
  type JobDescriptionVersion,
  type JobDescriptionVersionDetail,
} from "../../../../shared/api/jobDescriptions";
import { Alert } from "../../../../shared/ui/Alert";
import { Button } from "../../../../shared/ui/Button";
import { Card } from "../../../../shared/ui/Card";
import { InfoTip } from "../../../../shared/ui/InfoTip";
import { Modal } from "../../../../shared/ui/Modal";
import { RowMenu } from "../../../../shared/ui/RowMenu";
import { TablePager } from "../../../../shared/ui/TablePager";
import { DocumentIcon, DownloadIcon, PencilIcon, SearchIcon } from "../../../../shared/ui/icons";
import { paginate } from "../../../../shared/lib/paging";
import { formatSize } from "../../model/jdFile";
import { JobSectionsView } from "./JobDescriptionSections";
import { ReplaceJobDescriptionDialog } from "./ReplaceJobDescriptionDialog";
import { Tag } from "../../../../shared/ui/Tag";

const PAGE_SIZE = 8;

function shortDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

/** Every job description on record, under Create Job Opening's upload:
 *  which document, which job opening it belongs to, its version and
 *  whether it is the one in force, who added it and when, and how many
 *  applicants were scored against it. The current version of each job
 *  can be replaced from here; any version can be opened to read the
 *  exact text it put in force, and its PDF downloaded where one was kept. */
export function JobDescriptionLibrary({ token }: { token: string | null }) {
  const [versions, setVersions] = useState<JobDescriptionVersion[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [viewing, setViewing] = useState<JobDescriptionVersion | null>(null);
  const [replacing, setReplacing] = useState<JobDescriptionVersion | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  function load() {
    apiFetch<JobDescriptionVersion[]>("/hr/job-descriptions", { token })
      .then((rows) => {
        setVersions(rows);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the job descriptions."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const q = query.trim().toLowerCase();
  const rows = useMemo(
    () =>
      (versions ?? []).filter(
        (v) =>
          !q ||
          v.job_title.toLowerCase().includes(q) ||
          v.department.toLowerCase().includes(q) ||
          (v.original_filename ?? "").toLowerCase().includes(q),
      ),
    [versions, q],
  );
  const { pageCount, page: currentPage, visible } = paginate(rows, page, PAGE_SIZE);

  function openFile(version: JobDescriptionVersion) {
    setFileError(null);
    openJobDescriptionFile(version.id, token).catch((err) =>
      setFileError(err instanceof Error ? err.message : "Could not open the document."),
    );
  }

  return (
    <section className="ark-jd-library" aria-labelledby="jd-library-heading">
      <div className="ark-section-head">
        <div className="ark-stat__title-row">
          <h2 id="jd-library-heading" className="ark-section-head__title">
            Job Description History
          </h2>
          <InfoTip ariaLabel="About the job description history" width={340} className="ark-tip--about">
            <div className="ark-about">
              <p className="ark-about__eyebrow">About this history</p>
              <p className="ark-about__summary">
                Every job description on record, and the job opening each one belongs to. A job&rsquo;s description can
                be replaced when it changes; each replacement becomes its next version.
              </p>
              <ul className="ark-about__points">
                <li>Applicants already scored keep their scores, measured against the version they were scored on. No one is re-scored.</li>
                <li>&ldquo;Scored&rdquo; counts the applicants measured against each version.</li>
                <li>Documents are kept from 25 Sep 2026 on. Earlier versions have their text, but no file.</li>
              </ul>
            </div>
          </InfoTip>
        </div>
        <div className="ark-section-head__tools">
          <div className="ark-search" style={{ width: 240 }}>
            <SearchIcon width={15} height={15} className="ark-search__icon" aria-hidden="true" />
            <input
              type="search"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
              placeholder="Search jobs or documents"
              aria-label="Search job descriptions by job, department or file name"
              className="ark-search__input"
            />
          </div>
        </div>
      </div>

      {notice && <Alert tone="success" title={notice} />}
      {fileError && <Alert tone="danger" title={fileError} />}
      {error && (
        <Alert
          tone="danger"
          title={error}
          action={
            <Button variant="secondary" size="sm" onClick={load}>
              Try again
            </Button>
          }
        />
      )}

      {!error && (
        <>
          {/* Same table, card and spacing as the Staff table on User
              Management and the other admin lists: 24px of room inside
              every cell, uppercase headings on a toned band. */}
          <Card padding={0} elevation="md" style={{ marginTop: notice || fileError ? "var(--space-4)" : undefined }}>
            <div style={{ overflowX: "auto" }}>
              <table className="ark-table">
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Job Opening</th>
                    <th>Version</th>
                    <th>Added</th>
                    <th title="Applicants whose match score was measured against this version">Scored</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {versions === null &&
                    Array.from({ length: 3 }, (_, i) => (
                      <tr key={i}>
                        {Array.from({ length: 6 }, (_, j) => (
                          <td key={j}>
                            <span
                              className="ark-skeleton"
                              style={{ display: "block", height: 12, width: j === 5 ? 16 : j === 0 ? 180 : 90 }}
                            />
                          </td>
                        ))}
                      </tr>
                    ))}

                  {visible.map((v) => (
                    <tr key={v.id}>
                      <td>
                        <span className="ark-jd-doc">
                          {/* Accent only when there's a document to open; a
                              name without a kept file, or no document at all,
                              stays grey. */}
                          <span className="ark-jd-doc__icon" data-kind={v.has_file ? "file" : "none"} aria-hidden="true">
                            {v.original_filename ? <DocumentIcon width={16} height={16} /> : <PencilIcon width={14} height={14} />}
                          </span>
                          <span className="ark-jd-doc__text">
                            <span className="ark-truncate ark-dt__primary" title={v.original_filename ?? undefined}>
                              {v.original_filename ?? "Typed by hand"}
                            </span>
                            <span className="ark-truncate ark-dt__secondary">
                              {v.has_file && v.file_size != null
                                ? `PDF · ${formatSize(v.file_size)}`
                                : v.original_filename
                                  ? "Document not kept"
                                  : "No document"}
                            </span>
                          </span>
                        </span>
                      </td>
                      <td>
                        <span className="ark-dt__primary">{v.job_title}</span>
                        <span className="ark-dt__secondary">{v.department}</span>
                      </td>
                      <td>
                        <span className="ark-jd-version">
                          <span className="ark-jd-version__n">v{v.version}</span>
                          <Tag tone={v.is_current ? "green" : "neutral"} dot>
                            {v.is_current ? "Current" : "Replaced"}
                          </Tag>
                        </span>
                      </td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        <span className="ark-dt__primary" style={{ fontWeight: 500 }}>
                          {shortDate(v.created_at)}
                        </span>
                        <span className="ark-dt__secondary" title={v.change_note ?? undefined}>
                          {v.uploaded_by_name ? `by ${v.uploaded_by_name}` : "–"}
                        </span>
                      </td>
                      <td className="ark-num">
                        {v.scored_count}
                        <span className="ark-dt__secondary" style={{ display: "inline", marginLeft: 4 }}>
                          applicant{v.scored_count === 1 ? "" : "s"}
                        </span>
                      </td>
                      <td style={{ width: 1, textAlign: "right" }}>
                        <RowMenu
                          label={`Actions for ${v.job_title} version ${v.version}`}
                          items={[
                            { label: "View text", description: "What this version put in force.", onClick: () => setViewing(v) },
                            v.has_file
                              ? { label: "Open document", icon: <DownloadIcon width={15} height={15} />, onClick: () => openFile(v) }
                              : { label: "Open document", disabled: true, hint: "No document was kept for this version" },
                            v.is_current
                              ? {
                                  label: "Replace job description",
                                  description: "Make a new version the basis for future scores.",
                                  icon: <PencilIcon width={15} height={15} />,
                                  onClick: () => {
                                    setNotice(null);
                                    setReplacing(v);
                                  },
                                  separated: true,
                                }
                              : {
                                  label: "Replace job description",
                                  disabled: true,
                                  hint: "Only the current version can be replaced",
                                  separated: true,
                                },
                          ]}
                        />
                      </td>
                    </tr>
                  ))}

                  {versions !== null && rows.length === 0 && (
                    <tr>
                      <td colSpan={6} style={{ padding: 0 }}>
                        <div className="ark-empty">
                          <span className="ark-empty__mark">
                            {q ? <SearchIcon width={20} height={20} /> : <DocumentIcon width={20} height={20} />}
                          </span>
                          <span className="ark-empty__title">
                            {q ? `Nothing matches “${query.trim()}”` : "No job descriptions yet"}
                          </span>
                          <span className="ark-empty__body">
                            {q ? "Try another job, department or file name." : "The first job opening you create appears here."}
                          </span>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>

          <TablePager total={rows.length} page={currentPage} pageCount={pageCount} noun="document" onPage={setPage} />
        </>
      )}

      {viewing && (
        <VersionTextDialog version={viewing} token={token} onOpenFile={openFile} onClose={() => setViewing(null)} />
      )}

      {replacing && (
        <ReplaceJobDescriptionDialog
          current={replacing}
          token={token}
          onClose={() => setReplacing(null)}
          onReplaced={(created, previous) => {
            setReplacing(null);
            const kept =
              previous.scored_count > 0
                ? ` The ${previous.scored_count} applicant${previous.scored_count === 1 ? "" : "s"} already scored keep${previous.scored_count === 1 ? "s" : ""} version ${previous.version}.`
                : "";
            setNotice(`Version ${created.version} is now in force for ${created.job_title}.${kept}`);
            setQuery("");
            setPage(0);
            load();
          }}
        />
      )}
    </section>
  );
}

/** Read-only: the exact text a version put in force. */
function VersionTextDialog({
  version,
  token,
  onOpenFile,
  onClose,
}: {
  version: JobDescriptionVersion;
  token: string | null;
  onOpenFile: (version: JobDescriptionVersion) => void;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<JobDescriptionVersionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<JobDescriptionVersionDetail>(`/hr/job-descriptions/${version.id}`, { token })
      .then(setDetail)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load this version."));
  }, [version.id, token]);

  const sections: { label: string; text: string | null | undefined }[] = [
    { label: "Role description", text: detail?.description },
    { label: "Qualifications", text: detail?.qualifications },
    { label: "Requirements", text: detail?.requirements },
  ];

  return (
    <Modal
      open
      title={`${version.job_title} · version ${version.version}`}
      sub={
        <>
          {version.is_current ? "In force now" : `Replaced ${shortDate(version.replaced_at ?? version.created_at)}`}
          {" · "}added {shortDate(version.created_at)}
          {version.uploaded_by_name ? ` by ${version.uploaded_by_name}` : ""}
          {" · "}
          {version.scored_count} applicant{version.scored_count === 1 ? "" : "s"} scored against it
        </>
      }
      aside={
        <Tag tone={version.is_current ? "green" : "neutral"} dot>
          {version.is_current ? "Current" : "Replaced"}
        </Tag>
      }
      footer={
        <>
          {version.has_file ? (
            <Button variant="secondary" onClick={() => onOpenFile(version)}>
              <DownloadIcon width={15} height={15} aria-hidden="true" />
              Open document
            </Button>
          ) : (
            <span className="ark-wizard__note" style={{ margin: 0 }}>
              No document was kept for this version
            </span>
          )}
          <div className="ark-wizard__foot-end">
            <Button variant="primary" onClick={onClose}>
              Close
            </Button>
          </div>
        </>
      }
      onClose={onClose}
    >
      {error && <Alert tone="danger" title={error} />}
      {version.change_note && (
        <p className="ark-callout" style={{ marginTop: 0, marginBottom: "var(--space-5)" }}>
          <span>
            <strong>Reason for the change:</strong> {version.change_note}
          </span>
        </p>
      )}
      <div className="ark-jd-text">
        {sections.map((s) => (
          <div key={s.label} className="ark-jd-text__section">
            <p className="ark-jd-text__label">{s.label}</p>
            {detail === null && !error ? (
              <span className="ark-skeleton" style={{ display: "block", height: 12, width: "80%" }} />
            ) : (
              <p className="ark-jd-text__body" data-empty={!s.text || undefined}>
                {s.text || "Not filled in."}
              </p>
            )}
          </div>
        ))}
        {/* Versions saved before sections existed read as none. */}
        <JobSectionsView sections={detail?.additional_sections} loading={detail === null && !error} />
      </div>
    </Modal>
  );
}
