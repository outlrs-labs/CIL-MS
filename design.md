# CIL Reporting Workspace — UI/UX Specification

**Updated:** 2026-09-05  
**Source of truth:** The latest user-supplied screenshots take priority when a visual detail conflicts with an older mock-up.

## Design intent

The interface should feel like a compact enterprise desktop tool: direct, calm and information-dense without clutter. Each screen gives the user one obvious primary action. Use short labels, progressive disclosure and empty space instead of introductory paragraphs or decorative cards.

Blue translucent areas and red labels in reference screenshots are annotations, not permanent UI styling.

## Shell and layout

| Element | Desktop specification |
| --- | --- |
| Sidebar | 240 px wide, fixed, neutral surface, 1 px right border |
| Top bar | 56 px high, 1 px bottom border |
| Content | Fluid width, 24 px outer gutter, 21–34 px section gaps |
| Panels | Square or 2–4 px radius, quiet border, minimal shadow |
| Dialog | About 800 px wide and constrained to the viewport |
| Analysis | Fluid central canvas with persistent right chat/tools panel |

The sidebar contains the brand, primary navigation and account block. The header contains the current screen title, theme control and identity. Keep controls aligned to a simple column grid.

Below 850 px, collapse the sidebar behind a menu control and stack split panels. Below 600 px, allow Settings navigation to scroll horizontally and make dialogs fill the viewport with safe padding. Upload must work at 390 px.

## Typography and spacing

Use self-hosted **IBM Plex Sans** throughout the shell and embedded analytics workspace. Use monospace only for code, identifiers and machine values.

| Use | Size | Weight |
| --- | --- | --- |
| Caption / metadata | 12.6 px | 400–500 |
| Control / navigation | 14.2 px | 500 |
| Body / folder label | 16 px | 400–500 |
| Section heading | 20.35 px | 600 |
| Page title | 25.9 px | 600 |
| Prominent metric | 41.9 px | 600 |

Use the spacing scale `8, 13, 21, 34, 55`, body line height near 1.45 and heading line height near 1.2. Uppercase navigation is an explicit product requirement; body copy uses normal sentence case.

## Colour and themes

### Light

- Canvas/panel: `#ffffff`
- Secondary surface: `#f4f4f4`
- Primary text: `#262626`
- Secondary text: `#6f6f6f`
- Border: `#e0e0e0`

### Dark

- Canvas: `#161616`
- Panel: `#202020`
- Raised surface: `#2b2b2b`
- Primary text: `#f4f4f4`
- Border: `#454545`

Green `#198038` is the default accent. Appearance also offers IBM Blue `#0f62fe`, Purple `#8a3ffc`, Magenta `#d02670` and Teal `#007d79`. Use the accent for active navigation, primary actions, focus rings, selected cards and small status highlights. Do not flood panels with accent colour.

Use red for errors or destructive actions, amber for warnings and green for success/active states. Text and controls must meet WCAG AA contrast.

## Core components

- **Primary button:** solid accent, concise verb, 40–44 px minimum height.
- **Secondary button:** neutral or outline; use for Back, Filter, Refresh and Version Control.
- **Icon button:** 40 px target with an accessible label.
- **Input/select:** 40–44 px high, visible label, 1 px border and accent focus ring.
- **Panel:** title, optional one-line support text and focused content.
- **Metric card:** label, value and one short qualifier.
- **Table:** quiet row separators, sticky header when useful, actions at the right.
- **Folder/file card:** recognizable icon, name below, selected and keyboard-focus states.
- **Popover:** anchored and compact; Escape and outside click dismiss it.
- **Dialog:** title, optional one-line description, step content and stable footer actions.
- **Status badge:** short state only.
- **Empty state:** one icon, one title and one useful instruction/action.
- **Error state:** state what failed and how to recover; preserve user input.

## Screen composition

### Dashboard

The admin view uses a four-card metric row, hierarchy panel and entity/access tables. CMPDI emphasizes incoming submissions and technical coordination. Subsidiaries emphasize due cycles and the route `Subsidiary → CMPDI → CIL Central Admin`.

### UPLOAD

Show only the report-family selector, Upload action and a small Version Control action on the landing view. Place cadence, period, ZIP selection, confirmation and progress inside **Report → Package → Review → Submit**. History and schedule belong in Version Control.

### VAULT

Model Vault after a desktop file explorer. The toolbar contains Back, Forward, breadcrumbs, Search, Filter and Refresh. Use a spacious folder/file grid with names under the icons. Selection exposes one compact metadata row and Download. The filter popover contains Type, Updated and Sort; active filters become removable chips.

Do not add overview metrics, storage paths, version explanations, report-family cards or long helper text.

### ALALYSE

The idle view starts with **Choose data source**. Its source browser provides subsidiary chips, report family, search and file cards. Selected sources appear as compact chips; report destination stays collapsed until needed.

The active view keeps chart/table work central and chat/report tools at the right. Preserve zoom, chart controls, table preview, source mentions and model choice. Do not display upstream product names, installation links, license copy, copyright footers or unrelated metadata.

### AUDIT

Use a job list beside the review panel. Prioritize the original page and extracted table. Edit and Approve are separate actions. Show processing state without technical logs.

### DRAFT

Use a compact revision list with title, entity, family, version and created time. Group Complete package, Visual report, Markdown and Sources manifest downloads. Label every result as an analytical draft.

### Settings

Use secondary navigation with Overview; Account sections for Your profile, Login & security and Appearance; and Workspace sections for entity/team management. Appearance uses Light/Dark cards and five accent cards with swatches, descriptions and active state. CIL Admin sees Entity master and Team members; other roles see Subsidiaries.

## Required display labels

| Location | Text |
| --- | --- |
| Brand | `CIL MAGMENT SOFTWARE` |
| CMPDI/subsidiary navigation | `UPLOAD`, `VAULT`, `ALALYSE`, `AUDIT`, `DRAFT` |
| CMPDI account | `CMPDIL ADMIN` |

These presentation labels do not alter authorization. The only apex role is `cil_admin`; CMPDI is the technical coordinator.

## Interaction and accessibility

- Give every interactive element a visible focus state and accessible name.
- Preserve keyboard order; Escape closes popovers and non-busy dialogs.
- Never communicate status with colour alone.
- Use a compact progress state for waits and prevent double submission.
- Report success only after backend commit.
- Preserve selected files and form values after validation errors.
- Confirm destructive replacement or removal.
- Respect reduced-motion preferences.
- Apply appearance live and persist it locally under `cil.appearance.v1`.

## Implementation references

The shell and Settings use `frontend/src/WorkspaceChrome.tsx`, `App.tsx`, `Appearance.tsx` and their CSS. Main workspaces are `SubmissionWorkspace.tsx`, `VaultWorkspace.tsx`, `AnalyticsWorkspace.tsx` and `ExtractionWorkspace.tsx`. Backend Vault rules live in `backend/app/integration/vault.py`. Typography must load from local IBM Plex Sans assets.

