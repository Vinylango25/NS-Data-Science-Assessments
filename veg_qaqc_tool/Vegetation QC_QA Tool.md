# Vegetation Data Quality — From Assessment to Production Tool

**Project:** SAVMON Baseline 2026 · Lewa Wildlife Conservancy, Kenya  
**Live demo:** https://frontend-sandy-tau-56.vercel.app  
**Data:** 32 surveys · 31 plots · 640 quadrats · 211 QC flags

---

## The problem this tool solves

Natural State collects vegetation data through ODK Central. Field teams survey
50 m transects, recording herb species across 20 quadrats per plot. That data
flows through four ODK tables and two entity lists before it can feed any
biodiversity model — and at every step there are ways the data can be wrong.

The standard approach is to write a QA script, run it once, fix the issues, and
move on. We didn't do that, because it breaks the moment new data arrives. The
2026 baseline has 32 surveys. The 2027 monitoring round will have another 30.
Running a script once means every new field season produces a fresh backlog of
unflagged issues.

Instead we built a pipeline that runs the same checks every time new data arrives,
surfaces every issue on a live dashboard, and clears flags automatically when
issues are resolved. The same system that produced this assessment is the system
that runs in production.

---

## What we found in the 2026 data

**The good:** 30 of 30 viable plots were surveyed — complete coverage. All 640
quadrats were completed. 98.9% of quadrats recorded herbs present. No GPS accuracy
failures, no herbs-present inconsistencies.

**The issues that block analysis (HIGH severity):**

Plot_21 and Plot_18 were rejected by the ODK Central reviewer and both have
duplicate submissions. Until these are resolved, both plots appear in the dataset
twice — any species richness or occupancy model that treats surveys as independent
samples will double-count them. This is a data integrity problem, not a formatting
issue. It must be fixed before the data is used.

**The issues that need attention before final analysis (MEDIUM severity):**

107 species were recorded in the field under provisional identifiers — either
because the plant wasn't recognisable to the recorder, or because it was absent
from the pre-loaded species list. Species richness counts for every affected plot
are lower bounds until a botanist confirms or rejects each entry. This is not a
data collection failure — it is normal in species-rich savanna — but the queue
needs to be cleared.

Seven plots have transect lengths outside the 40–60 m SOP range. The dataset
average is 49.1 m, so there is no systematic problem. Plot_19 at 22.6 m and
Plot_27 at 28.6 m are notably short and worth re-measuring. Plot_08 has a
recorded survey duration of 236 minutes — the timer was left running after
completion; the species data is unaffected.

**The issues to fix before name-matching (LOW severity):**

64 species names have trailing whitespace and 45 are not in the required
`Genus_species` underscore format. These do not affect species counts, but they
will cause silent join failures against GBIF or any external taxonomic database
if not cleaned before name-matching analysis.

---

## How the pipeline works

Six inputs come from ODK Central. Three fields are computed by the pipeline
because they don't exist in the raw form output:

```
duration_min       = (end_time − start_time) / 60
transect_length_m  = haversine(ep_a, ep_b)
midpoint_offset_m  = haversine(recorded_midpoint, plot_centroid)
```

The transect length is computed from the GPS endpoints recorded in the form — it
is an independent ground-truth measurement of how far the tape was actually laid,
regardless of what the recorder typed. The midpoint offset measures how far the
transect drifted from the registered plot centroid — the spatial anchor that makes
repeat monitoring possible.

The pipeline then runs 14 checks against the joined data. Each check produces
zero or more flag rows. Every run is a complete replace: if a rejected survey is
re-submitted and approved, or a botanist confirms a pending species, the
corresponding flag disappears on the next run without any manual intervention.
The dashboard always shows the current state of the data.

---

## The 14 checks and why each one exists

**Survey level**

| Code | Check | Severity | Why |
|------|-------|----------|-----|
| S1 | Survey rejected by ODK reviewer | HIGH | A rejected survey has been flagged by the review team. It cannot appear in analysis under any circumstances. |
| S2 | Duplicate approved survey for same plot | HIGH | Two approved surveys for one plot will double-count that plot in any richness or occupancy model. |
| S3 | Duration outside 10–180 min | MEDIUM | Above 180 min the timer was left running after the survey ended. Below 10 min the form was submitted before the survey was complete. |
| S4 | Plot UUID not in vegplots entity list | HIGH | Without a confirmed plot match there is no way to geolocate, deduplicate, or validate the survey. |

**Plot level**

