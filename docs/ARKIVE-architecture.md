# ARKIVE architecture

How the code is organised, what each folder is for, and which way imports may point. Written 28 Oct 2026 from the code as it stands; the import facts below were checked by scanning every import, not assumed.

## The two applications

ARKIVE is two programs that talk over HTTP:

- **frontend/**: a React single-page app (Vite, TypeScript). Everything a person sees.
- **backend/**: a FastAPI JSON API (Python, SQLAlchemy, PostgreSQL). Every rule that must hold, every database write, and every AI call.

The backend sends JSON, never pages, so it is not a classic server-rendered MVC application. MVC is applied to the frontend; the backend keeps a layered design whose layers map onto the same ideas.

## Frontend

### Folders

```text
frontend/src/
├── main.tsx, App.tsx      start-up and the route table
├── styles/, index.css     the stylesheet (.ark-* classes)
├── shared/                code any feature may use; it never imports a feature
│   ├── api/               the HTTP client and the shapes of server data
│   ├── ui/                small design-system pieces (Button, Modal, Tag, icons)
│   ├── components/        larger displays reused by several features (PdfPreview, ScorecardReadOnly)
│   ├── hooks/             generic hooks (useLiveRefresh)
│   └── lib/               generic pure helpers (dates, stage labels, display text)
└── features/
    ├── account/           view/
    ├── applicant/         view/
    ├── auth/              controller/, model/, view/
    ├── evaluator/         view/
    ├── home/              view/
    ├── hr/                controller/, model/, view/
    └── notifications/     model/, view/
```

### What each layer means here

| Layer | Holds | Example |
|---|---|---|
| **view/** | Pages and components that show data and pass on what the user does. Pages live in `view/pages/`, pieces of pages in `view/components/`. | `hr/view/pages/HrPipelinePage.tsx` |
| **controller/** | Code that coordinates state and decides what happens in response to an event, where that logic is shared or substantial enough to stand apart from a screen. Written as React providers and hooks. | `auth/controller/AuthContext.tsx` (the session), `hr/controller/useStageTransition.ts` (moving a candidate between stages) |
| **model/** | Rules, checks and data handling with no screen of their own. Pure functions, unit-tested beside them. | `hr/model/examSessions.ts`, `auth/model/signupValidation.ts` |

A feature has only the layers it needs. Most pages keep their own simple state and their own server calls; splitting each of those into a separate controller file was considered and turned down, because it would add files without making anything easier to find. TypeScript types describe data but do not check it at runtime; the server validates everything it receives.

### Import rules

1. **shared never imports a feature.** Checked: no file under `shared/` imports from `features/`.
2. **Inside a feature, imports point downwards:** view may use controller and model; controller may use model; model uses neither. Checked: no model file imports a view or controller file.
3. **Features use each other only through a few public pieces:**
   - `auth/controller/AuthContext` (`useAuth`): the signed-in session, used by every feature. `AuthProvider` wraps the whole app in `main.tsx`.
   - `auth/model/roleHome`: where each role lands after signing in (used by the home page).
   - `notifications/view/components/NotificationBell`: the bell in each portal's top bar.
   - each portal's shell (`hr/view/components/AppShell`, `evaluator/view/components/EvaluatorAppShell`, `applicant/view/components/ApplicantAppShell`). Only `App.tsx` picks a shell for a page that every role shares: the `/hr`, `/evaluator` and `/applicant` routes for Account Settings and Notifications each pass their own portal's shell to the page, so neither page imports another feature. The route guards already keep each role on its own routes, so the shell always matches the person signed in.
4. **Server data shapes stay in `shared/api/`**, one file per area of the API, so a request is never re-declared inside a feature.

## Backend

### Folders

```text
backend/
├── app/
│   ├── main.py        creates the FastAPI app and mounts the routers
│   ├── api/           HTTP endpoints (api/hr/ and api/applicant/ split by area)
│   ├── services/      use cases: what happens when someone does something
│   │   └── agents/    the AI agents and their shared base
│   ├── domain/        hiring rules that need no database, web or AI library
│   ├── models/        database tables (SQLAlchemy)
│   ├── schemas/       request and response shapes (Pydantic)
│   └── infra/         settings, database session, security, rate limiting, uploads
├── alembic/           database migrations
├── scripts/           admin and evaluation scripts (scripts/eval/ holds the skill-matching evaluation)
└── tests/             pytest suite
```

### What each layer means here

| Folder | Responsibility | Closest MVC role |
|---|---|---|
| `api/` | Receives a request, checks who is asking, calls a service, and turns its result or error into an HTTP response. Simple reads may query the database directly. | Controller |
| `services/` | Use cases and workflows: stage transitions, scheduling, hiring decisions, notifications, email, and the AI pipelines (skill matching, RAG, interview analysis, synthesis). Calls OpenAI through the agents in `services/agents/`. | Model (application logic) |
| `domain/` | Pure hiring rules: the stage DFA, stage requirements, workflow rules, scorecard maths, decision support. No database, web framework or AI library. | Model (business rules) |
| `models/` | Database tables and their columns. `models/enums.py` also holds the shared vocabulary (stage and status names). | Model (persistence) |
| `schemas/` | The exact shape of every request and response, validated on the way in. | The contract between the frontend view and the API |
| `infra/` | Settings (`config`), the database engine and session (`db`), auth dependencies (`deps`), password hashing and tokens (`security`), rate limiting, upload limits. | Plumbing, used by every layer |

A Pydantic schema, a SQLAlchemy model and a domain rule can describe the same thing (an application, say) for different purposes: the schema is what crosses the wire, the model is what is stored, the domain rule is what must be true. They are kept apart on purpose.

### Import rules (enforced by `backend/tests/test_architecture.py`)

- `api` → `services` → `domain`; any layer may use `infra`.
- `domain/` imports nothing from the app except `models/enums`, and none of SQLAlchemy, FastAPI, LangChain, OpenAI or httpx.
- `services/` never imports `api/`.

## Sharing the source code

Make a source archive from Git, not by zipping the folder:

```bash
git archive --format=zip -o ARKIVE-source.zip HEAD
```

It contains only files Git tracks, so it leaves out `.env` files, applicant uploads, `node_modules`, the Python virtual environment, build output, caches, the `.git` history and macOS metadata. A hand-made ZIP of the working folder includes all of those. The zip also leaves out `w/` (marked `export-ignore` in `.gitattributes`). Before sending one, check what is in it:

```bash
unzip -l ARKIVE-source.zip | less
```

`git archive` copies whatever Git tracks; it does not look for secrets. What keeps them out is `.gitignore`, so a file that is already tracked stays in every zip until it is untracked.

## What is kept in Git, and why

| Path | Decision | Why |
|---|---|---|
| `.env`, `backend/.env`, `frontend/.env` | Ignored; each person keeps their own | Keys and passwords. The `.env.example` templates, with placeholders only, are in Git and list every setting. |
| `backend/uploads/` | Ignored | Applicants' uploaded documents: real personal data. |
| `node_modules/`, `.venv/`, `venv/`, `dist/`, caches | Ignored | Installed or built on each machine. |
| `.DS_Store` | Ignored | macOS folder metadata. |
| `.claude/` | Ignored | Each developer's own preview settings for their editor tools. |
| `.vscode/` | Kept in Git | Shared editor settings: test runner, debugger, linter folder. The default Python path is the Windows virtual environment; on macOS pick the interpreter once in VS Code. |
| `arkive-root-ca.crt` | Ignored | The local HTTPS certificate exported from Caddy. It is a public certificate, not a key, but it belongs to one machine's setup; regenerate it with the command in `ARKIVE-deployment.md`. |
| `docs/` | Only the how-tos and the references the code links to are kept: this file, the development guide, the deployment guide, the hosting guide, the skill matching algorithm, the operations notes, `SETUP.pdf` and the Team Guide | Handoff notes, sprint and phase plans, test-case sheets, the manuscript and other working notes stay on the maintainer's machine. `.gitignore` ignores `docs/*` and re-admits each how-to, so a new document must be added there to be shared. |
| `w/` | Kept in Git, left out of source zips | A thesis-document build workspace. No app code uses it; it stays until its owner decides where it belongs. |
| Automated tests (`backend/tests/`, `frontend/src/**/*.test.ts`) | Kept in Git | They check the system still works after a change, and one of them locks the AI prompts. The GitHub project is private. |
