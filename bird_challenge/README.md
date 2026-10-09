# Bird Challenge — From BirdNET Predictions to Confirmed Observations

**Project:** Savanna Monitoring Pilot (SAVMON) — Lewa, Kenya
**BirdNET version:** v2.4

## Problem

BirdNET produces confidence scores (0–1) for acoustic species detections, but these
are not calibrated probabilities. The same score means something different for
different species. For each species, I derived the minimum confidence score that
achieves 99% precision, then labelled all 29,491 predictions as confirmed observations
or not.

## Data

- `birdnet_predictions.csv` — 29,491 BirdNET predictions from 43 sites, covering 4 species
- `validation_results.csv` — 551 ornithologist-validated clips (ground truth)

Validated clip breakdown:

| Species | Clips validated | BirdNET correct | % correct |
|---------|----------------|----------------|-----------|
| Abyssinian Nightjar | 150 | 117 | 78% |
| African Black-headed Oriole | 150 | 150 | 100% |
| Red-billed Firefinch | 101 | 6 | 6% |
| Three-banded Plover | 150 | 149 | 99% |

This is why a single global threshold fails — it would flood the output with false
Firefinch detections or discard valid Nightjar observations.

## Approach

I applied a logit transform to reverse BirdNET's internal sigmoid compression, then
fit a logistic regression per species on the logit-transformed scores:

```
pr(BirdNET is correct) = sigmoid( β₀ + β₁ × logit_score )
```

The 99%-precision threshold is derived analytically:

```
threshold = sigmoid( ( ln(0.99/0.01) − β₀ ) / β₁ )
```

Species with no positive validation examples use a fallback: the minimum observed
confidence score. The `bird_challenge.md` technical write-up discusses why this
method was chosen over alternatives (isotonic regression, Platt scaling, beta
calibration) — the logit-logistic model is analytically invertible, deployable
with two floats per species, and robust across species.

## Results

| Species | Threshold | Observations | Out of |
|---------|-----------|-------------|--------|
| Abyssinian Nightjar | 0.757 | 2,700 | 10,187 |
| African Black-headed Oriole | 0.104 | 17,646 | 18,054 |
| Red-billed Firefinch | 0.9996 | 0 | 235 |
| Three-banded Plover | 0.240 | 570 | 1,015 |
| **Total** | | **20,916** | **29,491** |

The Firefinch threshold of 0.9996 means zero predictions qualify — BirdNET cannot
be trusted for this species in this acoustic environment.

## Outputs

| File | Description |
|------|-------------|
| `outputs/species_thresholds.csv` | Per-species 99%-precision threshold |
| `outputs/model_evaluation.csv` | AUC, Brier, log-loss for all 5 models |
| `outputs/birdnet_predictions_labelled.csv` | All 29,491 predictions with observation label |
| `outputs/observation_summary.csv` | Confirmed observations per species |
| `outputs/site_observation_summary.csv` | Confirmed observations per species per site |
| `outputs/calibration_curves.png` | Calibration curves per species |
| `outputs/score_distributions.png` | Score distributions by validation outcome |
| `outputs/precision_recall_curves.png` | Precision-recall curves with thresholds |

## Requirements

```
pandas>=2.0.0
numpy>=2.0.0
scikit-learn>=1.3.0
scipy>=1.11.0
matplotlib>=3.7.0
```

```bash
pip install -r requirements.txt
```

## Running

Open `bird_challenge.ipynb` in Jupyter and run all cells. Place the raw data files
(`birdnet_predictions.csv`, `validation_results.csv`) in a `Data Birds/` directory
at the project root — they are not included in this repository due to size.

For the standalone production pipeline:

```bash
python bird_pipeline.py
```
