"""Builds docs/ARKIVE-Team-Guide.pdf — the guide handed to teammates so
they can reach the system and exercise every feature of their role.

Regenerate it whenever the host address changes (a different network, or
the router reassigning the IP) or a feature is added:

    backend/venv/bin/python scripts/build_team_guide.py

reportlab used to be kept out of requirements.txt, since only this
script used it. The interview results report (backend/app/services/
interview_report_pdf.py) now does too, so it is installed with the
backend and this runs from the backend's own virtualenv.
"""

# The address teammates type. Private to the host's network, so it changes
# with the network — check with `ipconfig getifaddr en0` and update here.
SITE_ADDRESS = "192.168.1.29"

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

ACCENT   = colors.HexColor("#e63219")
INK900   = colors.HexColor("#2c3437")
INK600   = colors.HexColor("#596064")
INK400   = colors.HexColor("#acb3b7")
BG       = colors.HexColor("#f8fafc")
BORDER   = colors.HexColor("#dfe4e8")
WARN_BG  = colors.HexColor("#fef1ef")

ss = getSampleStyleSheet()
def S(name, **kw):
    base = kw.pop("parent", ss["Normal"])
    return ParagraphStyle(name, parent=base, **kw)

TITLE    = S("t", fontName="Helvetica-Bold", fontSize=30, leading=34, textColor=INK900, spaceAfter=4)
SUB      = S("s", fontName="Helvetica", fontSize=12.5, leading=17, textColor=INK600, spaceAfter=16)
H1       = S("h1", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=INK900, spaceBefore=16, spaceAfter=7)
H2       = S("h2", fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=ACCENT, spaceBefore=12, spaceAfter=5)
BODY     = S("b", fontName="Helvetica", fontSize=9.8, leading=14.5, textColor=INK900, spaceAfter=6)
SMALL    = S("sm", fontName="Helvetica", fontSize=8.6, leading=12.5, textColor=INK600, spaceAfter=4)
CELL     = S("c", fontName="Helvetica", fontSize=8.8, leading=12.5, textColor=INK900)
CELLB    = S("cb", parent=CELL, fontName="Helvetica-Bold")
CELLH    = S("ch", fontName="Helvetica-Bold", fontSize=8.2, leading=11, textColor=colors.white)
MONO     = S("m", fontName="Courier-Bold", fontSize=9.5, leading=13.5, textColor=INK900)
NOTE     = S("n", fontName="Helvetica", fontSize=9, leading=13, textColor=INK900)
STEPN    = S("stepn", fontName="Helvetica-Bold", fontSize=15, leading=17, textColor=ACCENT, alignment=TA_CENTER)


def table(rows, widths, header=True, zebra=True):
    data = []
    for i, r in enumerate(rows):
        style = CELLH if (header and i == 0) else CELL
        data.append([Paragraph(str(c), style) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    cmds = [("VALIGN", (0,0), (-1,-1), "TOP"),
            ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING", (0,0), (-1,-1), 8), ("RIGHTPADDING", (0,0), (-1,-1), 8),
            ("LINEBELOW", (0,0), (-1,-2), 0.4, BORDER),
            ("BOX", (0,0), (-1,-1), 0.6, BORDER)]
    if header:
        cmds += [("BACKGROUND", (0,0), (-1,0), INK900)]
        if zebra:
            for i in range(2, len(rows), 2):
                cmds.append(("BACKGROUND", (0,i), (-1,i), BG))
    t.setStyle(TableStyle(cmds))
    return t


def callout(title, body, tint=WARN_BG, bar=ACCENT):
    inner = [[Paragraph(f"<b>{title}</b>", NOTE)], [Paragraph(body, NOTE)]]
    t = Table(inner, colWidths=[163*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), tint),
        ("LEFTPADDING", (0,0), (-1,-1), 11), ("RIGHTPADDING", (0,0), (-1,-1), 11),
        ("TOPPADDING", (0,0), (0,0), 9), ("BOTTOMPADDING", (0,-1), (-1,-1), 9),
        ("TOPPADDING", (0,1), (-1,1), 2),
        ("LINEBEFORE", (0,0), (0,-1), 2.5, bar),
    ]))
    return t


