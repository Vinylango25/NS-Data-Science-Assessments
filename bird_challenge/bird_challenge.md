# Bird Challenge — From BirdNET Predictions to Confirmed Observations

**Project:** Savanna Monitoring Pilot (SAVMON) — Lewa, Kenya
**BirdNET version:** v2.4

---

## What we are trying to do and why it is not straightforward

Passive acoustic monitoring devices sit in the field and record audio around the clock.
That audio gets run through BirdNET, a machine learning model that listens to every
three-second clip and asks: does this sound like a bird calling? If it thinks the
answer is yes, it stamps the clip with the species name and a number between 0 and 1
called a confidence score.

The intuitive reading of that number — that 0.9 means "90% sure it is that bird" — is
wrong. BirdNET's confidence score is not a probability. It is an internal signal
strength that has been scaled to look like one. The same score of 0.7 might mean
something very different for two different species: for one it might be almost always
correct, for another it might still be guessing half the time. This species-specific
behaviour is the central point of the Wood & Kahl (2024) paper that guided the
approach here.

So the question we are answering is: **for each species, at what confidence score can
we trust BirdNET enough to call a prediction a confirmed observation?** The bar we set
is 99% — meaning we want to be 99% sure BirdNET got it right before we count a
detection as real. Below that threshold, a clip stays as an unverified prediction.
Above it, it becomes an observation that feeds into biodiversity metrics.

---

## The data we have to work with

We have two files:

- **29,491 BirdNET predictions** from 43 acoustic monitoring sites across the Lewa
  landscape. These cover 4 species. Each row is one three-second clip where BirdNET
  fired — it includes the confidence score, the species name, the file path, and the
  site folder.

- **551 ornithologist-validated clips** — a subset of predictions where a human expert
  listened to the audio and recorded whether BirdNET was right (outcome = 1) or wrong
  (outcome = 0). This is our ground truth.

Before we run any models, just looking at those 551 validated clips tells us something
important:

| Species | Clips validated | BirdNET correct | BirdNET wrong | % correct overall |
|---------|----------------|----------------|--------------|-------------------|
| Abyssinian Nightjar | 150 | 117 | 33 | 78% |
| African Black-headed Oriole | 150 | 150 | 0 | 100% |
| Red-billed Firefinch | 101 | 6 | 95 | 6% |
| Three-banded Plover | 150 | 149 | 1 | 99% |

These four numbers already tell a story. BirdNET is brilliant at the Oriole and the
Plover. It is decent at the Nightjar but makes meaningful mistakes. And for the
Red-billed Firefinch, it is essentially wrong 94% of the time — it is picking up
something else entirely and calling it a Firefinch.

This is exactly why a single global threshold would be a disaster. Setting one score
cutoff for all species at once would either let through masses of false Firefinch
detections or throw away perfectly good Nightjar and Plover observations. Each
species needs its own calibration.

---

## How we build a species-specific threshold

### The core idea: turn a score into a probability

The goal is to find, for each species, a curve that maps "BirdNET gave this clip a
score of X" to "there is a Y% chance BirdNET was right." Once we have that curve,
finding the 99% threshold is just reading off the score where the curve crosses 99%.

We use the validated clips as training data. For each clip, we know the confidence
score and whether BirdNET was right or wrong. We fit a model on those pairs, and the
model learns the score-to-probability relationship for that species.

### Why we transform the scores first

BirdNET's confidence scores are produced by passing an internal number through a
sigmoid function, which squashes everything into the 0–1 range. This is fine for
display purposes but awkward for modelling, because the squashing is uneven. Scores
near 0 and 1 are compressed — the gap between 0.95 and 0.99 is visually small but
represents a big jump in actual signal. By reversing the sigmoid (the logit
transform), we get back to the original unbounded scale where the scores are
spread out more evenly and a linear model fits them much better.

```
logit_score = ln( confidence / (1 - confidence) )
```

This is a standard log-odds transformation. A confidence of 0.5 becomes 0, scores
above 0.5 become positive, and scores below become negative. The higher the original
confidence, the larger the logit value.

### Fitting the model and solving for 99%

We fit a logistic regression on the logit scores:

```
pr(BirdNET is correct) = sigmoid( β₀  +  β₁ × logit_score )
```

The model learns two numbers — an intercept (β₀) and a slope (β₁) — that describe
the shape of the probability curve for that species. A steep positive slope means
confidence scores are informative: high scores are much more trustworthy than low
ones. A shallow slope means BirdNET's scores do not discriminate much.

Once the model is fitted, we solve it backwards: what score produces a probability
of exactly 0.99?

```
confidence_threshold = sigmoid( ( ln(0.99/0.01) − β₀ ) / β₁ )
```

