# Local CIL report repository

The `cil/` tree contains seven production subsidiaries (ECL, BCCL, CCL, NCL, WCL, SECL, MCL) and CMPDI. Each report family contains **data/** for existing source files and **report_generated/** for saved analytical reports. Place structured input files in the relevant data folder; nested period/project folders are allowed.

Production families: production_offtake (daily/monthly), environmental_compliance (half-yearly), financial (quarterly/annual), operational_statistics (monthly), washery_operations (daily/monthly).

CMPDI families: annual (annual), land_reclamation (annual), geological_exploration (project-based), hydrology_groundwater (project-based/annual), project_feasibility (event-driven), specialized_surveys (cadence unspecified).

Each subsidiary also has **report/**, the combined generated-report library. Immutable artifacts are hard-linked from the family output folder where supported (copy fallback). New saves produce new IDs; don't edit linked files in place.

Example input: `cil/BCCL/production_offtake/data/2026-08/production.csv`.
Example output: `cil/CMPDI/annual/report_generated/<report-id>/report.zip`.

`.processing/` contains local snapshots, workspaces, SQLite metadata and encrypted model configurations. Do not rename or remove it while servers are running. Back up it and `cil/` together; the provider encryption key is in `cil-platform/.env`. This repository is excluded from Git by default.

There is no input-upload/OCR pipeline in this increment. Files in this directory have not been certified as official data. Source data may be sent to a model provider when an authorized CMPDI user invokes AI features.


## Versioned ZIP submissions

Production users can submit ZIPs through Data & reports. Sources are preserved in `<entity>/<family>/data/versions/<cadence>/<period>/<submission-id>/`; original ZIPs and manifests live in `<entity>/<family>/submissions/<submission-id>/`. `cil/reporting_schedule.json` is a generated schedule/last-update projection for all 35 report families. SQLite under `.processing` is authoritative. The catalog defaults to latest versions per period. See [pipeline contract](../context/18-SUBSIDIARY-INPUT-PIPELINE.md). PDFs/images are preserved pending extraction, not analysed.
