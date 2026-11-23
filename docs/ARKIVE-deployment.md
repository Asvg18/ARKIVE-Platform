# ARKIVE — On-Premises Deployment

*Written 2026-08-30. Every command here was run and verified on the development machine; the numbers and outputs quoted are real, not illustrative.*

This is the deployment that closes **NFR-03 (encryption in transit)** — the only NFR that `docs/ARKIVE-nfr-evidence.md` recorded as a genuine gap. It runs entirely on one machine with nothing leaving the network, which keeps the thesis's **on-premises** claim literally true.

---

## 1. What this stack is

Four containers, one command:

```
                     browser
                        │  HTTPS (:443)
                        ▼
                  ┌───────────┐
                  │   Caddy   │  terminates TLS, serves the built SPA,
                  │  (proxy)  │  proxies /api/* to the backend
                  └─────┬─────┘
                        │  HTTP, container network only
                        ▼
                  ┌───────────┐        ┌──────────────┐
                  │  backend  │───────▶│  PostgreSQL  │
                  │ (FastAPI) │        │      16      │
                  └───────────┘        └──────────────┘
```

Plus a `frontend-build` container that compiles the React app into a shared volume and exits. **`docker compose ps` showing it as `Exited (0)` is the success case**, not a failure.

Two design points worth knowing:

- **TLS is terminated in the proxy, never inside FastAPI.** That is the standard shape, and the NFR-03 evidence note already said as much — this supplies the proxy that note assumed would exist. There is no TLS code in the application.
- **The SPA and the API are served from one origin.** Caddy serves the app at `/` and proxies `/api/*` to the backend, stripping the prefix (so `/api/auth/login` arrives as `/auth/login`). The browser therefore never makes a cross-origin request and **CORS is not involved at all** in this deployment.

---

## 2. Before you start

