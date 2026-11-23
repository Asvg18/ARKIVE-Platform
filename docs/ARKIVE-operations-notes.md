# ARKIVE operations notes

Why some runtime settings are the way they are, with the incident or measurement behind each. The code keeps a short comment and links here. Setup and deployment steps are in `ARKIVE-development-guide.md` and `ARKIVE-deployment.md`.

## Database connection pool (`backend/app/infra/db.py`)

**Settings:** `pool_pre_ping=True`, `pool_recycle=300`.

**The incident.** On every machine running the stack, the backend worked and then failed after a while with `OperationalError`, and the page's Retry button seemed to work at random.

**Cause.** Postgres runs inside the Docker VM and the backend on the host, so connections cross Docker's port forwarding. That forwarding silently drops TCP connections idle for a few minutes. Postgres never notices (`idle_session_timeout` is 0), and neither did SQLAlchemy: it kept the dead socket in its pool and handed it to the next request. The pool holds several connections, so a retry drew a live or a dead one by chance.

**Fix.** `pool_pre_ping` runs a cheap `SELECT 1` before handing out a connection and replaces it if the check fails. `pool_recycle` retires connections before they are old enough to be dropped, so the ping rarely has to repair anything.

**Verified** by killing every idle connection on the server side: requests returned 500 before the change and 200 after.

**Before changing either setting,** test against the Docker setup above, not only a local Postgres.

## AI clients created once per process (`backend/app/services/skill_matching/__init__.py`)

The OpenAI embedding and chat clients are module-level, created on first use and reused. Each construction opens its own HTTP connection pool, so a client per request paid a fresh TLS handshake every time: 9.88 s cold against 4.35 s warm in the NFR-01 response-time measurement. `warm_up()` creates them at start-up.

## Query expansion (`rag_query_expansion` in `backend/app/infra/config.py`)

Off by default. On the labelled set (18 Oct 2026) it gave no measurable gain with skill matching v3 (76.1% agreement on against 75.8% off, the same weighted κ of 0.66) and was worse with v2 (66.0% against 69.6%), while adding about 12 seconds per applicant on a request the applicant is waiting for. Full table: `backend/scripts/eval/RESULTS.md`. Method: `docs/ARKIVE-skill-matching-algorithm.md`, section 2.

## Allowed browser origins (`cors_origins` in `backend/app/infra/config.py`)

Comma-separated in `.env`. It replaced an address hard-coded to the Vite dev server in `main.py`, which made the app unreachable from any machine but the one running it. Links in emails use `app_base_url`, or the first allowed origin when that is unset.
