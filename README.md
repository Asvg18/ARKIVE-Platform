# ARKIVE

Applicant tracking and evaluation system for MSEUF HR. FastAPI + React,
Postgres, AI pre-screening over LangGraph.

How the code is organised (the frontend's view, model and controller
folders, the backend's layers, and which way imports may point) is in
[docs/ARKIVE-architecture.md](docs/ARKIVE-architecture.md).

To share the source, make the archive from Git rather than zipping the
folder, so `.env` files, uploads and installed packages stay out:

```bash
git archive --format=zip -o ARKIVE-source.zip HEAD
```

## Running it for development

The only prerequisite is **Docker Desktop**. No Python, no venv, no node
— every service runs in a container, so the setup is identical on macOS,
Windows and Linux.

```bash
docker compose up -d --build
```

| | |
|---|---|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Postgres | `localhost:5432` |

Both the API and the frontend hot-reload from the working tree — edit a
file on the host and the running container picks it up. `--build` is
only needed the first time and whenever `requirements.txt` or
`package.json` changes; after that plain `docker compose up -d` is enough.

Database migrations run automatically on every backend start, so there
is no separate `alembic upgrade` step to forget.

### Before the first run

Copy the two example env files and fill in the secrets:

```bash
cp .env.example .env && cp backend/.env.example backend/.env
```

`backend/.env` holds the dev secrets the API reads — `JWT_SECRET_KEY`
and `OPENAI_API_KEY`. The root `.env` holds the Postgres credentials
Compose interpolates. Both are gitignored. `DATABASE_URL` does **not**
need editing for the container stack: Compose overrides it to point at
the `db` service, so the `localhost:5432` value that native runs need
stays correct for them.

### Everyday commands

```bash
docker compose logs -f backend
```

```bash
docker compose exec backend pytest
```

```bash
docker compose exec db psql -U arkive -d arkive
```

```bash
docker compose down
```

`down` stops the stack but keeps the database — the data lives in a
named volume. Add `-v` to wipe it and start from an empty schema.

After changing `requirements.txt` or `package.json`:

```bash
docker compose up -d --build
```

### Sharing data between machines

**By default, nothing is shared.** Containers make the *environment*
reproducible, not the *data*. Postgres writes to a Docker volume on the
local disk (`arkive_arkive_pg_data`, driver `local`, scope `local`), so
every machine that runs the stack gets its own separate database.
Migrations give everyone the same empty schema; the rows are yours alone.

That is usually what you want for development. Three ways to change it:

**Same starting data, separate databases.** Run the seed scripts — this
is the normal way to get a comparable demo state on a new machine:

```bash
docker compose exec backend python -m scripts.seed_demo_users
```

```bash
docker compose exec backend python -m scripts.seed_demo_pipeline
```

**One shared database.** ARKIVE has no hosted database of its own — it
ships with the bundled Postgres container and nothing else is configured.
If you separately set one up with a managed provider (Neon, Supabase and
DigitalOcean all offer Postgres), put its connection string in
`DATABASE_URL` in the root `.env` and every machine points at it; the
bundled `db` container then goes unused. Same override
`docker-compose.prod.yml` accepts. Note this means shared migrations
too — whoever starts the backend first upgrades the schema for everyone.

**Copy a snapshot.** To hand someone your exact current state:

```bash
docker compose exec -T db pg_dump -U arkive arkive > snapshot.sql
```

```bash
docker compose exec -T db psql -U arkive -d arkive < snapshot.sql
```

For a demo where several people use one instance, the on-premises stack
is the better fit — one machine runs everything and the rest reach it
over the LAN. See the deployment guide.

### Running natively instead

The hybrid workflow still works — database in Docker, app on the host:

```bash
docker compose up -d db
```

Then run the API from `backend/` and the frontend from `frontend/`. The
API must start with `backend/` as the working directory — its settings
read `.env` relative to the process cwd, so launching from the repo root
silently loads no config at all.

In VS Code, the **Run Full Stack (Backend + Frontend)** compound in
`.vscode/launch.json` handles both correctly on every OS: it sets that
cwd and picks the right interpreter path per platform (`.venv/bin/python`,
or `.venv\Scripts\python.exe` on Windows). Containers avoid the whole
split, which is why they are the default.

## Deploying

See [docs/ARKIVE-deployment.md](docs/ARKIVE-deployment.md) for the
on-premises stack (`docker-compose.prod.yml`) — Caddy, TLS, and the
static frontend build.
