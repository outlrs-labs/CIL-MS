# CIL Reporting Workspace — Product Requirements

**Status:** Working product definition  
**Updated:** 2026-09-05

## Product purpose

The application gives CIL one controlled reporting workspace for its seven operating subsidiaries and CMPDI. Operating subsidiaries submit periodic source packages. CMPDI reviews, extracts, analyses and combines the data into report drafts. The sole CIL Central Admin manages entities, users and group oversight. The current release uses local storage under `Data/cil`.

## Users and access

| User | Scope | Main responsibility |
| --- | --- | --- |
| CIL Central Admin | All eight entities and access records | Entity master, people and group oversight |
| CMPDI | All reporting entities and technical families | Review, OCR, analysis and consolidated drafts |
| Operating subsidiary | Its own entity | Upload, inspect, analyse and draft from its reporting data |

The operating subsidiaries are BCCL, CCL, ECL, MCL, NCL, SECL and WCL. CMPDI is the technical and planning entity. Public sign-up is unavailable.

## Application shell

Every authenticated screen uses a fixed left sidebar, a 56 px top bar and a fluid content area. The header shows the current screen, theme control and identity; the account menu provides Profile, Settings and Sign out.

CMPDI and subsidiary navigation uses `UPLOAD`, `VAULT`, `ALALYSE`, `AUDIT` and `DRAFT`. CIL Admin uses Dashboard, Entity master, Access & people and Settings.

## Screens

### Dashboard

The CIL Admin view shows connected entities, operating subsidiaries, technical coordinator and apex administrator, followed by the reporting hierarchy, access model and entity directory. CMPDI sees incoming submissions, technical review and consolidated reporting. A subsidiary sees its reporting cycles and the route `Subsidiary → CMPDI → CIL Central Admin`.

### UPLOAD

The landing view contains a report-family selector, **Upload**, and a small **Version Control** action. CMPDI receives a read-only production-submission view.

Upload uses a four-step modal: **Report → Package → Review → Submit**. It collects family, cadence and period; accepts a ZIP; confirms its destination and replacement semantics; then shows real progress and the committed version. Structured files, supporting evidence and older revisions must remain traceable. Validation errors keep the selected values and explain recovery.

### VAULT

Vault is a Finder-style browser over the authorized part of `Data/cil`. It provides folder/file cards, breadcrumbs, Back/Forward, Search, a Type/Updated/Sort filter, Refresh, compact metadata and Download. CMPDI can browse all eight entities; a production user sees only its assigned entity and scoped schedule.

### ALALYSE

The source browser selects authorized files by subsidiary and family. CSV, XLSX, JSON and Parquet can also be stored directly in the local repository. The active workspace places charts and tables in the main canvas and data chat/report tools at the right. CMPDI can configure supported model providers. Each analysis retains source snapshots and provenance.

### AUDIT

Audit handles PDF/image OCR. A user selects a submitted source, runs extraction, compares the page preview and extracted table, corrects a CSV if needed, and approves it. Only reviewed outputs enter Analysis.

### DRAFT

Draft lists generated report revisions. Each analytical draft provides Markdown, a visual PNG, a source manifest, analysis state, chart assets and a complete ZIP. Saving a draft never represents final CIL approval.

### Entity master and Access & people

These are CIL Admin screens. Entity master supports search, type filters and entity editing. Access & people lists member identity, entity, role and status; supports adding, enabling and disabling accounts; and records access changes. Accounts are administrator-provisioned.

## Settings

| Section | Components |
| --- | --- |
| Overview | Settings landing state and account/workspace summary |
| Your profile | Full name, email, entity, role and account status |
| Login & security | Password update and account security |
| Appearance | Light/dark mode and five accent choices |
| Subsidiaries / Entity master | Role-appropriate entity directory |
| Team members | Admin-only access management |

Appearance applies immediately and is saved on the current device under `cil.appearance.v1`.

## Report families

Operating subsidiaries submit production and off-take (daily/monthly), environmental compliance (half-yearly), financial (quarterly/annual), operational statistics (monthly) and washery operations (daily/monthly).

CMPDI families are annual report, land reclamation, geological exploration, hydrology and groundwater, project feasibility, and specialized surveys.

## Acceptance criteria

- Each role sees only its authorized navigation and data scope.
- A valid ZIP creates an immutable version, source archive and manifest.
- Vault mirrors the local hierarchy and prevents traversal or cross-entity access.
- Approved OCR tables are selectable in Analysis.
- Analysis supports charts, table inspection, data chat and report drafting.
- Drafts preserve charts, provenance and revision history.
- All screens follow `design.md`, work on narrow viewports and avoid unnecessary copy.