| Code | Check | Severity | Why |
|------|-------|----------|-----|
| P1 | Viable plot not surveyed | MEDIUM | An unsurveyed viable plot is a sampling gap. Its absence contributes an ambiguous zero to occupancy models — was the species absent, or was it just not surveyed? |
| P2 | Non-viable plot surveyed | MEDIUM | Non-viable plots (destroyed, inaccessible) are excluded from richness estimates. Including one inflates or deflates the summary depending on its condition. |
| P3 | Transect length outside 40–60 m | MEDIUM | Quadrats are placed at fixed intervals along the transect. A shorter or longer tape distorts the spatial distribution of the sample. |
| P4 | Midpoint more than 25 m from registered centroid | MEDIUM | The centroid is the permanent anchor for repeat monitoring. A displaced midpoint means successive survey seasons are sampling different ground. |

**Quadrat level**

| Code | Check | Severity | Why |
|------|-------|----------|-----|
| Q1 | GPS accuracy greater than 5 m | LOW | Above 5 m the coordinate cannot reliably relocate the quadrat for a repeat visit. |
| Q2 | herbs_present = Yes with zero species | MEDIUM | The recorder marked herbs present but listed nothing. This is a data entry omission that suppresses the true species count for that quadrat. |
| Q3 | herbs_present = No with species listed | MEDIUM | The quadrat contributes to species richness while also appearing to have zero herb cover — an internal contradiction that breaks any cover-to-richness analysis. |
| Q4 | Trailing whitespace in canonical name | LOW | `"Evolvulus alsinoides "` and `"Evolvulus alsinoides"` are treated as different strings by every database join and GBIF API lookup. A trailing space is invisible in a spreadsheet and causes silent failures in code. |
| Q5 | Name not in Genus_species format | LOW | The SOP requires underscore-separated binomials. Space-separated or single-word names will not match GBIF's taxonomic backbone without manual correction. |

**Species level**

| Code | Check | Severity | Why |
|------|-------|----------|-----|
| R1 | Additional species pending taxonomic review | MEDIUM | Names entered as `new_unknown` or `new_missing` have not been confirmed by a botanist. Richness counts that include them are optimistic upper bounds. |

---

## The dashboard — what it shows and to whom

The live tool at https://frontend-sandy-tau-56.vercel.app has six pages, each
aimed at a different user:

**Dashboard** — The project manager's view. Headline numbers at a glance:
plots surveyed, surveys approved, quadrats completed, pending species count,
total flag breakdown by severity. A bar chart of flags by type immediately shows
where the quality work is concentrated.

**Scorecard** — The field coordinator's reference. All 14 checks in a single
table with plain-English explanations of why each one matters. The page to open
when a new coordinator asks "what does this flag mean?"

**Surveys** — The data manager's working list. All 32 submissions, filterable
by QC status, review state, or recorder name. Click any row to see the full flag
list for that survey with field values and expected values.

**Species Queue** — The botanist's action list. 107 provisional entries, each
showing the provisional identifier, the validated name if one has been assigned,
and the entry mode (unknown plant vs missing from master list).

**Map** — Spatial overview. All 31 transects as A→B lines on a Leaflet map,
colour-coded green (pass) / amber (warning or fail). Clicking any transect shows
species count, transect length, and flag count for that plot.

**Report** — The assessment response. Dynamically generated from the live data —
all numbers are computed at load time, so the report is always current.

---

## Embedding this into NS Analytics

This tool was built as a standalone demonstration, but the intended end state
is for the QC pipeline to run natively inside NS Analytics — not as a separate
service the platform connects to, but as a first-class feature of the platform
itself. This section describes what that looks like for the Dev Team.

### The model: pipeline as a service inside NS Analytics

NS Analytics already handles ODK data ingestion, entity list management, and
user authentication. The QC pipeline fits into that infrastructure as a
background worker. The architecture is:

```
ODK Central
    │
    ▼ webhook (new submission / entity update)
NS Analytics backend
    │
    ├── existing ingestion logic (unchanged)
    │
    └── VegQC worker (new)
            │
            ├── reads from existing NS Analytics tables (no new data sources)
            ├── runs 14 checks
            ├── writes to veg_qc_flags and veg_qc_runs tables
            └── signals the frontend that fresh results are available
```

The pipeline does not need its own database. It reads from the tables that
NS Analytics already populates from ODK and writes results to two new tables.
Everything else — authentication, project management, user permissions — is
inherited from NS Analytics as-is.

