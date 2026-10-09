"""
bird_pipeline.py
----------------
Production pipeline for calibrating BirdNET confidence scores and labelling
predictions as confirmed observations.

Implements the method described in:
  Wood & Kahl (2024) — Guidelines for appropriate use of BirdNET scores.
  Journal of Ornithology.

Pipeline steps
--------------
1. Load validation clips and BirdNET predictions
2. Apply logit transform to confidence scores
3. Fit per-species logistic regression: pr(correct) = sigmoid(b0 + b1 * logit_score)
4. Derive the 99% precision threshold analytically per species
5. Evaluate model quality (AUC, Brier score, log-loss)
6. Label all predictions: observation = 1 if confidence >= threshold, else 0
7. Save outputs

Usage
-----
    python bird_pipeline.py

All outputs are written to outputs/bird/.

Dependencies
------------
    pip install pandas numpy scikit-learn scipy matplotlib
"""

import os
import sys
import logging
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss, log_loss

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE       = os.path.dirname(os.path.abspath(__file__))
DATA_BIRDS = os.path.join(BASE, 'Data Birds')
OUT_DIR    = os.path.join(BASE, 'outputs', 'bird')
os.makedirs(OUT_DIR, exist_ok=True)

VAL_PATH   = os.path.join(DATA_BIRDS, 'validation_results.csv')
PRED_PATH  = os.path.join(DATA_BIRDS, 'birdnet_predictions.csv')

# ── Constants ─────────────────────────────────────────────────────────────────
TARGET_PRECISION = 0.99    # pr(prediction is correct) >= this to label as observation
CLIP_EPS         = 1e-6    # clipping margin to avoid log(0) in logit transform
BIRDNET_VERSION  = 'v2.4'  # thresholds are version-specific; validate before applying


# ==============================================================================
# STEP 1 — LOAD DATA
# ==============================================================================

