import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../../auth/controller/AuthContext";
import { apiFetch, ApiError } from "../../../../shared/api/client";
import type {
  JDExtractionResult,
  PreScreeningQuestion,
  RequisitionCreateRequest,
  RequisitionDetail,
  WorkflowIssue,
  WorkflowPreset,
} from "../../../../shared/api/pipeline";
import { AppShell } from "../components/AppShell";
import { PageHeader } from "../../../../shared/ui/PageHeader";
import { JobDescriptionLibrary } from "../components/JobDescriptionLibrary";
import { cleanSections } from "../../model/jobSections";
import { type WorkflowStageDraft } from "../../model/workflowStages";
import { interviewDurations } from "../../model/interviewMinutes";
import { makeQuestion } from "../../model/preScreeningQuestions";
import {
  EMPTY_EXTRACTION,
  PUBLISH_STEP,
  QUESTIONS_STEP,
  TEXT_FIELDS,
  WORKFLOW_STEP,
  presetRoundLabels,
  presetStages,
  type Source,
  type TextField,
} from "./job-opening-builder/builderModel";
import { Stepper } from "./job-opening-builder/wizard";
import { TitleStep } from "./job-opening-builder/TitleStep";
import { DescriptionStep } from "./job-opening-builder/DescriptionStep";
import { ReviewDetailsStep } from "./job-opening-builder/ReviewDetailsStep";
import { WorkflowStep } from "./job-opening-builder/WorkflowStep";
import { QuestionsStep } from "./job-opening-builder/QuestionsStep";
import { PublishStep } from "./job-opening-builder/PublishStep";

/**
 * HR types the job title and uploads the JD as a PDF — department,
 * description, qualifications, and requirements are extracted from the
 * real document text via a real GPT-4o-mini call (POST
 * /hr/requisitions/extract-jd, see backend/app/services/jd_extraction.py).
 * HR reviews and can edit every extracted field, and sets the application
 * deadline, before publishing.
 *
 * The job's stages and its pre-screening questions are set here too,
 * before the job exists: HR saves the
 * workflow in its own step, writes the questions when the workflow has
 * Pre-Screening, and can only publish a complete job. A draft can be
 * saved from the workflow step on, complete or not.
 *
 * Laid out as a centred wizard rather than a column pinned to the left:
 * the page has one job at a time, so the steps, the panel and its
 * actions share one centre line, and each step's actions sit in the
 * panel's footer where the eye ends up after the last field.
 */
