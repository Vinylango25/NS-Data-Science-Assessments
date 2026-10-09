# Natural State — Project Write-Up

## Overview

This repository contains my completed work for the Natural State Senior Data Scientist
take-home assessment. I worked on two independent challenges: acoustic bird detection
validation and vegetation survey QC/QA tooling.

---

## Bird Challenge

### Objective
Determine whether BirdNET confidence scores can be used as calibrated detection
probabilities, and derive per-species thresholds that achieve 99% precision.

### What I did
- Loaded and joined 29,491 BirdNET predictions with 1,529 human-validated clips across 23 species
- Assessed whether the validation set is representative of the full predictions using KS tests, chi-squared bin coverage, site overlap, and EPV checks
- Fit five calibration models per species: logistic on raw scores, logistic on logit-transformed scores, isotonic regression, Platt scaling, beta calibration
- Selected the best model per species using AUC, Brier score, and log-loss
- Derived the minimum confidence threshold per species achieving >= 99% precision analytically (M2 logit model) or via precision-recall curve fallback
- Labelled all 29,491 predictions and produced site-level observation summaries

### Key findings
- BirdNET scores are not well-calibrated out of the box — raw scores overestimate confidence at the high end for most species
- Logistic regression on logit-transformed scores (M2) was the best-performing model for the majority of species
- 99%-precision thresholds vary substantially across species (range ~0.5-0.95), making a single global threshold inappropriate
- The labelled dataset and per-species thresholds are ready for downstream biodiversity reporting

### Outputs
| File | Description |
|------|-------------|
| `outputs/species_thresholds.csv` | Per-species threshold and best model |
| `outputs/model_evaluation.csv` | Full model comparison per species |
| `outputs/birdnet_predictions_labelled.csv` | All predictions with observation label |
| `outputs/site_observation_summary.csv` | Confirmed detections per species per site |

---

## Vegetation Challenge

### Objective
Build a QC/QA tool for herbaceous vegetation survey data collected via ODK,
implementing automated checks to flag data quality issues before analysis.

### What I built
A full-stack web application with:
- **FastAPI backend** — loads ODK CSV exports, joins them, runs 14 automated checks, stores results in SQLite
- **React frontend** (Vite + Tailwind) — Dashboard, Surveys, Map, Scorecard, and Species Queue pages
- **Static JSON export** — zero-backend Vercel deployment mode

### QC checks implemented
| Code | Level   | Check |
|------|---------|-------|
| S1   | Survey  | GPS coordinate validity |
| S2   | Survey  | Observer recorded |
| S3   | Survey  | Survey date within expected range |
| S4   | Survey  | Plot ID matches registered plots |
| P1   | Plot    | Canopy cover within bounds (0-100%) |
| P2   | Plot    | Basal area recorded |
| P3   | Plot    | Ecosystem type matches expected for plot |
| P4   | Plot    | Duplicate plot-survey combinations |
| Q1   | Quadrat | Expected number of quadrats per plot |
| Q2   | Quadrat | Cover values sum within bounds |
| Q3   | Quadrat | Bare ground + litter + vegetation <= 100% |
| Q4   | Quadrat | Height values within plausible range |
| Q5   | Quadrat | Missing quadrat data |
| R1   | Species | Species name not in reference list |

---

## Repository Structure

```
NS-Data-Science-Assessments/
├── bird_challenge/
│   ├── Data Exploration.ipynb        # SAVMON EDA — bird and vegetation
│   ├── bird_challenge.ipynb          # Full calibration analysis
│   ├── bird_pipeline.py              # Standalone pipeline for dev team
│   ├── requirements.txt
│   └── outputs/
└── veg_qaqc_tool/
    ├── export_static_data.py
    ├── backend/
    │   ├── main.py
    │   ├── requirements.txt
    │   ├── railway.toml
    │   └── app/
    │       ├── pipeline/
    │       ├── api/
    │       ├── db/
    │       └── core/
    └── frontend/
        ├── src/
        │   ├── pages/
        │   ├── components/
        │   ├── api/
        │   └── hooks/
        └── public/data/
```
