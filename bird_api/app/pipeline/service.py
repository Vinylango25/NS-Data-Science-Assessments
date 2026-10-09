"""
app/pipeline/service.py
-----------------------
Wraps bird_pipeline.run_pipeline() and persists results to the API database.

This is the function called by POST /api/v1/birdnet/calibrate.
It does not reimplement the calibration logic — it delegates entirely
to bird_pipeline.py and then writes the outputs to the API DB.
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.core.config import settings
from app.db.database import SessionLocal, init_db
from app.db.models import CalibrationRun, SpeciesThreshold, ModelEvaluation, LabelledPrediction
from app.pipeline.loader import load_data

# bird_pipeline.py lives one directory up from bird_api/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from bird_pipeline import run_pipeline as _run_calibration  # noqa: E402

log = logging.getLogger(__name__)


def run_calibration(
    data_source:      str   = None,
    val_path:         str   = None,
    pred_path:        str   = None,
    target_precision: float = None,
    random_state:     int   = None,
    birdnet_version:  str   = None,
) -> dict:
    """
    Full calibration job:
      1. Load data (CSV or PostgreSQL)
      2. Run bird_pipeline.run_pipeline()
      3. Persist thresholds, evaluations, and labelled predictions to API DB
      4. Return summary dict

    Parameters
    ----------
    data_source      : "csv" | "postgres" (default: settings.DATA_SOURCE)
    val_path         : CSV file path or DB table name for validation clips
    pred_path        : CSV file path or DB table name for BirdNET predictions
    target_precision : Precision target (default: settings.TARGET_PRECISION)
    random_state     : Reproducibility seed (default: settings.RANDOM_STATE)
    birdnet_version  : BirdNET version string (default: settings.BIRDNET_VERSION)
    """
    source   = data_source      or settings.DATA_SOURCE
    target_p = target_precision or settings.TARGET_PRECISION
    seed     = random_state     or settings.RANDOM_STATE
    version  = birdnet_version  or settings.BIRDNET_VERSION

    v_path = val_path  or settings.VAL_PATH
    p_path = pred_path or settings.PRED_PATH

    log.info("=" * 60)
    log.info("BirdNET Calibration Service")
    log.info(f"  Data source      : {source}")
    log.info(f"  Target precision : {target_p:.0%}")
    log.info(f"  Random state     : {seed}")
    log.info(f"  BirdNET version  : {version}")
    log.info("=" * 60)

    init_db()
    db = SessionLocal()

    run_record = CalibrationRun(
        run_at          = datetime.utcnow(),
        birdnet_version = version,
        data_source     = source,
        val_path        = str(v_path),
        pred_path       = str(p_path),
        target_precision= target_p,
        random_state    = seed,
        status          = "running",
    )
    db.add(run_record)
    db.commit()
    db.refresh(run_record)
    run_id = run_record.id

    try:
        # ── Step 1: Run the calibration pipeline ──────────────────────────────
        # bird_pipeline.run_pipeline reads its own CSVs — we pass the paths
        import os
        os.makedirs(settings.OUT_DIR, exist_ok=True)

        results = _run_calibration(
            val_path     = str(v_path),
            pred_path    = str(p_path),
            out_dir      = str(settings.OUT_DIR),
            target_p     = target_p,
            random_state = seed,
        )

        threshold_table: pd.DataFrame = results["threshold_table"]
        eval_df:         pd.DataFrame = results["eval_df"]
        pred:            pd.DataFrame = results["pred"]        # labelled

        # ── Step 2: Persist species thresholds ────────────────────────────────
        for _, row in threshold_table.iterrows():
            db.add(SpeciesThreshold(
                run_id             = run_id,
                common_name        = row["common_name"],
                birdnet_version    = row.get("birdnet_version", version),
                threshold_p99      = float(row["threshold_p99"]) if row.get("threshold_p99") else None,
                threshold_reliable = bool(row["threshold_reliable"]),
                intercept_b0       = float(row["intercept_b0"])   if row.get("intercept_b0")   else None,
                coef_logit_b1      = float(row["coef_logit_b1"])  if row.get("coef_logit_b1")  else None,
                n_validated        = int(row["n_validated"])       if row.get("n_validated")    else None,
                n_true_positives   = int(row["n_true_positives"])  if row.get("n_true_positives") else None,
                method             = str(row.get("method", "")),
                target_precision   = target_p,
                random_state       = seed,
            ))

        # ── Step 3: Persist model evaluations ─────────────────────────────────
        for _, row in eval_df.iterrows():
            db.add(ModelEvaluation(
                run_id             = run_id,
                common_name        = row["common_name"],
                birdnet_version    = version,
                threshold_p99      = float(row["threshold_p99"]) if row.get("threshold_p99") else None,
                threshold_reliable = bool(row["threshold_reliable"]) if row.get("threshold_reliable") is not None else None,
                auc                = float(row["AUC"])     if row.get("AUC")     else None,
                brier_score        = float(row["Brier"])   if row.get("Brier")   else None,
                log_loss           = float(row["LogLoss"]) if row.get("LogLoss") else None,
                note               = str(row.get("note", "")),
            ))

        # ── Step 4: Persist labelled predictions ──────────────────────────────
        pred_rows = []
        for _, row in pred.iterrows():
            obs = row.get("observation")
            pred_rows.append(LabelledPrediction(
                run_id          = run_id,
                common_name     = str(row.get("common_name", "")),
                confidence      = float(row["confidence"]),
                folder          = str(row.get("folder", "")),
                begin_path      = str(row.get("begin_path", "")),
                birdnet_version = version,
                threshold_p99   = float(row["threshold_p99"]) if row.get("threshold_p99") else None,
                observation     = int(obs) if obs is not None and str(obs) not in ("nan", "<NA>", "None") else None,
            ))
        db.bulk_save_objects(pred_rows)

        # ── Step 5: Update run record ─────────────────────────────────────────
        n_obs = int((pred["observation"] == 1).sum())
        run_record.n_species      = len(threshold_table)
        run_record.n_predictions  = len(pred)
        run_record.n_observations = n_obs
        run_record.status         = "complete"
        db.commit()

        log.info(f"Calibration complete. Run ID: {run_id}")
        log.info(f"  Species          : {len(threshold_table)}")
        log.info(f"  Predictions      : {len(pred):,}")
        log.info(f"  Observations     : {n_obs:,}")

        return {
            "run_id":            run_id,
            "status":            "complete",
            "n_species":         len(threshold_table),
            "n_predictions":     len(pred),
            "n_observations":    n_obs,
            "completed_at":      datetime.utcnow().isoformat() + "Z",
        }

    except Exception as exc:
        db.rollback()
        run_record.status    = "error"
        run_record.error_msg = str(exc)
        db.commit()
        log.error(f"Calibration failed: {exc}", exc_info=True)
        raise

    finally:
        db.close()
