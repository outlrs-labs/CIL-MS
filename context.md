# CIL Reporting Workspace — File and Vault Context

**Updated:** 2026-09-05  
**Purpose:** Handoff reference for developers and agents working with local report storage.

## Storage boundary

The user-facing repository is `/Users/harshyadav/Documents/CIL/Data/cil`, configured by `CIL_DATA_ROOT`. Backend-only state uses `CIL_PROCESSING_ROOT`, defaulting to `/Users/harshyadav/Documents/CIL/Data/.processing`.

`Data/cil` holds source files, versions, OCR artifacts and generated reports. `.processing` holds private or rebuildable state such as `catalog.sqlite3`, analysis snapshots, workbench state and encrypted provider configuration. The frontend must never expose the processing root as Vault.

## Entity tree

```text
Data/cil/
├── BCCL/  ├── CCL/  ├── ECL/  ├── MCL/
├── NCL/   ├── SECL/ ├── WCL/  ├── CMPDI/
└── reporting_schedule.json
```

### Operating subsidiary

```text
<ENTITY>/
├── production_offtake/          # daily, monthly
├── environmental_compliance/    # half-yearly
├── financial/                   # quarterly, annual
├── operational_statistics/      # monthly
├── washery_operations/          # daily, monthly
└── report/                       # entity-wide report library
```

Each family starts with `data/` and `report_generated/`. `submissions/` appears after the first ZIP submission. `extractions/` appears only when a user selects a PDF/image in Analyse.

### CMPDI

```text
CMPDI/
├── annual/                      # annual, public
├── land_reclamation/            # annual, public
├── geological_exploration/      # project-based, internal
├── hydrology_groundwater/       # project-based/annual, internal
├── project_feasibility/         # event-driven, internal
├── specialized_surveys/         # specialized, internal
└── report/
```

Each CMPDI family also uses `data/` and `report_generated/`.

## ZIP submission and versions

```text
<ENTITY>/<FAMILY>/
├── data/versions/<CADENCE>/<PERIOD>/<SUBMISSION_UUID>/
│   └── <original safe ZIP paths>
└── submissions/<SUBMISSION_UUID>/
    ├── source.zip
    └── manifest.json
```

`source.zip` preserves the submitted package. The manifest records scope, version, owner, times, hashes and file status. SQLite is authoritative for committed versions; JSON is a durable projection. A replacement for the same entity/family/cadence/period receives the next version, and older versions remain immutable.

Files uploaded directly from Analysis use:

```text
<ENTITY>/<FAMILY>/data/analysis_uploads/<UPLOAD_UUID>/<filename>
```

Supported structured formats are CSV, XLSX, JSON and Parquet.

## OCR artifacts

```text
<ENTITY>/<FAMILY>/extractions/<EXTRACTION_UUID>/
├── page-<n>.*
├── *.csv
├── reviewed-*.csv
├── document.md
├── reviewed-document.md
└── review.json
```

PDF, PNG, JPG/JPEG and TIF/TIFF sources remain in their immutable submission. Upload never starts OCR. Analyse starts or reuses a source-hash-matched extraction only after the document is selected. Published derivatives are restricted to Markdown and CSV; both are snapshotted and loaded as workbench tables. Page PNGs are internal previews, not analytical outputs.

## Generated reports

```text
<ENTITY>/<FAMILY>/report_generated/<REPORT_UUID>/
├── report.md
├── report.png
├── manifest.json
├── analysis-state.json
├── report.zip
└── charts/<chart-id>.png
```

The same revision is hard-linked or copied into `<ENTITY>/report/<REPORT_UUID>/`, with `<ENTITY>/report/<REPORT_UUID>.json` as its library entry. The manifest records the report series/version, previous revision, analysis, target, scope, period, sources and hashes, chart metadata and model. Its status is `analytical-draft`.

## Schedule

`reporting_schedule.json` is generated from report obligations and submission history. It contains cadence and last-update state. A subsidiary receives a backend-generated projection for only its own entity, never the unfiltered disk file.

## Vault rules

- CMPDI can browse all eight roots; a production account can browse only its own entity.
- Vault is read-only and downloads require authentication.
- Hidden files, symlinks, traversal segments, backslashes and null bytes are rejected.
- Browsable family children are `data`, `report_generated` and `submissions`; entity-level `report` is allowed.
- `extractions` is backend-managed and created on demand from Analyse; Vault continues to present the immutable submitted source.
- Search/filter supports type, updated time and sort order.

Never edit an earlier version in place, analyse an organizational original without a snapshot, store secrets in `Data/cil`, or let the frontend construct arbitrary filesystem paths. Keep every generated report inside its target entity/family and preserve its source manifest.

## Workbench session continuity

The selected analysis is remembered in browser `sessionStorage` under an entity-scoped key. On a portal refresh, only that exact ready analysis is restored; the latest analysis is never opened implicitly. The workbench iframe stays mounted while the user visits Upload, Vault, Audit or Submitted Reports, so its in-memory Data Formulator state is preserved. Its short-lived bridge credential is kept only in backend memory, issued as an HttpOnly cookie scoped to the analysis path, and renewed silently every five minutes and when the portal becomes visible. A backend restart or expired response is recovered by renewing the same analysis session and reloading only that workbench frame.

## Report approval workflow

A generated subsidiary report is registered as an immutable revision and enters Audit as `pending_review`. It is not returned by the Submitted Reports API at this stage. An Assistant Manager or Manager assigned to the same subsidiary can approve, await or reject it; the author cannot audit their own report. Approval changes the state to `submitted_to_cmpdi`, removes it from the open Audit queue and makes it visible in both the subsidiary's Submitted Reports screen and CMPDI's incoming report list.

## Code map

| Responsibility | File |
| --- | --- |
| Folder definitions and catalog | `backend/app/integration/repository.py` |
| ZIP versioning and schedule | `backend/app/integration/submissions.py` |
| OCR jobs and approval | `backend/app/integration/ocr.py` |
| Vault validation and listing | `backend/app/integration/vault.py` |
| Analysis and report export API | `backend/app/integration/api.py` |
| Upload / Version Control UI | `frontend/src/SubmissionWorkspace.tsx` |
| Vault UI | `frontend/src/VaultWorkspace.tsx` |
| Analysis UI | `frontend/src/AnalyticsWorkspace.tsx` |
| Analysis-time OCR orchestration | `backend/app/integration/api.py`, `backend/app/integration/ocr.py` |