You need Docker running (Colima on this machine — `colima start` if it isn't) and a `.env` in the repo root. Copy `.env.example` and fill in:

```bash
cp .env.example .env
```

| Variable | What to put |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Anything; they only matter inside the container network |
| `ARKIVE_SITE_ADDRESS` | `localhost` for one machine, or the host's LAN IP (e.g. `192.168.1.42`) so others can reach it |
| `JWT_SECRET_KEY` | **Generate a real one.** `python -c "import secrets; print(secrets.token_hex(32))"` — do not reuse the dev default |
| `OPENAI_API_KEY` | Required, or the AI agents return errors instead of scores |

---

## 3. Bring it up

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The first build takes a few minutes (the backend installs LangChain and friends). Afterwards:

```bash
docker compose -f docker-compose.prod.yml ps
```

Expect `db`, `backend` and `caddy` **Up (healthy)**, and `frontend-build` **Exited (0)**.

Database migrations run automatically — the backend's entrypoint executes `alembic upgrade head` before starting uvicorn, so the schema can never be a step someone forgets.

> **The production stack is deliberately separate from development.** `docker-compose.prod.yml` pins `name: arkive-prod` and uses its own volumes. This is **not optional**: Compose derives a project name from the directory when none is given, so without that line both compose files claim the same project, and bringing this stack up *replaces the development database container* and points it at a different volume. The dev data survives, but the dev server loses its database until `docker compose up -d` is run again. This was found the hard way while writing this document.

### Seeding demo data

The production database starts empty. To populate it:

```bash
docker exec arkive-prod-backend-1 python -m scripts.seed_demo_users
docker exec arkive-prod-backend-1 python -m scripts.seed_demo_pipeline
docker exec arkive-prod-backend-1 python -m scripts.seed_golden_path
```

The third one drives the **real routers with real agents** — it makes live OpenAI calls and takes a minute or two. Verified output on this machine:

```
Golden candidate: application 3 — Marco Villanueva
  final_synthesis_score = 83.2  tier=qualified
  criteria 4/4 available
  agent runs logged: 10
  decision: hired by Harper Administrator at Final Decision (acknowledged_incomplete=False)
```

That last line is worth pointing at during a demo: the hire gate ran in production and this candidate **cleared it unassisted** — the only one in the database complete enough to do so.

All demo users share the password `demo-password-123`.

That makes the demo accounts **for demos and testing only** — a password written in this document is a default credential, and a real installation must not carry one. The demo's HR admin (`hr@arkive.demo`) is a super admin, as every installation's first HR admin is.

### The first super admin (a real installation)

A real installation starts with **no accounts at all**, and applicant sign-up can only ever make applicants — so nobody could open User Management to invite anyone. Instead of the demo seed, whoever installs ARKIVE runs this **once**, with the email of the person who will run HR's accounts (normally the head of the HR office):

```bash
docker exec -it arkive-prod-backend-1 python -m scripts.create_first_admin hr.head@example.edu
```

- It sets **no password**. It sends the same invitation email every staff member receives; the new super admin opens it and chooses their own. If mail is not set up, it prints the link instead, to pass on by hand.
- Once a super admin exists it **refuses to run again**, and names who the super admins are — from then on User Management is where accounts are made. `--again` overrides that (it asks for `YES` first): the emergency key if every super admin is locked out, and how the team re-runs "day one" while testing.
- If the email already belongs to an HR admin, they are simply made a super admin.
- The workshop equivalent, from `backend/` with the venv active: `python -m scripts.create_first_admin hr.head@example.edu`

**First things the new super admin should do:** make a second super admin (so one person being away cannot lock HR out), then invite the rest of HR as *HR Admin* and the interviewers as *Evaluator*. Any valid email address works for staff, personal or the institution's own.

---

## 4. The certificate — read this before the demo

Caddy issues a **real certificate from its own local certificate authority** (`tls internal`). The encryption is genuine — verified `ssl_verify_result: 0` once the CA is trusted — but that CA is not one browsers ship with, so **an untrusted machine shows a security warning**.

This is the honest trade-off of on-premises HTTPS on a private address: public CAs like Let's Encrypt cannot issue certificates for `localhost` or a LAN IP, because they cannot verify ownership of an address that isn't on the internet.

**Do this before the defense, not during it.** Export the CA once:

```bash
docker exec arkive-prod-caddy-1 cat /data/caddy/pki/authorities/local/root.crt > arkive-root-ca.crt
```

Then trust it on each machine that will view the demo:

- **macOS** — double-click `arkive-root-ca.crt`, add to the **System** keychain, open it in Keychain Access, expand **Trust**, set *When using this certificate* to **Always Trust**.
- **Windows** — double-click → *Install Certificate* → **Local Machine** → *Place all certificates in the following store* → **Trusted Root Certification Authorities**.
- **Verify it worked:** `curl -I https://localhost/` with no `-k` flag. No error means the certificate is trusted.

The CA is valid for ten years (verified: `notAfter=Jul 8 2036`), and the `arkive_caddy_data` volume persists it across restarts — so this is a one-time step per machine, not per demo.

If you cannot install certificates on the panel's machines, clicking through the browser warning still gives you a fully encrypted connection. Say so plainly if asked rather than pretending the warning isn't there: **the warning is about certificate provenance, not about whether the traffic is encrypted.**

### If the host machine's address changes, the certificate does not follow it

**Check this whenever the host has been on a different network, and before every demo.** Caddy issues the certificate for whatever `ARKIVE_SITE_ADDRESS` said at the time and then keeps it in the `arkive_caddy_data` volume. Change networks and the machine gets a new address, but the stored certificate still names the old one — so the certificate is now for an address nobody visits.

**This was live on 2026-09-21**: the setting said `192.168.1.29`, `ipconfig getifaddr en0` reported `192.168.1.116`, and the stored certificate carried `IP Address:192.168.1.29` as its only name.

**The reason it is easy to miss is that it punishes the people who followed §4 correctly.** Anyone who skipped the root CA sees the usual provenance warning, clicks through as always, and never learns anything is wrong. Anyone who *did* install the root CA gets a different and unskippable error:

```
curl: (60) SSL: no alternative certificate subject name matches target ipv4 address '192.168.1.116'
```

The site itself is fine throughout — it answers `200` the whole time. Only verification fails, so nothing in the logs or the container status looks wrong.

**One setting fixes both halves**, because the `Caddyfile` uses `ARKIVE_SITE_ADDRESS` twice: once to decide which certificate to issue, and once as `default_sni` to decide which certificate to *present* when a browser sends no name (see the SNI note in §5). A stale value poisons both.

1. `ipconfig getifaddr en0` — get the address the machine actually has now.
2. Set `ARKIVE_SITE_ADDRESS` in the root `.env` to that value.
3. `docker compose -f docker-compose.prod.yml up -d` — Caddy issues a fresh certificate for the new address.
4. Verify with **no** `-k`: `curl -I --cacert arkive-root-ca.crt https://<that-address>/`

**Nobody has to reinstall anything.** The signing authority is unchanged — only the certificate under it is reissued — so every machine that already trusts the root CA keeps working.

**`APP_BASE_URL` is derived from this same setting**, so a stale address also means every password-reset and invitation email links to an address that no longer exists. That failure is invisible from here: the send succeeds and the log says sent. It only fails in somebody else's inbox.

---

## 5. Letting other machines connect (LAN)

**This is the answer to "my teammate can't create a job opening."** They were each running their own copy of the backend, and `backend/.env` is gitignored — so cloning the repo gives them `.env.example` with `OPENAI_API_KEY=` empty, and the AI extraction endpoint correctly refuses with *"AI extraction is not configured."* Worse, each copy also had its own database, so nothing anyone created was visible to anyone else.

The fix is not to send them the key. It is to stop them running their own copy: **one machine runs ARKIVE, everyone else opens a browser.** One key, one database, and the key never leaves the host machine.

1. Find the host's LAN address — `ipconfig getifaddr en0` on macOS.
2. Set `ARKIVE_SITE_ADDRESS` in `.env` to that address.
3. `docker compose -f docker-compose.prod.yml up -d` to pick it up.
4. Give each teammate the root CA (§4) and have them visit `https://<that-address>/`.

**Verified on this machine at `192.168.1.29`** *(on 2026-08-30, commit `e16b3b6` — the host has since moved to a different address; that is a live issue, see §4's subsection on it. The verification itself still stands; the address in it no longer does.)*: HTTPS 200, login over TLS, and — the feature that was failing — a real JD PDF posted to `/api/hr/requisitions/extract-jd` returned **HTTP 200 with department, description, qualifications and requirements all extracted by the live agent**.

> **A bare IP needs `default_sni`, and the failure looks nothing like the cause.** SNI is how a client tells the server which hostname it wants, and RFC 6066 forbids putting an IP literal in it — so a browser opening `https://<a bare LAN IP>/` sends **no SNI at all**, Caddy has nothing to match a certificate against, and the handshake dies with `tlsv1 alert internal error` **even though the log says the certificate was obtained successfully**. The `Caddyfile`'s global block sets `default_sni {$ARKIVE_SITE_ADDRESS}` to name what to assume when SNI is absent. Harmless for hostname deployments. Without it, everything looks correct and nothing connects.

**Test this on a phone hotspot before relying on campus wifi.** Many institutional networks enable client isolation, which blocks laptop-to-laptop traffic entirely — no amount of configuration on this side fixes that, and finding out during the defense would be bad.

### Rotating the OpenAI key

The key lives in exactly one place for this deployment — `OPENAI_API_KEY` in the repo-root `.env`. To swap it:

```bash
# edit .env, then:
docker compose -f docker-compose.prod.yml up -d backend
```

Nothing else changes and no teammate has to do anything. Note the root `.env` and `backend/.env` are separate files: the first feeds the deployment, the second feeds the local dev server.

---

## 6. Everyday commands

```bash
# Watch the logs
docker compose -f docker-compose.prod.yml logs -f backend

# Rebuild after a code change
docker compose -f docker-compose.prod.yml up -d --build

# Stop (data is kept)
docker compose -f docker-compose.prod.yml down

# Stop AND delete all production data, including uploaded resumes
docker compose -f docker-compose.prod.yml down -v
```

`down -v` is the destructive one. `arkive_uploads` holds real applicant resumes and documents.

---

## 7. What this does and does not claim

**Closes NFR-03.** Traffic between the browser and the application is encrypted with TLS. Update `docs/ARKIVE-nfr-evidence.md` to reflect this rather than leaving the old "not satisfied" line standing.

**Does not make the system internet-facing.** That is deliberate — the thesis specifies on-premises. Nothing here is exposed beyond the machine or its LAN.

**Is not hardened for public production.** No rate limiting, no WAF, no secret manager, no backup schedule, no intrusion detection. That was explicitly recommended against for a capstone, and it remains the right call. If asked, the honest answer is that this is a correctly-shaped deployment for its stated scope, not a production hardening exercise.

---

## 8. Deploying to a public server (the reasoning)

**Status: host chosen — Microsoft Azure, for the defense only. See §9 for the procedure.** This section remains as the argument for *why* a public host, and what the trade is; §9 is the one that tells you what to click. The on-premises deployment in §1–§7 is still the deployment of record — the Azure instance is a temporary copy so a panel can open a link instead of joining a network.

### Why this is the answer to "my teammates shouldn't have to configure anything"

Everything awkward about the LAN setup traces to one root cause: **the system has no public address.**

- The certificate warning exists because no certificate authority can vouch for a private address like `192.168.1.x` — nobody can prove they own a private address, since every network has one.
- The same-wifi requirement exists because a private address is only routable on that network.
- The "your laptop must be on" requirement exists because your laptop *is* the server.

A real domain name on a machine that stays on fixes all three at once, and **removes every step from your teammates**: they open a link. No certificate, no clone, no `.env`, no Docker.

### What already works, unchanged

The stack is deliberately host-agnostic. Two environment variables switch it from "private address" to "public domain" — no code changes, no rebuild:

| Variable | LAN / localhost | Public domain |
|---|---|---|
| `ARKIVE_SITE_ADDRESS` | `localhost`, or the host's current LAN address from `ipconfig getifaddr en0` | `arkive.example.com` |
| `ARKIVE_TLS_DIRECTIVE` | leave the default (`tls internal`) | `ARKIVE_TLS_DIRECTIVE=tls you@example.com` |

With `ARKIVE_TLS_DIRECTIVE=tls you@example.com`, Caddy fetches a **free, publicly-trusted Let's Encrypt certificate automatically** and renews it on its own. Replace the example with a real email address for ACME notices.

The Compose default is intentionally safe for local and private deployments. A public domain must provide the ACME email explicitly; leaving the variable empty falls back to `tls internal`.

```
line left out of .env       -> compose passes "tls internal"       -> Caddy's own certificate
ARKIVE_TLS_DIRECTIVE=tls ... -> compose passes "tls you@example.com" -> Let's Encrypt
```

`DATABASE_URL` is also overridable, so a managed Postgres (Neon, Supabase, a provider's own database) can replace the bundled container without editing anything.

### The route worth trying first: GitHub Student Developer Pack

Free with proof of enrolment — an MSEUF student ID qualifies, and GitHub verifies the student rather than the school's email domain, which matters (see §9).

**Check the Pack's current catalogue rather than trusting a list written here.** Its offers are added and withdrawn over time: this section previously recommended DigitalOcean's $200 credit and a free Namecheap domain, and as of 2026-09-29 DigitalOcean is no longer among the offers shown. What *is* there is Microsoft Azure — $100 credit, no credit card — and §9 is the procedure for it.

Whatever the host, the deployment is the same one in §3: install Docker, clone, set `.env`, `docker compose -f docker-compose.prod.yml up -d --build`. Give the server a publicly-resolvable name and set `ARKIVE_TLS_DIRECTIVE=tls you@example.com`; HTTPS then configures itself.

Server sizing, measured on the development machine: backend 193 MB RAM, Postgres 31 MB, Caddy 11 MB at rest. The build step is the spike, not the running stack.

### Free-tier fallback

If the Student Pack does not come through: **Render** (builds from `backend/Dockerfile`) plus **Neon** (free managed Postgres, set as `DATABASE_URL`). Permanent URL, trusted certificate, genuinely free.

The catch to plan around rather than rely on: free web services sleep after roughly 15 minutes idle and take about a minute to wake. Open the site a few minutes before a demo. Free managed databases are also sometimes deleted after a period of inactivity, so keep `scripts/seed_golden_path.py` handy for re-seeding.

### The thesis question, stated plainly

Hosting off-campus is a different deployment model from the thesis's stated on-premises scope. The defensible framing, and it is genuinely true:

> The system is architected and verified for on-premises deployment — §1–§7 of this document are that deployment, built and measured, and it is what closed NFR-03. A hosted instance is maintained for evaluation access.

You have demonstrated the on-premises capability. Where a convenience copy runs does not change the architecture. **Confirm this with the adviser before committing to a host**, rather than discovering the objection at the defense.

### One detail specific to IP deployments

Caddy does not create an HTTP→HTTPS redirect for a bare IP address — it disables that by design, since there is no hostname to redirect. On the LAN setup, users must type `https://` explicitly; `http://<the LAN address>/` returns nothing. With a real domain the redirect is created automatically, so a plain `arkive.example.com` works.

---

## 9. The public demo instance (defense only)

*Written 2026-09-29. This is §8's "public server" with a host finally chosen. It does not replace §1–§7: the on-premises stack is still what the thesis claims and what closed NFR-03. This is a copy that exists so a panel can open a URL.*

**The host is Microsoft Azure, on the ordinary free trial — not Azure for Students.**

That distinction is the whole of §9.1, and it cost two days to learn. **Azure for Students** verifies eligibility by academic email domain, and MSEUF is not on Microsoft's list: a genuine student with a genuine school address is refused, and the refusal is not appealable from the sign-up flow. The GitHub Student Developer Pack's Azure offer looks like a way around it — it verifies by connecting a GitHub account rather than a school domain — but it hands you to the same `Azure for Students verification` step at the end, which fails the same way.

The **free trial** has no academic check of any kind. It asks for a payment card to establish identity, which is the price of skipping a verification that will never pass.

Because this exists only for a defense, everything optimises for **cheap, quick to stand up, and easy to destroy** — not durability.

### 9.1 Start the free trial

From the Azure welcome page, take **Start with an Azure free trial**. Not the Students card — that path is closed for this institution (above).

What it involves:

- **A credit or debit card, for identity verification.** Microsoft places a small temporary authorisation and reverses it. This is not a purchase.
- **A spending limit, on by default.** This is the part worth understanding: while the limit is on, Azure *cannot* charge you. When the credit is exhausted or the trial ends, services are disabled rather than billed. You are only ever charged if you deliberately remove the limit and upgrade to pay-as-you-go.
- Credit toward paid services for the first 30 days, plus a set of services that stay free for 12 months.

**Leave the spending limit on.** It is the difference between a defense instance and an accidental bill, and nothing in §9 needs it removed.

> If a card is genuinely not available, §8's free-tier fallback (Render + Neon) needs none. Note that Render's free tier has an **ephemeral filesystem**, which loses uploaded résumés and documents on every restart — see 9.8 for why that matters here more than it would for most apps.

### 9.2 Create the VM

**Create a resource → Virtual machine.**

| Field | Value | Why |
|---|---|---|
| Image | **Ubuntu Server LTS** | Docker's best-supported target |
| Region | Nearest the panel | Latency during a live demo |
| Size | **2 vCPU / 4 GB** class | At rest this stack is small — §1's measurements are backend 193 MB, Postgres 31 MB, Caddy 11 MB — but `up --build` compiles the React app, and that spike is what kills a 1 GB box |
| Authentication | **SSH public key**, not password | A password on a public SSH port is brute-forced within hours |
| Inbound ports | SSH (22) only for now | 80 and 443 come in 9.3 |
| Resource group | **A new one, used by nothing else** | 9.7 deletes it wholesale |

Check prices in the Azure pricing calculator for your region rather than trusting a figure quoted here. Against $100 of credit a machine this size is comfortable for a defense cycle **provided it is deallocated between sessions** (9.7) — left running continuously it is not.

### 9.3 Give it a name Let's Encrypt can certify, and open the ports

This is the step that makes HTTPS free and automatic, and it is easy to skip.

On the VM's **public IP address** resource, set a **DNS name label**. Azure then serves the VM at:

```
<your-label>.<region>.cloudapp.azure.com
```

That is a real, publicly-resolvable hostname, so Caddy can obtain a genuine Let's Encrypt certificate for it. A bare IP cannot be certified by anyone — the same limitation §8 explains for LAN addresses, and the reason the LAN setup shows a browser warning.

**This is why Azure suits a defense instance better than a plain server**: the hostname is free and automatic, so no domain has to be bought or registered. It also survives the stop/start cycle in 9.7 — a deallocated VM usually returns on a *different* IP, but the DNS label follows the new address, so the name and its certificate stay valid.

Then open the two web ports. On the VM's **Networking** blade, add inbound rules allowing **80** and **443**.

**Port 80 is not optional.** Let's Encrypt validates over HTTP before it will issue. Opening only 443 produces a stack that looks correct and never gets a certificate.

### 9.4 Install Docker and bring the stack up

SSH in, then:

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER && newgrp docker

git clone <this repository> arkive && cd arkive
cp .env.example .env
```

Fill in `.env`. Only three lines differ from the on-premises values in §2:

| Variable | Value here | Why |
|---|---|---|
| `ARKIVE_SITE_ADDRESS` | `<your-label>.<region>.cloudapp.azure.com` | The name from 9.3 |
| `ARKIVE_TLS_DIRECTIVE` | **`tls you@example.com`** | A real ACME email makes Caddy fetch and renew a publicly-trusted certificate. Leaving the default `tls internal` uses Caddy's local CA |
| `JWT_SECRET_KEY` | A fresh `python -c "import secrets; print(secrets.token_hex(32))"` | Never carry the development value onto a public address |

`OPENAI_API_KEY` and the five `SMTP_*` values carry over unchanged. Then:

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

The migration step is the most common thing to forget: the containers start happily against an empty schema and then fail on the first request that touches a table.

Seed demo data as in §3 if the panel should see a populated pipeline.

### 9.5 Check it days before, not on the day

Open `https://<your-label>.<region>.cloudapp.azure.com`. You want a padlock with **no warning** — that is the entire point of 9.3.

If you get a warning, it is almost always one of two things: `ARKIVE_TLS_DIRECTIVE` was left at `tls internal`, or **port 80 is closed**, which Let's Encrypt needs for validation even though the site itself serves on 443. After fixing either, `docker compose -f docker-compose.prod.yml restart caddy` to make it ask again.

`docker compose -f docker-compose.prod.yml ps` should show `db`, `backend` and `caddy` up, and **`frontend-build` as `Exited (0)`** — that container compiles the SPA and stops, so exited is the success case (§1).

### 9.6 What to say if the panel asks where it runs

§8's framing is the honest one and needs no softening:

> The system is architected and verified for on-premises deployment — §1–§7 of this document are that deployment, built and measured, and it is what closed NFR-03. A hosted instance is maintained for evaluation access.

Confirm it with the adviser in advance rather than discovering an objection mid-defense.

### 9.7 Money, and turning it off

**A VM bills for every hour it exists, whether or not anyone opens it.** The trial credit is finite and time-boxed, and a machine left running between a proposal and a final defense will consume most of it doing nothing.

Between sessions, **Stop (deallocate)** the VM from the portal. Deallocated compute stops billing; the disk still costs a little, which is the price of not rebuilding each time. The DNS label from 9.3 is what makes stopping safe — the hostname and its certificate survive the new IP.

This is the single habit that decides whether the credit lasts. Set a reminder if you have to.

The spending limit from 9.1 is the backstop, not the plan: with it on, exhausting the credit disables the VM rather than charging the card. That is a safety net against a mistake, not a reason to skip deallocating — a disabled VM in the middle of a defense is its own kind of disaster.

When the defense is over, delete the whole **resource group** — not the VM alone. Deleting a VM leaves its disk, public IP and network interface behind, each still billing. The resource group takes all of it in one action, which is why 9.2 puts this deployment in its own.

### 9.8 Why this needs a real VM at all

Worth recording, because it is the question that will be asked if someone suggests a simpler free host.

ARKIVE is a **stateful** application. Five separate paths write files to local disk — résumés, supplemental documents, job-description uploads and their versions, and avatars (`app/services/file_storage.py`) — and `docker-compose.prod.yml` keeps them in the `arkive_uploads` volume precisely so they survive a restart.

That rules out the serverless and free-tier hosts that suit most student projects:

- **Vercel, Netlify** and similar are built for stateless frontends and short functions. There is no persistent filesystem, so every one of those five write paths fails, and the AI pre-screening pipeline — embeddings, BM25 and an LLM call in one request, deliberately wrapped in `run_in_threadpool` because it blocks — exceeds their execution limits.
- **Render's free tier** has an ephemeral disk: uploads vanish on each restart and after each idle sleep. Since the pipeline *starts* with a CV upload, that breaks the demo rather than degrading it.
- Splitting the frontend onto one of these and the backend elsewhere also reintroduces **CORS**, which §1 notes this deployment deliberately avoids by serving both from one origin.

A plain Linux VM running the existing Compose file has none of these problems, which is why §9 is a VM and not a platform.

---

## 10. Fallback: Oracle Cloud Always Free

*If Azure's card check declines, or the trial credit runs out before the final defense.*

Oracle's Always Free tier is **free permanently, not a trial**, and its ARM allowance — up to 4 cores and 24 GB RAM — is far larger than anything else in this document. A machine that size runs this stack without thinking about it.

Two things can stop you, both worth knowing before spending an evening:

- **ARM capacity is frequently exhausted.** "Out of host capacity" on instance creation is common in popular regions and can persist for days. It is not a fault in your account and there is nothing to fix — you retry, or try another availability domain.
- **Signups are sometimes rejected** without a stated reason, occasionally after appearing to succeed.

Neither is predictable, which is why this is §10 and not §9.

### 10.1 Sign up

At **oracle.com/cloud/free**. A card is required for identity verification with a small reversed authorisation, same as Azure — Oracle uses a different payment processor, so a card Microsoft declines sometimes passes here.

**Choose the home region carefully: it cannot be changed afterwards.** Pick one near the panel — Singapore, Tokyo, Osaka or Seoul from the Philippines. There is a real trade-off: the nearest region is also the most contended, so the closest choice is often the one where ARM capacity is hardest to get.

Signup also grants trial credit for 30 days. Ignore it. Everything below stays inside Always Free, and when the trial lapses the account keeps working at that tier.

### 10.2 Create the instance

**Compute → Instances → Create instance.**

| Field | Value | Why |
|---|---|---|
| Image | **Ubuntu LTS** | Docker's best-supported target |
| Shape | **VM.Standard.A1.Flex**, 2 cores / 12 GB | Always Free covers 4/24 total; half of it is ample and leaves room to retry elsewhere |
| SSH | Upload your public key | Password auth on a public port is brute-forced within hours |

Do **not** take the `E2.1.Micro` AMD shapes instead. They are also Always Free but carry 1 GB of RAM, and 9.2 explains why the frontend build will not survive that.

If creation fails with **"Out of host capacity"**, switch availability domain and retry, or retry later. It is a queue, not a verdict.

Note the instance's **public IP** when it comes up.

### 10.3 Open the ports — both firewalls

**This is the step that wastes the most time on Oracle, because there are two firewalls and opening one is not enough.**

First the cloud one. On the instance's subnet → **Security List**, add ingress rules for TCP **80** and **443** from `0.0.0.0/0`.

Then the one inside the machine. Oracle's Ubuntu images ship with local `iptables` rules that drop almost everything, so the site stays unreachable even with the Security List correct and the containers running:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

If the stack is up and the browser still times out, this is almost always why.

### 10.4 Get a hostname

Azure hands out a free `cloudapp.azure.com` name (9.3); **Oracle does not.** You get a bare IP, and §8 explains why no certificate authority will certify one.

The free fix is a dynamic-DNS name — **DuckDNS** (`duckdns.org`) gives a free `yourname.duckdns.org` pointed at any IP, needs no card, and Let's Encrypt issues for it normally. Create the subdomain, point it at the instance's public IP, and confirm it resolves before continuing:

```bash
ping yourname.duckdns.org
```

**Do not continue until it answers with the instance's IP.** Caddy asks Let's Encrypt for a certificate the moment it starts; if the name does not resolve yet, that request fails and you will debug the wrong layer.

### 10.5 Deploy

Identical to 9.4, with `ARKIVE_SITE_ADDRESS` set to the DuckDNS name:

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER && newgrp docker

git clone <this repository> arkive && cd arkive
cp .env.example .env
# ARKIVE_SITE_ADDRESS=yourname.duckdns.org
# ARKIVE_TLS_DIRECTIVE=tls you@example.com
# JWT_SECRET_KEY=                (a fresh one)

docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

On ARM the first build is noticeably slower than on x86 — some Python wheels compile from source rather than downloading. It is a one-time cost, not a running one.

Then verify as in 9.5.

### 10.6 Money

There is none, which is the point. Always Free resources do not bill, and the account does not require the trial credit to stay alive.

Two habits still apply. **Do not exceed the Always Free allowances** — a second large instance, or block storage past 200 GB, moves you onto paid rates. And leave the instance **running**: unlike §9.7's advice for Azure, there is no billing reason to stop it, and stopping it only risks the ephemeral public IP changing, which would break the DuckDNS record until you update it.
