import { Navigate, Route, Routes } from "react-router-dom";
import { RequireRole } from "./features/auth/controller/RequireRole";
import { useAuth } from "./features/auth/controller/AuthContext";
import { LoginPage } from "./features/auth/view/pages/LoginPage";
import { SignupPage } from "./features/auth/view/pages/SignupPage";
import { AcceptInvitePage } from "./features/auth/view/pages/AcceptInvitePage";
import { HomePage } from "./features/home/view/pages/HomePage";
import { HrCommandCenterPage } from "./features/hr/view/pages/HrCommandCenterPage";
import { HrPipelinePage } from "./features/hr/view/pages/HrPipelinePage";
import { CandidateProfilePage } from "./features/hr/view/pages/candidate-profile/CandidateProfilePage";
import { JobOpeningBuilderPage } from "./features/hr/view/pages/JobOpeningBuilderPage";
import { JobOpeningsPage } from "./features/hr/view/pages/JobOpeningsPage";
import { JobOpeningDetailPage } from "./features/hr/view/pages/JobOpeningDetailPage";
import { WorkflowBuilderPage } from "./features/hr/view/pages/WorkflowBuilderPage";
import { UserManagementPage } from "./features/hr/view/pages/UserManagementPage";
import { PreScreeningQuestionsPage } from "./features/hr/view/pages/PreScreeningQuestionsPage";
import { FinalDecisionBoardPage } from "./features/hr/view/pages/FinalDecisionBoardPage";
import { Pre201PackagePage } from "./features/hr/view/pages/candidate-profile/Pre201PackagePage";
import { ApplicantDashboardPage } from "./features/applicant/view/pages/ApplicantDashboardPage";
import { ApplicationStagePage } from "./features/applicant/view/pages/ApplicationStagePage";
import { ReviewSubmissionPage } from "./features/applicant/view/pages/ReviewSubmissionPage";
import { ReviewQueuePage } from "./features/evaluator/view/pages/ReviewQueuePage";
import { InterviewDetailPage } from "./features/evaluator/view/pages/InterviewDetailPage";
import { ForgotPasswordPage } from "./features/auth/view/pages/ForgotPasswordPage";
import { ResetPasswordPage } from "./features/auth/view/pages/ResetPasswordPage";
import { ConfirmEmailPage } from "./features/auth/view/pages/ConfirmEmailPage";
import { VerifyEmailPage } from "./features/auth/view/pages/VerifyEmailPage";
import { AccountSettingsPage } from "./features/account/view/pages/AccountSettingsPage";
import { ApplicantJobsPage } from "./features/applicant/view/pages/ApplicantJobsPage";
import { NotificationsPage } from "./features/notifications/view/pages/NotificationsPage";
import { AppShell } from "./features/hr/view/components/AppShell";
import { EvaluatorAppShell } from "./features/evaluator/view/components/EvaluatorAppShell";
import { ApplicantAppShell } from "./features/applicant/view/components/ApplicantAppShell";
import { HelpPage } from "./features/help/view/pages/HelpPage";

/** The public job board, for everyone but HR. An HR admin has nothing to
 *  apply to there and runs the postings from their own console, so a
 *  signed-in one arriving at "/" (typing the address, an old bookmark,
 *  the catch-all below) goes straight to the Command Center instead.
 *  Each job's posting is readable on its own page under Job Openings. */
function PublicHome() {
  const { user } = useAuth();
  if (user?.role === "hr_admin") return <Navigate to="/hr" replace />;
  return <HomePage />;
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<PublicHome />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/accept-invite/:token" element={<AcceptInvitePage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password/:token" element={<ResetPasswordPage />} />
      <Route path="/confirm-email/:token" element={<ConfirmEmailPage />} />
      <Route path="/verify-email/:token" element={<VerifyEmailPage />} />
      {/* Open to everyone: it picks the reader's own portal shell, or a
          plain one when nobody is signed in (HelpPage). */}
      <Route path="/help" element={<HelpPage />} />

      <Route element={<RequireRole allowed={["applicant"]} />}>
        <Route path="/applicant" element={<ApplicantDashboardPage />} />
        <Route path="/applicant/applications/:id" element={<ApplicationStagePage />} />
        <Route path="/applicant/applications/:id/review" element={<ReviewSubmissionPage />} />
        <Route path="/applicant/account" element={<AccountSettingsPage shell={ApplicantAppShell} />} />
        <Route path="/applicant/jobs" element={<ApplicantJobsPage />} />
        <Route
          path="/applicant/notifications"
          element={<NotificationsPage shell={ApplicantAppShell} role="applicant" />}
        />
      </Route>

      <Route element={<RequireRole allowed={["hr_admin"]} />}>
        <Route path="/hr" element={<HrCommandCenterPage />} />
        <Route path="/hr/pipelines" element={<HrPipelinePage />} />
        <Route path="/hr/applications/:id" element={<CandidateProfilePage />} />
        <Route path="/hr/requisitions/new" element={<JobOpeningBuilderPage />} />
        <Route path="/hr/job-openings" element={<JobOpeningsPage />} />
        <Route path="/hr/job-openings/:id" element={<JobOpeningDetailPage />} />
        <Route path="/hr/workflow-builder" element={<WorkflowBuilderPage />} />
        <Route path="/hr/requisitions/:id/workflow" element={<WorkflowBuilderPage />} />
        <Route path="/hr/user-management" element={<UserManagementPage />} />
        <Route path="/hr/pre-screening-questions" element={<PreScreeningQuestionsPage />} />
        <Route path="/hr/requisitions/:id/pre-screening-questions" element={<PreScreeningQuestionsPage />} />
        <Route path="/hr/requisitions/:id/final-decision-board" element={<FinalDecisionBoardPage />} />
        <Route path="/hr/applications/:id/pre-201-package" element={<Pre201PackagePage />} />
        <Route path="/hr/account" element={<AccountSettingsPage shell={AppShell} />} />
        <Route path="/hr/notifications" element={<NotificationsPage shell={AppShell} role="hr" />} />
      </Route>

      <Route element={<RequireRole allowed={["evaluator"]} />}>
        <Route path="/evaluator" element={<ReviewQueuePage />} />
        <Route path="/evaluator/interviews/:id" element={<InterviewDetailPage />} />
        <Route path="/evaluator/account" element={<AccountSettingsPage shell={EvaluatorAppShell} />} />
        <Route path="/evaluator/notifications" element={<NotificationsPage shell={EvaluatorAppShell} role="evaluator" />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