### What the Dev Team adds to NS Analytics

**Two new database tables** — the pipeline writes to these and the API reads from them:

```sql
CREATE TABLE veg_qc_runs (
    id                SERIAL PRIMARY KEY,
    run_at            TIMESTAMPTZ DEFAULT now(),
    project_id        INTEGER REFERENCES projects(id),
    data_source       VARCHAR(16),
    status            VARCHAR(16),   -- queued | running | complete | error
    n_surveys         INTEGER,
    n_flags_high      INTEGER,
    n_flags_medium    INTEGER,
    n_flags_low       INTEGER,
    n_pending_species INTEGER
);

CREATE TABLE veg_qc_flags (
    id              SERIAL PRIMARY KEY,
    run_id          INTEGER REFERENCES veg_qc_runs(id),
    flag_id         VARCHAR(3),    -- S1, P3, Q4, R1, etc.
    flag_type       VARCHAR(64),
    severity        VARCHAR(8),    -- HIGH | MEDIUM | LOW
    survey_key      TEXT,
    plot_name       VARCHAR(64),
    quadrat_number  INTEGER,
    field_value     TEXT,
    expected_value  TEXT,
    description     TEXT
);
```

**One background worker** — the QC pipeline, reading from NS Analytics tables:

```python
# veg_qaqc_tool/backend/app/pipeline/qc_service.py
# Port this to read from NS Analytics tables instead of CSV files.
# The check logic is identical — only the data source changes.
# All 14 checks are documented with their SOP clause in this file.
```

**Eight API endpoints** — added to the NS Analytics API under `/api/v1/veg/`:

```
GET  /api/v1/veg/dashboard           → headline counts + flag_type_summary
GET  /api/v1/veg/surveys             → paginated survey list with flag counts
GET  /api/v1/veg/surveys/{key}       → single survey + flags + narrative
GET  /api/v1/veg/plots               → plot list with transect metrics
GET  /api/v1/veg/flags               → paginated flag list with filters
GET  /api/v1/veg/species-queue       → provisional species awaiting review
POST /api/v1/veg/runs                → trigger a QC run
GET  /api/v1/veg/runs                → run history
```

The full response contracts are in `src/api/client.js`. The frontend calls
these endpoints exactly as documented — no changes needed on the frontend side.

**One webhook handler** — added to the existing ODK Central webhook receiver:

```python
# When NS Analytics receives a webhook from ODK Central:
if event.type in ('submission.create', 'entity.update'):
    if event.form in VEG_FORMS:
        enqueue_qc_run(project_id=event.project_id)
```

Entity list updates (a botanist confirming a pending species, a plot deactivated)
should also trigger a run. The pipeline is idempotent — running it twice on the
same data produces identical output, so there is no cost to over-triggering.

### Configurable thresholds per project

These six values must be stored in NS Analytics project configuration, not
hard-coded. Different monitoring sites use different protocols:

| Parameter | Default | SOP | Rationale |
|-----------|---------|-----|-----------|
| `max_duration_min` | 180 | §5.13 | A 20-quadrat survey should take 1–3 hours. |
| `min_transect_m` | 40 | §3.1 | ±20% of the 50 m target. |
| `max_transect_m` | 60 | §3.1 | ±20% of the 50 m target. |
| `max_midpoint_m` | 25 | §5.5 | Half the transect length. |
| `max_gps_accuracy_m` | 5 | §4.2 | Typical open-savanna GPS performance. |
| `quadrats_per_survey` | 20 | §3.1 | Fixed by SAVMON protocol. |

### Embedding the frontend

The React frontend in `veg_qaqc_tool/frontend/` can be embedded in NS Analytics
as an iframe, a micro-frontend, or ported component-by-component into the NS
Analytics UI framework. The simplest path is to serve it as a sub-application
under the NS Analytics domain:

```
https://analytics.naturalstate.org/projects/{id}/veg-qc
```

Set these two environment variables and the frontend routes its API calls
through NS Analytics — no other changes:

```
VITE_STATIC=false
VITE_API_URL=https://analytics.naturalstate.org
```

### What this tool does not replace

NS Analytics handles authentication, project management, user roles, and
data storage. The QC pipeline adds a layer on top of that: it reads the data
that already exists in NS Analytics, runs the checks, and writes the results
back. It does not duplicate or bypass any existing NS Analytics functionality.

---

*Natural State Analytics · SAVMON Baseline 2026 · Lewa Wildlife Conservancy*