export function JobOpeningBuilderPage() {
  const { token } = useAuth();
  const navigate = useNavigate();

  const [step, setStep] = useState(0);
  const [source, setSource] = useState<Source>("upload");
  const [fromUpload, setFromUpload] = useState(false);
  const [title, setTitle] = useState("");
  const [jdFile, setJdFile] = useState<File | null>(null);
  /** The file the current extraction came from. Going back a step and
   *  forward again with the same file then continues with what was
   *  already drafted (and edited), instead of paying for a second read
   *  that would overwrite those edits. */
  const [extractedFile, setExtractedFile] = useState<File | null>(null);
  /** The server's id for the PDF the current draft was read from (it now
   *  keeps the file), sent on create so version 1 holds the document. */
  const [jdUploadId, setJdUploadId] = useState<string | null>(null);
  /** Fields the AI came back empty for — flagged on the review step so
   *  HR sees where the document was silent, not just a blank box. */
  const [missingFromPdf, setMissingFromPdf] = useState<TextField[]>([]);
  const [extraction, setExtraction] = useState<JDExtractionResult | null>(null);
  const [applicationDeadline, setApplicationDeadline] = useState("");
  const [preset, setPreset] = useState<WorkflowPreset>("standard");
  const [stages, setStages] = useState<WorkflowStageDraft[]>(() => presetStages("standard"));
  const [roundLabels, setRoundLabels] = useState<Record<string, string>>(() => presetRoundLabels("standard"));
  const [examLabels, setExamLabels] = useState<Record<string, string>>({});
  const [workflowIssues, setWorkflowIssues] = useState<WorkflowIssue[]>([]);
  const [questions, setQuestions] = useState<PreScreeningQuestion[]>(() => [makeQuestion()]);
  const [pending, setPending] = useState<"publish" | "draft" | null>(null);
  const [error, setError] = useState<string | null>(null);
  /** The same title is already live in this department (409
   *  duplicate_job) — shown under the title, where it can be changed. */
  const [titleError, setTitleError] = useState<string | null>(null);

  const stageTypes = stages.map((s) => s.stageType);
  const needsQuestions = stageTypes.includes("skill_matching");
  const writtenQuestions = questions
    .map((q) => ({ ...q, text: q.text.trim() }))
    .filter((q) => q.text.length > 0);
  const workflowErrors = workflowIssues.filter((i) => i.severity === "error");
  // What still stands between this job and publishing -- the same three
  // things the server checks (app.domain.publish_rules), listed on the
  // last step. The server stays the authority; this is the courtesy.
  const publishGaps = [
    ...(applicationDeadline.trim() ? [] : ["Set an application deadline (Review Details)."]),
    ...(stages.length === 0 ? ["Add the workflow's stages."] : []),
    ...workflowErrors.map((i) => i.message),
    ...(needsQuestions && writtenQuestions.length === 0 ? ["Write at least one pre-screening question."] : []),
  ];

  // The Workflow step is long; moving on from its foot would otherwise
  // land HR mid-way down the next step. Only scrolls when the steps bar
  // is out of view, so short steps don't jump.
  const wizardRef = useRef<HTMLDivElement>(null);
  const firstStep = useRef(true);
  useEffect(() => {
    if (firstStep.current) {
      firstStep.current = false;
      return;
    }
    const top = wizardRef.current?.getBoundingClientRect().top ?? 0;
    if (top < 0) wizardRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [step]);

  function choosePreset(id: WorkflowPreset) {
    setPreset(id);
    setStages(presetStages(id));
    setRoundLabels(presetRoundLabels(id));
    setExamLabels({});
  }

  async function handleSubmit(publish: boolean) {
    if (!extraction) return;
    const fromDocument = jdFile != null && jdFile === extractedFile;
    setPending(publish ? "publish" : "draft");
    setError(null);
    try {
      const body: RequisitionCreateRequest = {
        title: title.trim(),
        department: extraction.department.trim(),
        description: extraction.description.trim() || null,
        qualifications: extraction.qualifications.trim() || null,
        requirements: extraction.requirements.trim() || null,
        additional_sections: cleanSections(extraction.additional_sections),
        // Only when the text was actually drafted from this file: a job
        // typed by hand shouldn't claim a document it never came from.
        jd_filename: fromDocument ? jdFile.name : null,
        jd_upload_id: fromDocument ? jdUploadId : null,
        application_deadline: applicationDeadline || null,
        workflow_definition: stageTypes,
        interview_round_labels: roundLabels,
        examination_labels: examLabels,
        interview_durations: interviewDurations(stages),
        // Blank rows are dropped rather than sent; a workflow without
        // Pre-Screening keeps none.
        pre_screening_questions: needsQuestions ? writtenQuestions : [],
        publish,
      };
      const created = await apiFetch<RequisitionDetail>("/hr/requisitions", { method: "POST", token, body });
      navigate(`/hr/job-openings/${created.id}`);
    } catch (err) {
      const code = err instanceof ApiError ? (err.detail as { code?: unknown } | null)?.code : undefined;
      if (code === "duplicate_job") {
        setTitleError(err instanceof ApiError ? err.message : null);
        setStep(0);
      } else {
        setError(err instanceof ApiError ? err.message : "Failed to create job opening.");
      }
    } finally {
      setPending(null);
    }
  }

  function writeByHand() {
    // Keeps whatever is already in the form: switching to the manual path
    // after a read (or after going back a step) must not wipe it.
    setExtraction((current) => current ?? EMPTY_EXTRACTION);
    setFromUpload(false);
    setMissingFromPdf([]);
    setSource("manual");
    setStep(2);
  }

  return (
    <AppShell>
      <div className="ark-wizard" ref={wizardRef}>
        <PageHeader
          title="Create Job Opening"
          info={{
            summary:
              "Name the role and add its job description. Upload the PDF and ARKIVE reads it to draft the details, or write them yourself.",
            points: [
              "Every drafted field stays editable before anything is saved.",
              "The job description is what each applicant's match score is measured against.",
              "The workflow and, when it has Pre-Screening, the questions are set here too. Publishing needs all of it; a draft doesn't.",
              "Candidates can only apply once the opening is published. Until then it can wait as a draft.",
            ],
          }}
        />

        <Stepper current={step} onJump={setStep} skipped={needsQuestions ? [] : [QUESTIONS_STEP]} />

        <div className="ark-wizard__panel">
          {/* Keyed by step, so each step settles in rather than snapping. */}
          <div key={step} className="ark-wizard__stage">
            {step === 0 && (
              <TitleStep
                title={title}
                error={titleError}
                onChange={(value) => {
                  setTitle(value);
                  setTitleError(null);
                }}
                onNext={() => setStep(1)}
              />
            )}
            {step === 1 && (
              <DescriptionStep
                title={title}
                source={source}
                onSourceChange={setSource}
                file={jdFile}
                extractedFile={extractedFile}
                token={token}
                onSelect={setJdFile}
                onExtracted={(file, { jd_upload_id, ...fields }) => {
                  setExtraction({ ...fields, additional_sections: fields.additional_sections ?? [] });
                  setExtractedFile(file);
                  setJdUploadId(jd_upload_id);
                  setMissingFromPdf(TEXT_FIELDS.filter((k) => fields[k].trim() === ""));
                  setFromUpload(true);
                  setStep(2);
                }}
                onContinue={() => {
                  setFromUpload(true);
                  setStep(2);
                }}
                onManual={writeByHand}
                onBack={() => setStep(0)}
              />
            )}
            {step === 2 && extraction && (
              <ReviewDetailsStep
                title={title}
                token={token}
                extraction={extraction}
                onChange={setExtraction}
                applicationDeadline={applicationDeadline}
                onDeadlineChange={setApplicationDeadline}
                onNext={() => setStep(3)}
                onBack={() => setStep(1)}
                fromUpload={fromUpload}
                fileName={jdFile?.name ?? null}
                missingFromPdf={missingFromPdf}
              />
            )}
            {step === WORKFLOW_STEP && extraction && (
              <WorkflowStep
                preset={preset}
                onPresetChange={choosePreset}
                stages={stages}
                onStagesChange={setStages}
                roundLabels={roundLabels}
                onRoundLabelsChange={setRoundLabels}
                examLabels={examLabels}
                onExamLabelsChange={setExamLabels}
                onIssuesChange={setWorkflowIssues}
                canSave={stages.length > 0 && workflowErrors.length === 0}
                pending={pending}
                error={error}
                onBack={() => setStep(2)}
                onSave={() => setStep(needsQuestions ? QUESTIONS_STEP : PUBLISH_STEP)}
                onSaveDraft={() => handleSubmit(false)}
              />
            )}
            {step === QUESTIONS_STEP && extraction && (
              <QuestionsStep
                questions={questions}
                onChange={setQuestions}
                complete={writtenQuestions.length > 0 && writtenQuestions.length === questions.length}
                pending={pending}
                error={error}
                onBack={() => setStep(WORKFLOW_STEP)}
                onNext={() => setStep(PUBLISH_STEP)}
                onSaveDraft={() => handleSubmit(false)}
              />
            )}
            {step === PUBLISH_STEP && extraction && (
              <PublishStep
                title={title.trim()}
                department={extraction.department.trim()}
                applicationDeadline={applicationDeadline}
                stages={stageTypes}
                roundLabels={roundLabels}
                examLabels={examLabels}
                questionCount={needsQuestions ? writtenQuestions.length : null}
                gaps={publishGaps}
                pending={pending}
                error={error}
                onBack={() => setStep(needsQuestions ? QUESTIONS_STEP : WORKFLOW_STEP)}
                onPublish={() => handleSubmit(true)}
                onSaveDraft={() => handleSubmit(false)}
              />
            )}
          </div>
        </div>
      </div>

      {/* Every job description on record, under the upload that adds
          them — which job each belongs to, its versions, and the way to
          replace one when a job's description changes. Outside the
          wizard's column, at the page's full width, so the table has
          room for its columns. */}
      <JobDescriptionLibrary token={token} />
    </AppShell>
  );
}