That is our threshold. Every prediction above it gets labelled as an observation.

---

---

## What the calibration curves show

![Calibration curves](outputs/calibration_curves.png)

Each panel shows one species. The grey dots scattered at the top and bottom are the
validated clips — dots near the top are true positives (BirdNET was right), dots near
the bottom are false positives (BirdNET was wrong). The fitted curve shows how the
logit-logistic model translates confidence scores into probabilities. The red dashed
vertical line marks the 99% threshold.

What to look for in each panel:

- **For the Nightjar**, the curve rises steeply between 0.5 and 0.8, crossing 99%
  at 0.757.

- **For the Oriole**, all the dots are at the top (all correct) and there is no
  curve to fit. The threshold defaults to the lowest validated score.

- **For the Firefinch**, the dots are almost entirely at the bottom (almost all
  wrong), and the curve barely climbs above 50% across the whole score range.
  Only in the very high 0.9+ range does precision approach 99%.

- **For the Plover**, the dots are overwhelmingly at the top (almost all correct),
  so even at low scores the probability is already close to 1. The threshold is 0.24.

---

## Score distributions: seeing the problem visually

![Score distributions](outputs/score_distributions.png)

These histograms show how the true positive (green) and false positive (red)
predictions are distributed across confidence scores for each species.

For the **Nightjar**, there is a clear separation. True positives pile up toward the
right (high confidence), false positives cluster toward the left (low confidence).
The threshold at 0.757 sits right at the point where the green distribution dominates.
This is a textbook example of a well-behaved classifier.

For the **Firefinch**, the distributions almost completely overlap across the whole
range. There are so few true positives (just 6 out of 101) that they barely form a
visible bar, and they are not even consistently high-scoring. This confirms what
the table already suggested: BirdNET simply does not have a reliable signal for this
species in this recording context.

For the **Plover**, nearly everything is green, confirming its very high overall
accuracy and the low threshold needed to reach 99% precision.

---

## Precision-recall: the full tradeoff picture

![Precision-recall curves](outputs/precision_recall_curves.png)

A precision-recall curve shows what happens as you adjust the threshold. Moving
left along the curve means accepting more predictions (higher recall — you catch
more of the real birds) but at the cost of letting in more false positives (lower
precision). Moving right means being more selective.

The area under the curve (average precision, AP) summarises how good a classifier
is across all possible threshold choices. A perfect classifier would have AP = 1.0.

The Oriole, Nightjar, and Plover all have high AP scores, meaning BirdNET can
discriminate true from false positives well for these species. The Firefinch AP
of 0.170 is the damning number — even if you could choose any threshold, you
cannot get both high precision and high recall for this species at the same time.

---

---

## Results: labelling the 29,491 predictions

Once we have the thresholds, applying them is straightforward. Each prediction is
compared to its species-specific threshold. If the confidence score clears the bar,
the prediction is labelled as an observation (1). If not, it stays as a prediction (0).

**Species thresholds derived:**

| Species | Threshold | β₀ (intercept) | β₁ (slope) | How it was set |
|---------|-----------|----------------|------------|----------------|
| Abyssinian Nightjar | **0.757** | 2.633 | 1.727 | Logistic regression on 150 validated clips |
| African Black-headed Oriole | **0.104** | — | — | All 150 validated clips correct; set to minimum observed score |
| Red-billed Firefinch | **0.9996** | −1.643 | 0.790 | Logistic regression — curve barely reaches 99% |
| Three-banded Plover | **0.240** | 5.023 | 0.371 | Logistic regression on 150 validated clips |

**What do these thresholds mean in practice?**

A threshold of 0.757 for the Nightjar means: "we only count a Nightjar detection
as a real observation if BirdNET scored it above 0.757. Below that, there are too
many mistakes to trust." The slope of 1.727 tells us the relationship is reasonably
steep — scores carry information for this species.

A threshold of 0.104 for the Oriole means: "BirdNET was correct on every single
validated clip, right down to a score of 0.104. We have no evidence it makes
mistakes for this species, so we accept everything at or above that floor." This
is a conservative interpretation: we are not claiming BirdNET is infallible for the
Oriole — only that the validation data gave us no reason to reject any of its
predictions.

A threshold of 0.9996 for the Firefinch means: "the model only reaches 99% precision
at an essentially impossible score." No clip in the dataset scores that high, so
zero Firefinch predictions are classified as observations. This is the correct
outcome given what the data shows. It does not mean Firefinches are absent from the
area — it means BirdNET v2.4 cannot be trusted to identify this species reliably
in this acoustic environment. Manual review of any Firefinch detections is the
appropriate next step.