def load_data(val_path: str, pred_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load and minimally validate the validation clips and prediction tables.

    Validation file  : one row per ornithologist-reviewed clip
                       columns: scientificName, commonName, vBirdNET, filename,
                                confidence, outcome (1=correct, 0=incorrect)

    Predictions file : one row per BirdNET detection
                       columns: common_name, confidence, folder, begin_path, ...

    Returns
    -------
    val  : cleaned validation DataFrame
    pred : cleaned predictions DataFrame
    """
    log.info('Loading data...')
    val  = pd.read_csv(val_path)
    pred = pd.read_csv(pred_path)

    val.columns  = val.columns.str.strip()
    pred.columns = pred.columns.str.strip()

    # Enforce types
    val['outcome']     = val['outcome'].astype(int)
    val['confidence']  = pd.to_numeric(val['confidence'],  errors='coerce')
    pred['confidence'] = pd.to_numeric(pred['confidence'], errors='coerce')

    # Drop unresolvable rows
    val  = val.dropna(subset=['confidence', 'commonName']).drop_duplicates().reset_index(drop=True)
    pred = pred.dropna(subset=['confidence', 'common_name']).drop_duplicates().reset_index(drop=True)

    # Align species name column
    val = val.rename(columns={'commonName': 'common_name'})

    # Version guard
    versions = val['vBirdNET'].unique().tolist()
    if any(v != BIRDNET_VERSION for v in versions):
        log.warning(
            f'Validation contains BirdNET version(s) {versions}. '
            f'Expected {BIRDNET_VERSION}. '
            'Do not apply derived thresholds to predictions from a different version.'
        )

    log.info(f'  Validation  : {len(val):,} rows')
    log.info(f'  Predictions : {len(pred):,} rows')
    return val, pred


# ==============================================================================
# STEP 2 — LOGIT TRANSFORM
# ==============================================================================

def apply_logit_transform(
    val: pd.DataFrame,
    pred: pd.DataFrame,
    clip_eps: float = CLIP_EPS
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Add a logit_score column to both DataFrames.

    Why: BirdNET confidence scores are produced by a sigmoid function applied to an
    internal activation value. The sigmoid compresses the scale non-linearly, making
    the extreme ranges (near 0 and 1) difficult for a linear model to fit. The logit
    transform ( ln(p / (1-p)) ) is the inverse of the sigmoid and returns scores to
    a roughly linear scale where logistic regression works correctly.

    Wood & Kahl (2024) recommend this pre-processing step explicitly.
    """
    def safe_logit(c: np.ndarray) -> np.ndarray:
        c_clip = np.clip(c, clip_eps, 1 - clip_eps)
        return np.log(c_clip / (1 - c_clip))

    val  = val.copy()
    pred = pred.copy()
    val['logit_score']  = safe_logit(val['confidence'].values)
    pred['logit_score'] = safe_logit(pred['confidence'].values)

    log.info('Logit transform applied.')
    return val, pred


# ==============================================================================
# STEP 3 — FIT LOGISTIC REGRESSION PER SPECIES
# ==============================================================================

def fit_species_models(
    val: pd.DataFrame,
    target_p: float = TARGET_PRECISION,
    random_state: int = 42,
) -> dict:
    """
    For each species in the validation set, fit a logistic regression model:

        pr(correct) = sigmoid(b0 + b1 * logit_score)

    The model is fitted on the validated clips (ground truth). Each species gets
    its own model because BirdNET's accuracy at a given confidence score varies
    substantially by species.

    Fallback rule
    -------------
    If only one outcome class is present (e.g. all 150 clips were correct),
    logistic regression cannot be fitted. The threshold defaults to the minimum
    observed confidence score in the validation set. This situation is flagged
    with threshold_reliable = False.

    Parameters
    ----------
    val          : cleaned validation DataFrame with logit_score column
    target_p     : precision target (default 0.99)
    random_state : integer seed passed to LogisticRegression for reproducibility.
                   lbfgs is deterministic but other solvers (saga, liblinear) are
                   not; fixing the seed ensures identical results regardless of
                   solver choice. Default 42.

    Returns
    -------
    results : dict keyed by species name, each value is a dict:
        {
            'model'              : fitted LogisticRegression or None,
            'b0'                 : intercept (float or None),
            'b1'                 : logit slope (float or None),
            'threshold_p99'      : derived confidence threshold (float or None),
            'threshold_reliable' : bool,
            'n_validated'        : int,
            'n_tp'               : int,
            'n_fp'               : int,
            'note'               : str,
        }
    """
    log.info(f'Fitting logistic regression models (random_state={random_state})...')
    species_list = sorted(val['common_name'].unique())
    results = {}

    for sp in species_list:
        d       = val[val['common_name'] == sp]
        y       = d['outcome'].values
        X_logit = d['logit_score'].values
        X_raw   = d['confidence'].values
        n_tp    = int(y.sum())
        n_fp    = int((y == 0).sum())

        # ── Fallback: single outcome class ──────────────────────────────────
        if len(np.unique(y)) < 2:
            min_conf = float(X_raw.min())
            log.info(
                f'  {sp}: single class (all TP). '
                f'Fallback threshold = min confidence = {min_conf:.4f}'
            )
            results[sp] = {
                'model': None, 'b0': None, 'b1': None,
                'threshold_p99': min_conf, 'threshold_reliable': False,
                'n_validated': len(d), 'n_tp': n_tp, 'n_fp': n_fp,
                'note': 'Fallback: single outcome class in validation data'
            }
            continue

        # ── Fit logistic regression ──────────────────────────────────────────
        model = LogisticRegression(solver='lbfgs', max_iter=1000, random_state=random_state)
        model.fit(X_logit.reshape(-1, 1), y)

        b0 = float(model.intercept_[0])
        b1 = float(model.coef_[0][0])

        # ── Derive threshold analytically ────────────────────────────────────
        # Solve: target_p = sigmoid(b0 + b1 * logit_score)
        # => logit(target_p) = b0 + b1 * logit_score
        # => logit_score = (logit(target_p) - b0) / b1
        # => confidence_threshold = sigmoid(logit_score)
        if b1 == 0:
            threshold = None
            note = 'b1 = 0: flat curve, no discriminating signal'
        else:
            logit_target = np.log(target_p / (1 - target_p))
            logit_thresh = (logit_target - b0) / b1
            threshold    = float(expit(logit_thresh))
            note = ''

        log.info(
            f'  {sp}: b0={b0:.4f}  b1={b1:.4f}  '
            f'threshold={round(threshold, 4) if threshold is not None else "None"}'
        )

        results[sp] = {
            'model': model, 'b0': round(b0, 6), 'b1': round(b1, 6),
            'threshold_p99': round(threshold, 6) if threshold else None,
            'threshold_reliable': threshold is not None,
            'n_validated': len(d), 'n_tp': n_tp, 'n_fp': n_fp,
            'note': note
        }

    return results


# ==============================================================================
# STEP 4 — EVALUATE MODEL QUALITY
# ==============================================================================

def evaluate_models(
    val: pd.DataFrame,
    species_results: dict
) -> pd.DataFrame:
    """
    Compute AUC, Brier score, and log-loss for each species model.

    AUC       : discrimination — how well logit scores rank TPs above FPs
                (1.0 = perfect, 0.5 = random)
    Brier     : calibration quality — mean squared error of predicted
                probabilities (0 = perfect)
    Log-loss  : calibration quality — penalises confident wrong predictions
                more heavily than Brier (lower is better)

    Returns a DataFrame with one row per species.
    """
    log.info('Evaluating model quality...')
    rows = []

    for sp, res in species_results.items():
        d       = val[val['common_name'] == sp]
        y       = d['outcome'].values
        X_logit = d['logit_score'].values
        model   = res['model']

        if model is None:
            rows.append({
                'common_name': sp, 'threshold_p99': res['threshold_p99'],
                'threshold_reliable': False, 'AUC': None, 'Brier': None,
                'LogLoss': None, 'note': res['note']
            })
            continue

        probs = model.predict_proba(X_logit.reshape(-1, 1))[:, 1]

        try:    auc   = round(roc_auc_score(y, probs), 4)
        except: auc   = None
        try:    brier = round(brier_score_loss(y, probs), 4)
        except: brier = None
        try:    ll    = round(log_loss(y, probs), 4)
        except: ll    = None

        rows.append({
            'common_name'       : sp,
            'threshold_p99'     : res['threshold_p99'],
            'threshold_reliable': res['threshold_reliable'],
            'AUC'               : auc,
            'Brier'             : brier,
            'LogLoss'           : ll,
            'note'              : res['note']
        })

    return pd.DataFrame(rows)


# ==============================================================================
# STEP 5 — BUILD THRESHOLD TABLE
# ==============================================================================

def build_threshold_table(
    val: pd.DataFrame,
    species_results: dict,
    birdnet_version: str = BIRDNET_VERSION
) -> pd.DataFrame:
    """
    Produce the species_thresholds table — the operational artefact that the
    Tech Team loads into the production database.

    Schema
    ------
    common_name        : species name — must match BirdNET output exactly
    birdnet_version    : version string — thresholds are version-specific
    n_validated        : number of clips reviewed by the ornithologist
    n_true_positives   : number of clips judged correct
    method             : 'logistic_logit_score' or 'fallback_min_confidence'
    intercept_b0       : logistic regression intercept (None for fallback)
    coef_logit_b1      : logistic regression logit slope (None for fallback)
    threshold_p99      : confidence score threshold at pr(correct) = 0.99
    threshold_reliable : True = use threshold; False = flag for manual review
    """
    rows = []
    for sp, res in species_results.items():
        rows.append({
            'common_name'       : sp,
            'birdnet_version'   : val[val['common_name'] == sp]['vBirdNET'].iloc[0],
            'n_validated'       : res['n_validated'],
            'n_true_positives'  : res['n_tp'],
            'method'            : 'logistic_logit_score' if res['model']
                                  else 'fallback_min_confidence',
            'intercept_b0'      : res['b0'],
            'coef_logit_b1'     : res['b1'],
            'threshold_p99'     : res['threshold_p99'],
            'threshold_reliable': res['threshold_reliable'],
        })
    return pd.DataFrame(rows)


# ==============================================================================
# STEP 6 — LABEL PREDICTIONS
# ==============================================================================

def label_predictions(
    pred: pd.DataFrame,
    threshold_table: pd.DataFrame
) -> pd.DataFrame:
    """
    Apply species-specific thresholds to all predictions.

    Labelling rules
    ---------------
    observation = 1   : confidence >= threshold  (confirmed observation)
    observation = 0   : confidence <  threshold  (sub-threshold prediction)
    observation = NA  : threshold_reliable = False OR species not in table
                        (needs manual review by Biometrics Team)

    The rule is >= (not >) because a clip at exactly the threshold meets the
    99% precision bar and should be included.

    Edge cases
    ----------
    - Species not in threshold table     : observation = NA, alert Biometrics Team
    - threshold_reliable = False         : observation = NA, do not auto-label
    - threshold_p99 is None              : observation = NA
    - confidence exactly equals threshold: counts as observation (>= rule)
    """
    log.info('Labelling predictions...')

    lookup = {
        row['common_name']: (row['threshold_p99'], row['threshold_reliable'])
        for _, row in threshold_table.iterrows()
    }

    def _label(row):
        entry = lookup.get(row['common_name'])
        if entry is None:
            return pd.NA                              # unknown species
        thr, reliable = entry
        if not reliable or thr is None:
            return pd.NA                              # fallback — do not auto-label
        return int(row['confidence'] >= thr)

    pred = pred.copy()
    pred['observation'] = pred.apply(_label, axis=1)
    return pred


# ==============================================================================
# STEP 7 — SUMMARISE AND SAVE OUTPUTS
# ==============================================================================

def summarise_labels(
    pred: pd.DataFrame,
    threshold_table: pd.DataFrame
) -> pd.DataFrame:
    """Produce a per-species observation summary table."""
    lookup = {
        row['common_name']: row['threshold_p99']
        for _, row in threshold_table.iterrows()
    }
    rows = []
    for sp in sorted(pred['common_name'].unique()):
        sp_df  = pred[pred['common_name'] == sp]
        n_pred = len(sp_df)
        n_obs  = (sp_df['observation'] == 1).sum()
        n_sub  = (sp_df['observation'] == 0).sum()
        n_null = sp_df['observation'].isna().sum()
        thr    = lookup.get(sp)
        rows.append({
            'common_name'     : sp,
            'threshold_p99'   : round(thr, 4) if thr else None,
            'n_predictions'   : n_pred,
            'n_observations'  : int(n_obs),
            'n_sub_threshold' : int(n_sub),
            'n_needs_review'  : int(n_null),
            'pct_observations': round(100 * n_obs / n_pred, 1) if n_pred > 0 else 0,
        })
    return pd.DataFrame(rows)


def save_outputs(
    pred: pd.DataFrame,
    threshold_table: pd.DataFrame,
    eval_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    out_dir: str
) -> None:
    """Write all pipeline outputs to disk."""
    # Labelled predictions
    path = os.path.join(out_dir, 'birdnet_predictions_labelled.csv')
    pred.to_csv(path, index=False)
    log.info(f'Saved: {path}  ({len(pred):,} rows)')

    # Threshold table
    path = os.path.join(out_dir, 'species_thresholds.csv')
    threshold_table.to_csv(path, index=False)
    log.info(f'Saved: {path}')

    # Model evaluation
    path = os.path.join(out_dir, 'model_evaluation.csv')
    eval_df.to_csv(path, index=False)
    log.info(f'Saved: {path}')

    # Observation summary
    path = os.path.join(out_dir, 'observation_summary.csv')
    summary_df.to_csv(path, index=False)
    log.info(f'Saved: {path}')

    # Site-level observation summary
    obs_only = pred[pred['observation'] == 1]
    if len(obs_only):
        site_summary = (
            obs_only
            .groupby(['folder', 'common_name'])
            .size()
            .reset_index(name='n_observations')
            .pivot(index='folder', columns='common_name', values='n_observations')
            .fillna(0).astype(int)
        )
        path = os.path.join(out_dir, 'site_observation_summary.csv')
        site_summary.to_csv(path)
        log.info(f'Saved: {path}  ({len(site_summary)} sites)')


# ==============================================================================
# MAIN
# ==============================================================================

def run_pipeline(
    val_path:     str   = VAL_PATH,
    pred_path:    str   = PRED_PATH,
    out_dir:      str   = OUT_DIR,
    target_p:     float = TARGET_PRECISION,
    random_state: int   = 42,
) -> dict:
    """
    Run the full BirdNET calibration and labelling pipeline.

    Parameters
    ----------
    val_path     : path to validation_results.csv
    pred_path    : path to birdnet_predictions.csv
    out_dir      : directory for output files
    target_p     : precision target for threshold derivation (default 0.99)
    random_state : integer seed for reproducibility (default 42).
                   Controls the LogisticRegression solver. Fix this value to
                   guarantee identical thresholds across runs and environments.

    Returns
    -------
    dict with keys: threshold_table, eval_df, summary_df, pred (labelled)
    """
    log.info('=' * 60)
    log.info('BirdNET Calibration Pipeline')
    log.info(f'Target precision : {target_p:.0%}')
    log.info(f'Random state     : {random_state}')
    log.info(f'Output directory : {out_dir}')
    log.info('=' * 60)

    # Step 1: Load
    val, pred = load_data(val_path, pred_path)

    # Step 2: Logit transform
    val, pred = apply_logit_transform(val, pred)

    # Step 3: Fit models
    species_results = fit_species_models(val, target_p=target_p, random_state=random_state)

    # Step 4: Evaluate
    eval_df = evaluate_models(val, species_results)

    # Step 5: Build threshold table
    threshold_table = build_threshold_table(val, species_results)

    # Step 6: Label predictions
    pred = label_predictions(pred, threshold_table)

    # Step 7: Summarise and save
    summary_df = summarise_labels(pred, threshold_table)
    save_outputs(pred, threshold_table, eval_df, summary_df, out_dir)

    # Console summary
    log.info('')
    log.info('RESULTS SUMMARY')
    log.info('-' * 60)
    for _, row in summary_df.iterrows():
        log.info(
            f"  {row['common_name']:<35} "
            f"threshold={row['threshold_p99']}  "
            f"observations={row['n_observations']:,} / {row['n_predictions']:,} "
            f"({row['pct_observations']}%)"
        )
    totals = summary_df[['n_predictions','n_observations','n_sub_threshold','n_needs_review']].sum()
    log.info('')
    log.info(f"  Total predictions  : {totals['n_predictions']:,}")
    log.info(f"  Observations       : {totals['n_observations']:,}  ({100*totals['n_observations']/totals['n_predictions']:.1f}%)")
    log.info(f"  Sub-threshold      : {totals['n_sub_threshold']:,}")
    log.info(f"  Needs review       : {totals['n_needs_review']:,}")
    log.info('=' * 60)
    log.info('Pipeline complete.')

    return {
        'threshold_table': threshold_table,
        'eval_df'        : eval_df,
        'summary_df'     : summary_df,
        'pred'           : pred,
    }


if __name__ == '__main__':
    run_pipeline()
