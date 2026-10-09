"""
app/api/routes/birdnet.py
-------------------------
BirdNET Calibration API routes.

Endpoints:
  GET  /api/v1/birdnet/thresholds          — current species thresholds
  GET  /api/v1/birdnet/predictions          — labelled predictions (paginated, filtered)
  POST /api/v1/birdnet/calibrate            — trigger a calibration run
  GET  /api/v1/birdnet/calibrate/{run_id}  — check run status / results
  GET  /api/v1/birdnet/model-quality        — per-species AUC, Brier, LogLoss
"""
import logging
from typing import Optional, Literal
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.database import get_db
from app.db.models import SpeciesThreshold, LabelledPrediction, ModelEvaluation, CalibrationRun

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/birdnet", tags=["BirdNET"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ThresholdOut(BaseModel):
    id:                 int
    common_name:        str
    birdnet_version:    str
    threshold_p99:      Optional[float]
    threshold_reliable: bool
    method:             Optional[str]
    intercept_b0:       Optional[float]
    coef_logit_b1:      Optional[float]
    n_validated:        Optional[int]
    n_true_positives:   Optional[int]
    target_precision:   Optional[float]
    random_state:       Optional[int]
    derived_at:         Optional[datetime]

    class Config:
        from_attributes = True


class PredictionOut(BaseModel):
    id:             int
    common_name:    str
    confidence:     float
    folder:         Optional[str]
    begin_path:     Optional[str]
    birdnet_version:Optional[str]
    threshold_p99:  Optional[float]
    observation:    Optional[int]   # 1 | 0 | None
    labelled_at:    Optional[datetime]

    class Config:
        from_attributes = True


class PredictionsPage(BaseModel):
    total:   int
    page:    int
    page_size: int
    results: list[PredictionOut]


class ModelQualityOut(BaseModel):
    common_name:        str
    birdnet_version:    str
    threshold_p99:      Optional[float]
    threshold_reliable: Optional[bool]
    auc:                Optional[float]
    brier_score:        Optional[float]
    log_loss:           Optional[float]
    note:               Optional[str]
    evaluated_at:       Optional[datetime]

    class Config:
        from_attributes = True


class CalibrateRequest(BaseModel):
    data_source:      Literal["csv", "postgres"] = Field(
        default="csv",
        description="'csv' reads from file paths; 'postgres' reads from SOURCE_DB_URL tables"
    )
    val_path:         Optional[str] = Field(
        default=None,
        description="CSV file path OR PostgreSQL table name for validation clips. "
                    "Defaults to settings.VAL_PATH / settings.VALIDATION_TABLE."
    )
    pred_path:        Optional[str] = Field(
        default=None,
        description="CSV file path OR PostgreSQL table name for BirdNET predictions. "
                    "Defaults to settings.PRED_PATH / settings.PREDICTIONS_TABLE."
    )
    target_precision: float = Field(default=0.99, ge=0.5, le=1.0)
    random_state:     int   = Field(default=42, description="Reproducibility seed — store this")
    birdnet_version:  str   = Field(default="v2.4")


class CalibrateRunOut(BaseModel):
    run_id:           int
    status:           str
    birdnet_version:  str
    data_source:      str
    target_precision: float
    random_state:     int
    n_species:        Optional[int]
    n_predictions:    Optional[int]
    n_observations:   Optional[int]
    run_at:           Optional[datetime]
    error_msg:        Optional[str]

    class Config:
        from_attributes = True


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/thresholds", response_model=list[ThresholdOut],
            summary="Get current species thresholds")
def get_thresholds(
    species: Optional[str] = Query(default=None, description="Filter by common_name"),
    reliable_only: bool    = Query(default=False, description="Return only threshold_reliable=True"),
    db: Session = Depends(get_db),
):
    """
    Returns the most recent threshold for each species.

    If multiple runs have been executed, returns the latest threshold per
    (common_name, birdnet_version) pair.
    """
    # Latest threshold per species: subquery on max id per species/version
    from sqlalchemy import func
    subq = (
        db.query(
            SpeciesThreshold.common_name,
            SpeciesThreshold.birdnet_version,
            func.max(SpeciesThreshold.id).label("max_id"),
        )
        .group_by(SpeciesThreshold.common_name, SpeciesThreshold.birdnet_version)
        .subquery()
    )

    q = db.query(SpeciesThreshold).join(
        subq,
        (SpeciesThreshold.id == subq.c.max_id)
    )

    if species:
        q = q.filter(SpeciesThreshold.common_name.ilike(f"%{species}%"))
    if reliable_only:
        q = q.filter(SpeciesThreshold.threshold_reliable == True)

    return q.order_by(SpeciesThreshold.common_name).all()