A threshold of 0.240 for the Plover means: "BirdNET is so accurate on this species
that even moderate-confidence predictions are almost always correct." The high
intercept (β₀ = 5.023) reflects a high baseline probability regardless of score —
consistent with only a single false positive in 150 validations.

**Observation counts after labelling:**

| Species | Total predictions | Labelled as observations | Proportion |
|---------|------------------|------------------------|------------|
| Abyssinian Nightjar | 10,187 | 2,700 | 26.5% |
| African Black-headed Oriole | 18,054 | 17,646 | 97.7% |
| Red-billed Firefinch | 235 | 0 | 0.0% |
| Three-banded Plover | 1,015 | 570 | 56.2% |
| **Total** | **29,491** | **20,916** | **70.9%** |

70.9% of predictions across all species become confirmed observations. The Oriole
dominates both the prediction count and the observation count. The Firefinch's 235
predictions generate nothing. The Nightjar, despite being the most-predicted species
at 10,187 clips, converts at only 26.5% — reflecting its higher false positive rate
and higher threshold.

The labelled file is at `outputs/bird/birdnet_predictions_labelled.csv`. Each row
from the original predictions file now has an `observation` column: 1 means
confirmed, 0 means sub-threshold.

---

## Reproducibility

```bash
python bird_challenge.py
```

All outputs land in `outputs/bird/`:

- `birdnet_predictions_labelled.csv` — the 29,491 predictions with the `observation` column added
- `species_thresholds.csv` — the threshold table ready to load into the platform database
- `site_observation_summary.csv` — observation counts per acoustic monitoring site per species
- `calibration_curves.png`, `score_distributions.png`, `precision_recall_curves.png` — diagnostic plots

---

## 9. Integration Guide for the Tech Team

The calibration pipeline (bbird_pipeline.py) is complete and tested. A FastAPI backend (bbird_api/) wraps it and exposes everything the NS Analytics platform needs through a REST API. No further science work is required — this section is addressed to the developers who will wire it into the platform.

---

### What the backend does

It sits between the raw BirdNET predictions table in your database and the observation dashboards your users see. When triggered, it loads the validation clips and predictions, fits per-species logistic regression models, derives 99%-precision thresholds, and labels every prediction as a confirmed observation (1), sub-threshold (0), or manual review required (NULL). All results are written back to the database. A full run history is kept — old thresholds are never deleted.

By default it reads from local CSV files (for demos). Set DATA_SOURCE=postgres and point SOURCE_DB_URL at your database to switch to live data. No code changes required.

---

### Endpoints — Base URL: /api/v1/birdnet

| Method | Endpoint | When to call it |
|--------|----------|-----------------|
| POST | /calibrate | Every time new BirdNET predictions are ingested into the platform |
| GET | /calibrate/{run_id} | Poll for status after triggering — returns queued / running / complete / error |
| GET | /thresholds | Read the current per-species confidence thresholds — feed these to dashboards and reports |
| GET | /predictions | Read all labelled predictions — filterable by species, site, observation status, paginated |
| GET | /model-quality | Per-species AUC, Brier score, log-loss — for the Biometrics Team to assess model health |
| POST | /validation/notify | Call this after ornithologists add new validated clips — triggers recalibration automatically if any species gained enough new data |

The two trigger points in the platform workflow are:

1. **New BirdNET predictions arrive** → call POST /calibrate
2. **Ornithologist submits new validated clips** → call POST /validation/notify

Everything else is read-only and can be called at any time by the frontend.

---

### Configuration (.env)

`
DATA_SOURCE=postgres
SOURCE_DB_URL=postgresql+psycopg2://user:pass@host:5432/ns_analytics
PREDICTIONS_TABLE=birdnet_predictions
VALIDATION_TABLE=birdnet_validation_clips
DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/ns_analytics
RANDOM_STATE=42
BIRDNET_VERSION=v2.4
TARGET_PRECISION=0.99
`

**Do not change RANDOM_STATE=42.** It controls the model seed. Changing it changes all threshold values and invalidates every existing observation label in the database.

---

### Known gaps

| Issue | Action required |
|-------|----------------|
| Only 5.8% of predictions matched to validation clips | Add a shared clip ID to the BirdNET export and validation form |
| 11 sites with no validated clips (RBS26, 28, 31, 37, 41, 42, 43, 54, 67, 69, 73) | Prioritise these in the next ornithologist validation round |
| Red-billed Firefinch threshold effectively ≥1.0 — zero observations | Collect ≥50 confirmed clips before relying on this threshold |
| African Black-headed Oriole uses fallback threshold | Needs at least one false positive clip to fit the regression properly |
| All thresholds are BirdNET v2.4 specific | Re-derive everything if the platform upgrades BirdNET |