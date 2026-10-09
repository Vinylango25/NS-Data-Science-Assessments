# Natural State — Project Write-Up

**Project:** Savanna Monitoring Pilot (SAVMON) · Lewa Wildlife Conservancy, Kenya

This repository contains my completed work for the Natural State Senior Data Scientist
take-home assessment, covering two independent challenges.

---

## Bird Challenge

### Objective

BirdNET produces confidence scores (0–1) for acoustic species detections, but these
are not calibrated probabilities — the same score means something different for
different species. I derived a per-species confidence threshold achieving 99% precision,
then labelled all predictions as confirmed observations or not.

### Data

- **29,491 BirdNET v2.4 predictions** from 43 acoustic monitoring sites at Lewa, covering 4 species
- **551 ornithologist-validated clips** with ground-truth labels

Validated clip breakdown before any modelling:

| Species | Clips validated | BirdNET correct | % correct |
|---------|----------------|----------------|-----------|
| Abyssinian Nightjar | 150 | 117 | 78% |
| African Black-headed Oriole | 150 | 150 | 100% |
| Red-billed Firefinch | 101 | 6 | 6% |
| Three-banded Plover | 150 | 149 | 99% |

This is why a single global threshold fails — it would flood the output with false
Firefinch detections or discard valid Nightjar observations.

### Approach

I applied a logit transform to the raw scores to reverse BirdNET's internal sigmoid
compression, then fit and compared 5 calibration models per species:

| Method | Description |
|--------|-------------|
| M1 | Logistic regression on raw scores |
| M2 ★ | Logistic regression on logit-transformed scores (chosen) |
| M3 | Isotonic regression |
| M4 | Platt scaling |
| M5 | Beta calibration |

Models were evaluated on AUC, Brier score, and log-loss. M2 was selected as the
production method: nearly as accurate as isotonic regression, analytically invertible
(the threshold is a single formula), and robust across species.

For each species, the 99%-precision threshold was derived analytically:

```
threshold = sigmoid( ( ln(0.99/0.01) − β₀ ) / β₁ )
```

### Results

| Species | Threshold | Predictions | Confirmed observations |
|---------|-----------|-------------|----------------------|
| Abyssinian Nightjar | 0.757 | 10,187 | 2,700 (26.5%) |
| African Black-headed Oriole | 0.104 | 18,054 | 17,646 (97.7%) |
| Red-billed Firefinch | 0.9996 | 235 | 0 (0%) |
| Three-banded Plover | 0.240 | 1,015 | 570 (56.2%) |
| **Total** | | **29,491** | **20,916 (70.9%)** |

The Firefinch threshold of 0.9996 means no predictions qualify — BirdNET cannot be
trusted for this species in this acoustic environment. Manual review is required.

### Outputs

| File | Description |
|------|-------------|
| `outputs/species_thresholds.csv` | Per-species 99%-precision threshold |
| `outputs/model_evaluation.csv` | AUC, Brier, log-loss for all 5 models |
| `outputs/birdnet_predictions_labelled.csv` | All 29,491 predictions with observation label |
| `outputs/site_observation_summary.csv` | Confirmed detections per species per site |
| `outputs/calibration_curves.png` | Calibration curves per species |
| `outputs/score_distributions.png` | Score distributions by validation outcome |
| `outputs/precision_recall_curves.png` | Precision-recall curves with thresholds |

---

## Vegetation Challenge

### Objective

Build a QC/QA pipeline for herbaceous vegetation survey data collected via ODK,
implementing automated SOP-based checks to flag data quality issues before analysis.

### What I found in the 2026 data

- 30 of 30 viable plots surveyed — complete coverage
- 640 quadrats completed, 98.9% with herbs present
- **HIGH** — Plot_21 and Plot_18 rejected with duplicates: double-count risk in any
  richness or occupancy model. Must be resolved before analysis.
- **MEDIUM** — 107 provisional species identifiers pending botanist review: species
  richness counts are lower bounds until cleared
- **MEDIUM** — 7 plots with transect lengths outside 40–60 m SOP range; Plot_08
  duration of 236 min (timer left running after completion)
- **LOW** — 64 names with trailing whitespace, 45 not in `Genus_species` format:
  will cause silent join failures against external taxonomic databases

### What I built

A full-stack web application:

- **FastAPI backend** — loads ODK CSV exports (or PostgreSQL in production), joins
  survey, quadrat, species, and plot registration tables, runs 14 SOP-based checks,
  stores results in SQLite, and generates plain-English AI narratives per survey via
  Groq (with rule-based fallback)
- **React frontend** (Vite + Tailwind) with 6 pages: Dashboard, Scorecard, Surveys,
  Species Queue, Map, and Report
- **Static JSON export** for zero-backend Vercel deployment

Live demo: https://frontend-sandy-tau-56.vercel.app

### QC checks implemented

| Code | Level   | Severity | Check |
|------|---------|----------|-------|
| S1   | Survey  | HIGH     | Survey rejected by ODK reviewer |
| S2   | Survey  | HIGH     | Duplicate approved survey for the same plot |
| S3   | Survey  | MEDIUM   | Duration outside 10–180 min |
| S4   | Survey  | HIGH     | Plot UUID not in vegplots entity list |
| P1   | Plot    | MEDIUM   | Viable plot not surveyed |
| P2   | Plot    | MEDIUM   | Non-viable plot surveyed |
| P3   | Plot    | MEDIUM   | Transect length outside SOP range (40–60 m) |
| P4   | Plot    | MEDIUM   | Midpoint more than 25 m from registered centroid |
| Q1   | Quadrat | LOW      | GPS accuracy greater than 5 m |
| Q2   | Quadrat | MEDIUM   | herbs_present = Yes with zero species listed |
| Q3   | Quadrat | MEDIUM   | Species listed but herbs_present = No |
| Q4   | Species | LOW      | Trailing whitespace in canonical name |
| Q5   | Species | LOW      | Name not in Genus_species format |
| R1   | Species | MEDIUM   | Additional species pending taxonomic review |

### Architecture

- Backend deployed on Railway (FastAPI + SQLite, configurable for PostgreSQL via
  `DATA_SOURCE=postgres` env var)
- Frontend deployed on Vercel
- Designed for embedding into NS Analytics as a background worker reading from
  existing NS Analytics tables — no duplicate data storage required

---

## Repository Structure

```
NS-Data-Science-Assessments/
├── bird_challenge/
│   ├── Data Exploration.ipynb        # SAVMON EDA — bird and vegetation data
│   ├── bird_challenge.ipynb          # Full calibration analysis notebook
│   ├── bird_pipeline.py              # Standalone production pipeline
│   ├── bird_challenge.md             # Full technical write-up
│   ├── requirements.txt
│   └── outputs/                      # CSVs and diagnostic plots
└── veg_qaqc_tool/
    ├── export_static_data.py         # Pre-exports JSON for static Vercel deploy
    ├── Vegetation QC_QA Tool.md      # Full technical write-up
    ├── backend/
    │   ├── main.py
    │   ├── requirements.txt
    │   ├── railway.toml
    │   ├── .env.example
    │   └── app/
    │       ├── pipeline/             # ODK loader + 14 QC checks
    │       ├── api/                  # REST route handlers
    │       ├── narrative/            # Groq AI narrative generator
    │       ├── db/                   # SQLite models and session
    │       └── core/                 # Settings and config
    └── frontend/
        ├── src/
        │   ├── pages/
        │   ├── components/
        │   ├── api/
        │   └── hooks/
        └── public/data/              # Pre-exported static JSON
```