@router.get("/predictions", response_model=PredictionsPage,
            summary="Get labelled BirdNET predictions")
def get_predictions(
    species:     Optional[str] = Query(default=None),
    site:        Optional[str] = Query(default=None, description="Filter by folder/site code"),
    observation: Optional[int] = Query(default=None, description="Filter: 1=confirmed, 0=sub-threshold"),
    page:        int           = Query(default=1, ge=1),
    page_size:   int           = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    Returns labelled predictions with optional filters.

    observation=1  → confirmed observations (confidence >= threshold)
    observation=0  → sub-threshold predictions
    observation    → NULL means needs manual review (threshold not reliable)
    """
    q = db.query(LabelledPrediction)

    if species:
        q = q.filter(LabelledPrediction.common_name.ilike(f"%{species}%"))
    if site:
        q = q.filter(LabelledPrediction.folder.ilike(f"%{site}%"))
    if observation is not None:
        q = q.filter(LabelledPrediction.observation == observation)

    total   = q.count()
    results = q.offset((page - 1) * page_size).limit(page_size).all()

    return PredictionsPage(
        total     = total,
        page      = page,
        page_size = page_size,
        results   = results,
    )


@router.post("/calibrate", status_code=202,
             summary="Trigger a calibration run")
def trigger_calibration(
    req: CalibrateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Starts a calibration run in the background.

    **data_source options:**
    - `csv` — reads from local CSV files (val_path / pred_path as file paths)
    - `postgres` — reads from SOURCE_DB_URL database (val_path / pred_path as table names)

    Returns a run_id immediately. Poll `GET /calibrate/{run_id}` for status.
    """
    from app.pipeline.service import run_calibration

    # Create a placeholder run record to get a run_id immediately
    run = CalibrationRun(
        run_at           = datetime.utcnow(),
        birdnet_version  = req.birdnet_version,
        data_source      = req.data_source,
        val_path         = req.val_path,
        pred_path        = req.pred_path,
        target_precision = req.target_precision,
        random_state     = req.random_state,
        status           = "queued",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Run calibration in the background
    background_tasks.add_task(
        run_calibration,
        data_source      = req.data_source,
        val_path         = req.val_path,
        pred_path        = req.pred_path,
        target_precision = req.target_precision,
        random_state     = req.random_state,
        birdnet_version  = req.birdnet_version,
    )

    return {
        "run_id": run.id,
        "status": "queued",
        "message": f"Calibration queued. Poll GET /api/v1/birdnet/calibrate/{run.id} for status.",
    }


@router.get("/calibrate/{run_id}", response_model=CalibrateRunOut,
            summary="Get calibration run status and results")
def get_calibration_run(run_id: int, db: Session = Depends(get_db)):
    """
    Returns the status and summary of a calibration run.

    status values: queued | running | complete | error
    """
    run = db.query(CalibrationRun).filter(CalibrationRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


@router.get("/model-quality", response_model=list[ModelQualityOut],
            summary="Get per-species model evaluation metrics")
def get_model_quality(
    species: Optional[str] = Query(default=None),
    run_id:  Optional[int] = Query(default=None, description="Specific run. Defaults to latest."),
    db: Session = Depends(get_db),
):
    """
    Returns AUC, Brier score, and log-loss for each species from the
    most recent calibration run (or a specific run_id).
    """
    if run_id is None:
        latest = db.query(ModelEvaluation).order_by(desc(ModelEvaluation.id)).first()
        if not latest:
            return []
        run_id = latest.run_id

    q = db.query(ModelEvaluation).filter(ModelEvaluation.run_id == run_id)

    if species:
        q = q.filter(ModelEvaluation.common_name.ilike(f"%{species}%"))

    return q.order_by(ModelEvaluation.common_name).all()



class ValidationNotifyRequest(BaseModel):
    data_source:     str   = Field(default="csv")
    val_path:        Optional[str] = None
    pred_path:       Optional[str] = None
    min_new_clips:   int   = Field(
        default=10,
        description="Minimum number of new validated clips for a species to trigger recalibration"
    )
    birdnet_version: str   = Field(default="v2.4")
    random_state:    int   = Field(default=42)


class ValidationNotifyOut(BaseModel):
    recalibration_triggered: bool
    run_id:                  Optional[int]
    species_updated:         list[str]
    species_checked:         int
    message:                 str


@router.post(
    "/validation/notify",
    response_model=ValidationNotifyOut,
    summary="Notify when validation set is updated — triggers recalibration if needed",
)
def validation_notify(
    req: ValidationNotifyRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Call this endpoint whenever the ornithologist adds new validated clips
    to the validation table.

    The service compares the current validation set against what was used in
    the last calibration run. If any species now has `min_new_clips` or more
    new validated clips since the last run, a new calibration is triggered
    automatically.

    Returns which species triggered the update and why.
    This closes the feedback loop — thresholds stay current without anyone
    needing to manually remember to re-run calibration.

    **Trigger points on the NS Analytics platform:**
    - After an ornithologist submits a batch of validated clips via the platform UI
    - On a nightly schedule as a safety net

    **What happens if recalibration is triggered:**
    - A new CalibrationRun is created (status = queued)
    - The full pipeline runs in the background
    - New SpeciesThreshold rows are inserted (old rows preserved for audit)
    - All LabelledPrediction rows are re-written with updated observation labels
    - Poll GET /calibrate/{run_id} for completion
    """
    from app.pipeline.loader import load_data
    from app.pipeline.service import run_calibration
    from sqlalchemy import func

    # ── 1. Load current validation data to count clips per species ────────────
    try:
        val, _ = load_data(
            data_source = req.data_source,
            val_path    = req.val_path,
            pred_path   = req.pred_path,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load validation data: {exc}")

    current_counts = val.groupby("common_name").size().to_dict()

    # ── 2. Get counts from last calibration run ───────────────────────────────
    last_run = db.query(SpeciesThreshold).order_by(desc(SpeciesThreshold.id)).first()
    last_run_id = last_run.run_id if last_run else None

    prev_counts = {}
    if last_run_id:
        rows = db.query(
            SpeciesThreshold.common_name,
            SpeciesThreshold.n_validated,
        ).filter(SpeciesThreshold.run_id == last_run_id).all()
        prev_counts = {r.common_name: (r.n_validated or 0) for r in rows}

    # ── 3. Find species with enough new clips to warrant recalibration ────────
    species_updated = []
    for sp, current_n in current_counts.items():
        prev_n = prev_counts.get(sp, 0)
        new_clips = current_n - prev_n
        if new_clips >= req.min_new_clips:
            species_updated.append(sp)

    # ── 4. Trigger recalibration if needed ────────────────────────────────────
    if not species_updated:
        return ValidationNotifyOut(
            recalibration_triggered = False,
            run_id                  = None,
            species_updated         = [],
            species_checked         = len(current_counts),
            message                 = (
                f"Checked {len(current_counts)} species. "
                f"No species gained {req.min_new_clips}+ new clips since last run. "
                "No recalibration needed."
            ),
        )

    # Create queued run record
    from app.db.models import CalibrationRun
    run = CalibrationRun(
        run_at           = datetime.utcnow(),
        birdnet_version  = req.birdnet_version,
        data_source      = req.data_source,
        val_path         = str(req.val_path or ""),
        pred_path        = str(req.pred_path or ""),
        target_precision = 0.99,
        random_state     = req.random_state,
        status           = "queued",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    new_run_id = run.id

    background_tasks.add_task(
        run_calibration,
        data_source      = req.data_source,
        val_path         = req.val_path,
        pred_path        = req.pred_path,
        target_precision = 0.99,
        random_state     = req.random_state,
        birdnet_version  = req.birdnet_version,
    )

    sp_list = ", ".join(species_updated)
    return ValidationNotifyOut(
        recalibration_triggered = True,
        run_id                  = new_run_id,
        species_updated         = species_updated,
        species_checked         = len(current_counts),
        message                 = (
            f"Recalibration triggered for {len(species_updated)} species "
            f"with {req.min_new_clips}+ new clips: {sp_list}. "
            f"Poll GET /api/v1/birdnet/calibrate/{new_run_id} for status."
        ),
    )
