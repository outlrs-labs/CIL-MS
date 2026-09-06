# CIL Central identity and entity foundation

Current implementation: versioned local ZIP ingestion and analysis-time document conversion. Upload preserves PDFs/images without processing them. Selecting one in **Analyse** runs local extraction and adds immutable Markdown and CSV derivatives to the embedded analytics workbench.

First application slice for the hierarchy:

- One protected CIL apex administrator.
- Seven seeded operating subsidiaries: ECL, BCCL, CCL, NCL, WCL, SECL and MCL.
- One technical coordinator: CMPDI.
- Administrator-managed users and entities; no public registration or assignable admin role.
- Operating users are restricted to their entity. CMPDI and CIL have group entity visibility; only CIL can administer accounts/entity master.
- Temporary passwords must be changed at first sign-in. Role and entity come from protected database records.

This slice establishes identity, authorization and the dashboard shell. It does not yet include reporting, uploads, reminders or analytics workbench integration.

## Configure Supabase

Run the setup commands from `cil-platform/`.

1. Create a dedicated Supabase project. In Authentication settings, disable public email signups; the app has no signup path.
2. Copy/edit `.env` (already created from `.env.example`). Fill both server and Vite URL/key pairs. `SUPABASE_SECRET_KEY` stays server-only; never put it in a `VITE_` variable.
3. Run `supabase/migrations/001_identity.sql` once in Supabase SQL Editor.
4. Set `ADMIN_EMAIL`, a unique 14+ character `ADMIN_PASSWORD`, and `ADMIN_NAME`. Then run:

```sh
./.venv/bin/python scripts/bootstrap_admin.py
```

Remove `ADMIN_PASSWORD` from `.env` after success. The bootstrap refuses to replace a different existing administrator. To bind an existing confirmed Auth user, set `ADMIN_USER_ID` and ensure `ADMIN_EMAIL` matches it.

## Install on another machine

Run all commands below from `cil-platform/`. Use Python 3.12 and Node.js 22 or later.

```sh
python3.12 -m venv .venv
./.venv/bin/pip install -r backend/requirements.lock.txt
npm ci --prefix frontend
```

Dependencies are already installed in this workspace.

## Run locally

Start the complete workspace (web app, CIL API, and the private analytics
engine) with one supervised command:

```sh
./.venv/bin/python scripts/dev.py
```

Open `http://127.0.0.1:5173`. Stopping the launcher stops all three child
services, which prevents a stale frontend from reporting an analytics 503.
With empty Supabase values, Vite development can show the read-only interface
preview; it never authenticates or calls protected APIs. Set
`VITE_ENABLE_UI_PREVIEW=false` to hide it.

## Validate

```sh
./.venv/bin/pytest -c backend/pytest.ini backend/tests
npm test --prefix frontend
npm run build --prefix frontend
```

The migration test uses an embedded PostgreSQL runtime to compile the real SQL and verify seed/admin constraints. Validate the final migration and RLS in the dedicated Supabase project before deployment.

## Security decisions

Supabase Auth validates access tokens. FastAPI requests the current user from Auth on every protected request and reads role/entity from RLS-protected tables. The browser never receives the secret key. Provisioning and administrative RPCs require the service role and recheck the authenticated actor's protected CIL-admin record. An unprofiled Auth user has no application access.

Account provisioning is deliberately fail-safe: if Auth succeeds but profile creation has an ambiguous failure, the API leaves an unassigned Auth user with no access and asks an operator to review it. It never deletes a possibly committed identity automatically.

## Verification and remaining setup

Local verification on 2026-09-04: 9 backend tests and 3 frontend/database tests passed; production frontend build passed; dashboard returned HTTP 200 and API health returned `configured: false`. Database tests exercise the migration in embedded PostgreSQL, including RLS isolation, CMPDI visibility, role escalation denial and protected admin constraints. Live Supabase authentication has not been tested because credentials are not configured yet.

After updating `.env`, restart the complete workspace. Apply the migration before running the administrator bootstrap. Entity seeds create organization records; the administrator creates individual subsidiary/CMPDI accounts from Access & people. Temporary credentials require a password change on first login.

There is no self-service password recovery screen yet. Administrator recovery should be handled through the project's trusted Supabase operator; do not create a replacement apex account. Before deployment, configure the organization's recovery/MFA/session requirements and test live authentication, password changes and disabled-user access. analytics workbench remains separate for the next integration step.

## CMPDI local analytics workbench workbench

Repository data now stays inside this checkout under `Data/cil/<entity>/<family>/`, with private snapshots and workspaces under `Data/.processing/`. Sign in and open **Analyse** to select uploaded versions or launch the embedded workbench.

Start from `cil-platform/`:

```sh
.venv/bin/python scripts/dev.py
```

For a fresh dependency installation, install backend requirements and the bundled Data Formulator copy into the same virtualenv:

```sh
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m pip install setuptools wheel
.venv/bin/python -m pip install --no-build-isolation -e data-analyser
npm --prefix data-analyser install --legacy-peer-deps --ignore-scripts
CIL_EMBEDDED=true npm --prefix data-analyser run build
npm --prefix frontend install
npm --prefix frontend run build
```

`--legacy-peer-deps` accommodates the upstream Vega peer-version mismatch. The source, backend package, and compiled workbench now resolve from `data-analyser/` inside this project.

Set `DF_BRIDGE_SECRET` to a random secret of at least 32 characters, and retain the loopback `DF_URL=http://127.0.0.1:5567`. Keep `.env` private. `CIL_DATA_ROOT`/`CIL_PROCESSING_ROOT` can override storage locations. `WORKBENCH_COOKIE_SECURE=true` is required when deployed over HTTPS; proxy both `/api/cmpdi` and `/cmpdi/workbench` on the frontend origin. This local pilot uses `DF_SANDBOX=local`; harden execution before deployment.

AI credentials can be configured through **Settings → AI providers & models**, including an explicit Sarvam AI primary, Gemini fallback, third-party OpenAI-compatible APIs, and Ollama. Environment-backed credentials remain server-side: `CIL_PRIMARY_PROVIDER` selects the primary CIL Auto route and `CIL_FALLBACK_PROVIDER` selects its first fallback. No model credential is required to browse sources or open manual charts; the UI reports that AI is not configured instead of failing during workspace load.


## Production subsidiary ZIP workflow

All seven production accounts now have ZIP submission, schedule/history, scoped analytics/chat and report drafting. CMPDI reviews cross-subsidiary submissions and generated revisions. Same-origin deployment must proxy `/api/analytics` to FastAPI. Upload needs no AI credential; PDF/image conversion uses local text extraction when a source is chosen in Analyse, while AI operations use the configured model provider.
> Document workflow: install Tesseract (`brew install tesseract` on macOS). ZIP upload stores the original package only. OCR starts when a PDF or image is selected in Analyse; Markdown and CSV outputs are then imported into that workbench session.

## AWS production deployment

The production stack uses CloudFront as the single HTTPS origin, a private S3 bucket for the frontend, a versioned S3 bucket for the durable `Data/cil` hierarchy, and one EC2 host for FastAPI, the private analytics workbench, Nginx, and PostgreSQL. Supabase remains the authentication and authorization authority.

Copy `.env.production.example` to `.env.production`, fill in the Supabase values, and run `./deploy/aws-deploy.sh cil-platform ap-south-1` from an AWS-authenticated computer. See [deploy/README.md](deploy/README.md) for the full procedure and operations notes.
