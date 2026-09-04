# CIL Central identity and entity foundation

Current implementation: [Reference UI, reliable ZIP/CSV import and local OCR](../context/19-DESIGN-UPLOAD-OCR.md). Install the backend requirements and local Tesseract engine. In **Data & reports**, use **Document extraction** to review scanned PDFs/screenshots; approved outputs appear in **analytics workbench**. The native workbench keeps its original interface.

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

Backend:

```sh
./.venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8000
```

Frontend:

```sh
npm run dev --prefix frontend
```

Open `http://localhost:5173`. With empty Supabase values, Vite development can show the read-only interface preview; it never authenticates or calls protected APIs. Set `VITE_ENABLE_UI_PREVIEW=false` to hide it.

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

After updating `.env`, restart both development servers. Apply the migration before running the administrator bootstrap. Entity seeds create organization records; the administrator creates individual subsidiary/CMPDI accounts from Access & people. Temporary credentials require a password change on first login.

There is no self-service password recovery screen yet. Administrator recovery should be handled through the project's trusted Supabase operator; do not create a replacement apex account. Before deployment, configure the organization's recovery/MFA/session requirements and test live authentication, password changes and disabled-user access. analytics workbench remains separate for the next integration step.

## CMPDI local analytics workbench workbench

See [integration handoff](../context/17-LOCAL-ANALYTICS-INTEGRATION.md) for storage, endpoints, permissions, verification and known limits. Sign in as CMPDI and open **Data & reports**. Place existing source files under `../Data/cil/<entity>/<family>/data/`; no upload pipeline is included.

Start from `cil-platform/`, in separate terminals:

```sh
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
.venv/bin/python integration/run_data_formulator.py
npm --prefix frontend run dev -- --host 127.0.0.1
```

For a fresh dependency installation, install backend requirements and the sibling package into the same virtualenv:

```sh
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m pip install setuptools wheel
.venv/bin/python -m pip install --no-build-isolation -e ../data-formulator
npm --prefix ../data-formulator install --legacy-peer-deps --ignore-scripts
CIL_EMBEDDED=true npm --prefix ../data-formulator run build
npm --prefix frontend install
npm --prefix frontend run build
```

`--legacy-peer-deps` accommodates the upstream Vega peer-version mismatch. The installed dependency snapshot is in `integration/requirements.lock`; the npm snapshot is `integration/data-formulator.package-lock.json` (copy to the sibling checkout's `package-lock.json` before `npm ci --legacy-peer-deps --ignore-scripts` for exact replay).

Set `DF_BRIDGE_SECRET` to a random secret of at least 32 characters, and retain the loopback `DF_URL=http://127.0.0.1:5567`. Keep `.env` private. `CIL_DATA_ROOT`/`CIL_PROCESSING_ROOT` can override storage locations. `WORKBENCH_COOKIE_SECURE=true` is required when deployed over HTTPS; proxy both `/api/cmpdi` and `/cmpdi/workbench` on the frontend origin. This local pilot uses `DF_SANDBOX=local`; harden execution before deployment.

AI credentials can be configured later through **AI providers & models**, including third-party OpenAI-compatible APIs and Ollama. No model credentials are required just to browse sources/open manual charts. Existing optional environment-based provider configuration is also supported by the private runner.


## Production subsidiary ZIP workflow

All seven production accounts now have **Data & reports** with ZIP submission, schedule/history, own-data charts/chat and report drafting. CMPDI reviews cross-subsidiary submissions and generated revisions. See [pipeline handoff](../context/18-SUBSIDIARY-INPUT-PIPELINE.md). Same-origin deployment must also proxy `/api/analytics` to FastAPI. No extra credential is needed for upload; AI operations use configured models. Scanned-PDF extraction is the next phase.
> Latest update: [Reference-led UI, ZIP/CSV compatibility and local OCR](../context/19-DESIGN-UPLOAD-OCR.md). Run `pip install -r backend/requirements.txt` in the project virtualenv and install Tesseract (`brew install tesseract` on macOS). Upload PDFs/images, then open **Data & reports → Document extraction** to review results. Approved CSVs become available in the analytics workbench tab.