def steps(items):
    rows = []
    for n, (head, body) in enumerate(items, 1):
        rows.append([Paragraph(str(n), STEPN),
                     Paragraph(f"<b>{head}</b><br/>{body}", BODY)])
    t = Table(rows, colWidths=[11*mm, 152*mm])
    t.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"),
                           ("TOPPADDING", (0,0), (-1,-1), 5),
                           ("BOTTOMPADDING", (0,0), (-1,-1), 9),
                           ("LEFTPADDING", (0,0), (0,-1), 0)]))
    return t


class TeamGuideBuilder:
    """Assembles the story (reportlab's flowable list) for the team guide
    and renders it to a PDF.

    `story` used to be a bare module global that `P`/`SP` closed over and
    every section of the script appended to directly. That was fine for a
    single linear build, but it meant the whole file was really one
    function's worth of state wearing a script's clothes. Folding it into
    an instance turns each section into its own method -- addressable,
    testable in isolation, and no longer able to interfere with a second
    build in the same process."""

    def __init__(self, site_address: str) -> None:
        self.site_address = site_address
        self.story: list = []

    def _p(self, text, style=BODY) -> None:
        self.story.append(Paragraph(text, style))

    def _sp(self, height=6) -> None:
        self.story.append(Spacer(1, height))

    # ============================== COVER ==============================
    def _build_cover(self) -> None:
        self._sp(16)
        self._p("ARKIVE", TITLE)
        self._p("Team Guide &mdash; how to get in, and what every role can do", SUB)
        self.story.append(Table([[""]], colWidths=[163*mm], style=TableStyle(
            [("LINEABOVE", (0,0), (-1,0), 2.5, ACCENT)])))
        self._sp(11)
        self._p("ARKIVE is an AI-assisted recruitment and decision-support system built for the MSEUF "
          "Human Resources Department. It walks an applicant from a job posting through document "
          "screening, an AI skill match, an examination, a chain of interviews, and a final hiring "
          "decision &mdash; recording the evidence behind that decision at every step.")
        self._p("This guide is for the people testing it. It covers how to reach the system, then every "
          "feature available to each of the three roles.")
        self._sp(7)
        self.story.append(callout(
            "Everyone shares one system",
            "You are not each running your own copy. One machine hosts ARKIVE and everybody else "
            "opens it in a browser, so you all see the same data. When one of you acts, the others' "
            "screens update on their own within about 8 seconds &mdash; or immediately when they click "
            "back into their window. <b>You should not need to press refresh.</b>",
            tint=BG, bar=INK900))
        self._sp(12)

    def _build_getting_in_section(self) -> None:
        self._p("1 &nbsp; Getting in", H1)
        self.story.append(steps([
            ("Install the certificate (Windows, once per laptop)",
             "Save the <font face='Courier-Bold'>arkive-root-ca.crt</font> file you were sent somewhere "
             "you can find it, then <b>double-click it</b> and choose <b>Install Certificate</b>. "
             "Pick <b>Current User</b> and click Next. Choose <i>Place all certificates in the "
             "following store</i>, click <b>Browse</b>, select <b>Trusted Root Certification "
             "Authorities</b>, then Next and Finish. Windows will ask you to confirm a security "
             "warning &mdash; that is expected, and you should say yes. You only ever do this once."),
            ("Close the browser completely, then reopen it",
             "Not just the tab &mdash; every window. Chrome and Edge only read the certificate store "
             "when they start, so a browser that was already open will keep refusing the connection "
             "no matter how many times you reload."),
            ("Open the system",
             "Go to <font face='Courier-Bold'>https://" + self.site_address + "/</font> in any browser. "
             "The <b>https</b> matters &mdash; typing the plain address will not work. If the address has "
             "changed, ask for the current one."),
            ("Log in",
             "Use the account for the role you are testing. Every demo account shares the password "
             "<font face='Courier-Bold'>demo-password-123</font>."),
        ]))
        self._sp(4)
        self.story.append(table([
            ["Role", "Email", "What you get"],
            ["Applicant", "applicant@arkive.demo", "Apply for jobs and move through the hiring stages"],
            ["HR Administrator", "hr@arkive.demo", "Full control of postings, pipelines and hiring decisions"],
            ["Evaluator", "depthead@arkive.demo", "Conduct interviews and submit scorecards"],
            ["Evaluator (2nd)", "vp@arkive.demo", "A second interviewer, for multi-round testing"],
        ], [30*mm, 48*mm, 85*mm]))
        self._sp(8)
        self.story.append(callout(
            "If the browser still warns you about the connection",
            "Work through these in order. <b>Did you fully close and reopen the browser?</b> That is "
            "the usual answer. <b>Are you using Firefox?</b> Firefox keeps its own certificate list "
            "and ignores the one Windows manages, so use <b>Chrome or Edge</b> instead. <b>Did the "
            "install land in the right place?</b> Press the Windows key, type "
            "<font face='Courier-Bold'>certmgr.msc</font>, open <i>Trusted Root Certification "
            "Authorities &rarr; Certificates</i> and look for <b>Caddy Local Authority</b>; if it is "
            "not there, the install did not finish.<br/><br/>"
            "You can always click <i>Advanced &rarr; Proceed</i> to carry on without it. The "
            "connection is encrypted either way &mdash; the warning is about who vouched for the "
            "certificate, not about your data being exposed."))
        self._sp(8)
        self.story.append(callout(
            "Only if your laptop is a Mac",
            "Double-click <font face='Courier-Bold'>arkive-root-ca.crt</font>, add it to the "
            "<b>System</b> keychain, then find it in Keychain Access, expand <b>Trust</b>, and set "
            "<i>When using this certificate</i> to <b>Always Trust</b>. Everything else in this guide "
            "is the same.",
            tint=BG, bar=INK600))
        self._sp(10)
        self.story.append(callout(
            "Two things that must be true",
            "The host laptop has to be <b>awake with the system running</b>, and you have to be on "
            "<b>the same wi-fi network</b> as it. The address <font face='Courier-Bold'>" + self.site_address + "</font> "
            "is private &mdash; it exists only on that network, so it will not work from home.",
            tint=BG, bar=INK600))
        self._sp(14)

    # ============================== ROLES ==============================
    def _build_roles_section(self) -> None:
        self._p("2 &nbsp; The three roles", H1)
        self._p("ARKIVE gives each role a different portal. You only ever see what your role is allowed to "
          "see &mdash; an evaluator, for example, sees only the interviews they were personally assigned, "
          "not the whole pipeline.")
        self._sp(4)
        self.story.append(table([
            ["Applicant", "HR Administrator", "Evaluator"],
            ["Browse and search jobs<br/><br/>Apply and upload a r&eacute;sum&eacute;<br/><br/>"
             "Answer pre-screening questions<br/><br/>Pick exam and interview times<br/><br/>"
             "Track their own progress",
             "Create and publish job openings<br/><br/>Design hiring workflows<br/><br/>"
             "Run the candidate pipeline<br/><br/>Record exam and check results<br/><br/>"
             "Assign interviewers<br/><br/>Make the hire or reject decision",
             "See interviews assigned to them<br/><br/>Read the candidate's full profile<br/><br/>"
             "Submit a scored evaluation<br/><br/>Request a different schedule"],
        ], [54*mm, 54*mm, 55*mm]))
        self._sp(12)

        self._p("How a candidate moves through the system", H2)
        self._p("Every job defines its own sequence of stages. A candidate can only ever move forward one "
          "stage at a time, in the order that job specifies &mdash; the system will not let anyone skip "
          "ahead. A typical full workflow looks like this:")
        self._sp(2)
        flow = Table([[Paragraph(x, CELLB)] for x in [
            "Document Upload &nbsp;&rarr;&nbsp; Pre-Screening &nbsp;&rarr;&nbsp; Examination "
            "&nbsp;&rarr;&nbsp; Interview Rounds 1&ndash;3 &nbsp;&rarr;&nbsp; Final Decision "
            "&nbsp;&rarr;&nbsp; Onboarding"]],
            colWidths=[163*mm])
        flow.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), BG),
                                  ("BOX", (0,0), (-1,-1), 0.6, BORDER),
                                  ("TOPPADDING", (0,0), (-1,-1), 10),
                                  ("BOTTOMPADDING", (0,0), (-1,-1), 10),
                                  ("LEFTPADDING", (0,0), (-1,-1), 12)]))
        self.story.append(flow)
        self._sp(14)

    # ============================== APPLICANT ==============================
    def _build_applicant_section(self) -> None:
        self._p("3 &nbsp; Applicant", H1)
        self._p("Log in as <font face='Courier-Bold'>applicant@arkive.demo</font>, or create your own account "
          "from the sign-up link &mdash; a real applicant would.")

        self._p("Finding and applying for a job", H2)
        self._p("The public job board is the landing page, and you do not need an account to look at it. "
          "Search by keyword and filter by department. The search covers the full posting, not just the "
          "title &mdash; searching <b>CCNA</b> finds the Network Administrator role even though those "
          "letters appear nowhere in its title, only deep in its requirements.")
        self._p("Open a posting and choose <b>Apply</b>. You can only apply once per job.")

        self._p("Document Upload", H2)
        self._p("Upload your r&eacute;sum&eacute; as a PDF. An AI agent reads the actual document and fills in "
          "your name, contact details, education, work history and skills for you. <b>Review what it "
          "extracted and correct anything wrong</b> before submitting &mdash; it is a draft for you to "
          "check, not a final answer. You can also add a letter of intent in your own words.")

        self._p("Pre-Screening", H2)
        self._p("Answer the job's screening questions, and choose which examination sittings you are available "
          "for. When you submit, several AI agents run at once: one scores your r&eacute;sum&eacute; "
          "against the job description, one reads your answers, and one proposes an exam booking.")
        self._sp(2)
        self.story.append(callout(
            "If your match score comes back low",
            "Your application is <b>flagged</b> and pauses here. This is not a rejection &mdash; it means "
            "the AI did not find enough overlap between your r&eacute;sum&eacute; and the posting, and a "
            "human has to decide. HR sees the flag and chooses to continue you anyway or to reject. "
            "<b>Worth knowing when testing:</b> the score is calculated from the text inside your uploaded "
            "PDF, not from the fields you edited on screen, so a generic r&eacute;sum&eacute; will score low."))
        self._sp(6)

        self._p("Examination", H2)
        self._p("Once HR confirms your booking you will see the date, time and venue. The exam itself is taken "
          "offline; HR enters your score afterwards. You will then see your score and your percentile "
          "rank against everyone else who sat that exam.")

        self._p("Interviews", H2)
        self._p("Each round shows its schedule once HR sets it. If the time does not work for you, you can ask "
          "for a different one and HR will approve or decline it.")

        self._p("Final steps", H2)
        self._p("When a decision is made you will see the outcome. If you are hired, an onboarding checklist "
          "appears for the requirements you need to submit. You can also withdraw your application at any "
          "point before then.")

        self._p("The notification bell", H2)
        self._p("The bell in the top bar tells you when something happens to your application &mdash; a schedule "
          "set, a decision made. It updates on its own; you do not need to reload.")

        self.story.append(PageBreak())

    # ============================== HR ==============================
    def _build_hr_section(self) -> None:
        self._p("4 &nbsp; HR Administrator", H1)
        self._p("Log in as <font face='Courier-Bold'>hr@arkive.demo</font>. This role has the most to explore &mdash; "
          "the left sidebar is your map.")

        self._p("HR Dashboard", H2)
        self._p("The landing dashboard: how many positions are open, how many candidates are active, and what "
          "needs your attention.")

        self._p("Create Job Opening", H2)
        self._p("A four-step wizard. Name the role, upload the job description as a PDF, and an AI agent reads "
          "the real document to draft the department, description, qualifications and requirements. "
          "<b>Review and edit every field before publishing</b> &mdash; nothing is published without you "
          "approving it. Finally choose the hiring workflow the job will use.")
        self._sp(2)
        self.story.append(callout(
            "That same document does double duty",
            "The job description you upload is also what every applicant's AI match score is calculated "
            "against. A vague posting produces vague scores.",
            tint=BG, bar=INK600))
        self._sp(6)

        self._p("Workflow Builder and Pre-Screening Questions", H2)
        self._p("Choose which stages a job uses &mdash; a senior post might need three interview rounds and an "
          "exam, a part-time role far less &mdash; and write the questions applicants answer during "
          "pre-screening.")
        self._sp(2)
        self.story.append(callout(
            "A short workflow has a real consequence",
            "The final synthesis score is calculated from four criteria. If a job's workflow has no "
            "skill-matching or examination stage, two of those four can never be recorded, and that job "
            "can never produce a final score at all. The candidate's profile says so explicitly rather "
            "than showing a blank &mdash; but it is a deliberate trade-off to be aware of when designing "
            "a workflow."))
        self._sp(6)

        self._p("HR Workflow", H2)
        self._p("Every application in the system, with its current stage, status and AI match score. Search by "
          "candidate or job. <b>Advance</b> moves a candidate to the next stage; the system enforces the "
          "order and will refuse a skip.")

        self._p("The Candidate Profile", H2)
        self._p("Click any candidate to open the most important screen in the system. Seven tabs:")
        self._sp(2)
        self.story.append(table([
            ["Tab", "What it shows"],
            ["Synthesis", "The decision-support summary. The final weighted score, each of the four "
                          "criteria behind it with its weight and actual point contribution, and &mdash; "
                          "when there is no score &mdash; exactly which criteria are missing and whether "
                          "they can ever arrive. Also lists every AI agent that has acted on this "
                          "candidate."],
            ["Overview", "The AI skill-match analysis: score, matched strengths, and gaps against the posting."],
            ["Pre-Screening", "The candidate's own answers, with the AI's reading of them."],
            ["Examinations", "Exam scheduling, booking approval, and where you enter the score."],
            ["Interview Rounds", "Assign an interviewer, set the schedule, approve reschedule requests, "
                                 "and read submitted scorecards."],
            ["Documents", "The r&eacute;sum&eacute;, letter of intent, and anything else submitted."],
        ], [32*mm, 131*mm]))
        self._sp(8)

        self._p("Assigning an interviewer", H2)
        self._p("On the Interview Rounds tab, pick an evaluator for a round. They are notified, and that "
          "interview appears in their queue &mdash; on their screen, without them reloading. An evaluator "
          "only ever sees rounds assigned to them personally.")

        self._p("Final Decision Board", H2)
        self._p("For a given job, every candidate who has finished the interview chain, ranked side by side "
          "with all their scores. The interview rounds are weighted 30/30/40 &mdash; the final round "
          "counts most.")

        self._p("Hiring or rejecting", H2)
        self._p("At the bottom of a candidate profile. <b>You can always hire from any stage</b> &mdash; the "
          "system never blocks the decision, because that call belongs to a person. What it does is make "
          "an incomplete decision deliberate: if the candidate has not been through everything, a dialog "
          "lists exactly what is missing and asks you to confirm and give a reason.")
        self._p("Every decision is recorded permanently: who made it, when, from which stage, the reason given, "
          "and a frozen snapshot of the scores as they stood at that moment.")

        self._p("Pre-Employment Records", H2)
        self._p("Once hired, the candidate's complete record compiled into one file &mdash; r&eacute;sum&eacute;, "
          "exam results, every interview scorecard, the decision record and the scores behind it.")

        self._p("User Management", H2)
        self._p("Invite evaluators and other HR staff by email.")

        self.story.append(PageBreak())

    # ============================== EVALUATOR ==============================
    def _build_evaluator_section(self) -> None:
        self._p("5 &nbsp; Evaluator", H1)
        self._p("Log in as <font face='Courier-Bold'>depthead@arkive.demo</font> or "
          "<font face='Courier-Bold'>vp@arkive.demo</font>. This is the simplest portal &mdash; deliberately.")

        self._p("Review Queue", H2)
        self._p("Every interview assigned to you, showing the candidate, the round, the schedule, and whether "
          "you have already submitted. <b>You will not see candidates you were not assigned</b>, and "
          "nothing appears here until HR assigns you.")

        self._p("Conducting an interview", H2)
        self._p("Open an interview to see the candidate's full background &mdash; r&eacute;sum&eacute;, "
          "pre-screening answers, and the AI's analysis &mdash; then score them on the official "
          "HRD-F-APIEF form across four categories:")
        self._sp(2)
        self.story.append(table([
            ["Category", "Covers"],
            ["Personal Background", "Presentation, communication, personal circumstances relevant to the role"],
            ["Educational Qualifications", "Degrees, training and how relevant they are to this position"],
            ["Work Background", "Experience, achievements and how it maps to the job"],
            ["Job Expectations", "Motivation, salary expectations, fit with the institution"],
        ], [46*mm, 117*mm]))
        self._sp(6)
        self._p("Each item is rated 1 to 5. The system averages them into an overall score and a tier: "
          "<b>Highly Qualified</b> (5), <b>Qualified</b> (3&ndash;4) or <b>Not Qualified</b> (1&ndash;2).")
        self._sp(2)
        self.story.append(callout(
            "Your written remarks genuinely matter",
            "An AI agent reads your remarks and scores how well they actually address the form's "
            "categories. This is measured, not decorative: in testing, one generic paragraph reused "
            "across all three rounds scored <b>27.5 out of 100</b> for coverage, while remarks where each "
            "interviewer addressed the categories from their own perspective scored <b>90</b> &mdash; with "
            "identical numeric ratings. That difference moved the candidate's final score by more than "
            "20 points. Write properly when testing, or the results will look worse than the system is."))
        self._sp(6)
        self._p("If the scheduled time does not work, request a different one. HR approves or declines it, and "
          "you are notified either way.")

    # ============================== TESTING TOGETHER ==============================
    def _build_testing_together_section(self) -> None:
        self._sp(10)
        self._p("6 &nbsp; Testing all three roles together", H1)
        self._p("The most useful thing to try. Three people, three laptops, one system &mdash; watch each "
          "other's actions appear without anyone reloading.")
        self._sp(4)
        self.story.append(table([
            ["#", "Who", "Does this", "Everyone else sees"],
            ["1", "Applicant", "Applies for a job", "It appears in HR's pipeline"],
            ["2", "Applicant", "Uploads a r&eacute;sum&eacute; and letter of intent",
             "HR sees the stage move to Pre-Screening"],
            ["3", "HR", "Publishes an examination sitting", "The applicant can choose it"],
            ["4", "Applicant", "Submits pre-screening", "HR sees the AI match score appear"],
            ["5", "HR", "Records the exam score and advances", "The applicant sees their stage move"],
            ["6", "HR", "Assigns an evaluator to round 1", "It appears in the evaluator's queue"],
            ["7", "Evaluator", "Submits a scorecard", "HR sees the score and tier land"],
            ["8", "HR", "Hires, giving a reason", "The applicant sees the outcome"],
        ], [8*mm, 24*mm, 68*mm, 63*mm]))
        self._sp(10)

    def _build_troubleshooting_section(self) -> None:
        self._p("7 &nbsp; If something looks wrong", H1)
        self.story.append(table([
            ["What you see", "What it means"],
            ["A screen seems out of date",
             "Give it 8 seconds, or click into the window. Screens only pause updating while you have a "
             "form or dialog open, so nothing is overwritten while you type."],
            ["The page will not load at all",
             "The host laptop is asleep or the system is not running, or you are not on the same wi-fi. "
             "The address only exists on that network."],
            ["A browser security warning",
             "The certificate was not installed or trusted. Your connection is encrypted regardless."],
            ["&ldquo;AI extraction is not configured&rdquo;",
             "You are on a local copy rather than the shared system. Use the shared address instead."],
            ["A candidate is stuck and will not advance",
             "They were probably flagged by the AI match. Open their profile &mdash; HR has to choose to "
             "continue or reject before the pipeline moves."],
            ["A final score shows as blank",
             "The Synthesis tab explains why. Either something has not been recorded yet, or this job's "
             "workflow can never produce it."],
        ], [46*mm, 117*mm]))
        self._sp(12)
        self._p("Report anything that behaves differently from this guide &mdash; that is exactly what the "
          "testing is for.", SMALL)

    # ============================== BUILD ==============================
    def _decorate_page(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(INK400)
        canvas.drawString(23*mm, 12*mm, "ARKIVE — Team Guide")
        canvas.drawRightString(A4[0] - 23*mm, 12*mm, f"Page {doc.page}")
        canvas.setStrokeColor(BORDER); canvas.setLineWidth(0.4)
        canvas.line(23*mm, 15.5*mm, A4[0] - 23*mm, 15.5*mm)
        canvas.restoreState()

    def build(self, out_path: str) -> None:
        self._build_cover()
        self._build_getting_in_section()
        self._build_roles_section()
        self._build_applicant_section()
        self._build_hr_section()
        self._build_evaluator_section()
        self._build_testing_together_section()
        self._build_troubleshooting_section()

        doc = BaseDocTemplate(out_path, pagesize=A4,
                              leftMargin=23*mm, rightMargin=23*mm,
                              topMargin=18*mm, bottomMargin=20*mm,
                              title="ARKIVE - Team Guide", author="ARKIVE")
        frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
        doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=self._decorate_page)])
        doc.build(self.story)
        print("wrote", out_path)


if __name__ == "__main__":
    TeamGuideBuilder(SITE_ADDRESS).build("docs/ARKIVE-Team-Guide.pdf")
