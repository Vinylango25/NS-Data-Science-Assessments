"""
app/api/routes/vegetation.py
-----------------------------
Vegetation QA/QC API routes.

Endpoints:
  GET  /api/v1/veg/runs                    — list QC runs
  POST /api/v1/veg/runs                    — trigger a new QC run
  GET  /api/v1/veg/runs/{run_id}           — run status + summary
  GET  /api/v1/veg/surveys                 — list surveys (latest run)
  GET  /api/v1/veg/surveys/{survey_key}    — survey detail + flags
  GET  /api/v1/veg/plots                   — list plots (latest run)
  GET  /api/v1/veg/plots/{plot_name}       — plot detail
  GET  /api/v1/veg/flags                   — all QC flags (filterable)
  GET  /api/v1/veg/species-queue           — pending species list
  GET  /api/v1/veg/narrative/{survey_key}  — AI narrative for a survey
  POST /api/v1/veg/narrative/{survey_key}  — (re-)generate AI narrative
  GET  /api/v1/veg/dashboard               — dashboard summary stats
"""
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.db.database import get_db, init_db, SessionLocal
from app.db.models import QCRun, Survey, Plot, QCFlag, PendingSpecies, Narrative
from app.core.config import settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/veg", tags=["Vegetation QA/QC"])


# ── Pydantic response schemas ─────────────────────────────────────────────────

class RunSummary(BaseModel):
    id:               int
    run_at:           Optional[datetime]
    data_source:      Optional[str]
    status:           str
    n_surveys:        Optional[int]
    n_plots:          Optional[int]
    n_quadrats:       Optional[int]
    n_flags_high:     Optional[int]
    n_flags_medium:   Optional[int]
    n_flags_low:      Optional[int]
    n_pending_species: Optional[int]
    completed_at:     Optional[datetime]
    error_msg:        Optional[str]
    scorecard_params: Optional[dict]

    class Config:
        from_attributes = True


class SurveyOut(BaseModel):
    id:                  int
    run_id:              Optional[int]
    odk_key:             str
    plot_name:           Optional[str]
    submission_date:     Optional[str]
    submitter:           Optional[str]
    recorder:            Optional[str]
    duration_min:        Optional[float]
    review_state:        Optional[str]
    quadrats_completed:  Optional[int]
    quadrats_with_herbs: Optional[int]
    species_occurrences: Optional[int]
    additional_species:  Optional[int]
    n_flags:             Optional[int]
    qc_status:           Optional[str]
    stratum_label:       Optional[str]
    area_label:          Optional[str]

    class Config:
        from_attributes = True


class PlotOut(BaseModel):
    id:                       int
    run_id:                   Optional[int]
    plot_uuid:                Optional[str]
    plot_name:                str
    stratum_label:            Optional[str]
    area_label:               Optional[str]
    is_viable:                Optional[bool]
    centroid_lat:             Optional[float]
    centroid_lon:             Optional[float]
    geohash:                  Optional[str]
    transect_length_m:        Optional[float]
    midpoint_displacement_m:  Optional[float]
    ep_a_lat:                 Optional[float]
    ep_a_lon:                 Optional[float]
    ep_b_lat:                 Optional[float]
    ep_b_lon:                 Optional[float]
    mid_lat:                  Optional[float]
    mid_lon:                  Optional[float]
    was_surveyed:             Optional[bool]
    approved_survey_count:    Optional[int]
    total_species_occurrences: Optional[int]
    quadrats_with_herbs:      Optional[int]
    total_quadrats:           Optional[int]
    n_flags:                  Optional[int]
    qc_status:                Optional[str]

    class Config:
        from_attributes = True


class FlagOut(BaseModel):
    id:              int
    run_id:          Optional[int]
    flag_id:         str
    flag_type:       str
    severity:        str
    survey_key:      Optional[str]
    plot_name:       Optional[str]
    quadrat_number:  Optional[int]
    field_value:     Optional[str]
    expected_value:  Optional[str]
    description:     Optional[str]
    created_at:      Optional[datetime]

    class Config:
        from_attributes = True


class FlagsPage(BaseModel):
    total:    int
    page:     int
    page_size: int
    results:  list[FlagOut]


class PendingSpeciesOut(BaseModel):
    id:                int
    run_id:            Optional[int]
    survey_key:        Optional[str]
    plot_name:         Optional[str]
    recorder:          Optional[str]
    submission_date:   Optional[str]
    provisional_name:  Optional[str]
    validated_name:    Optional[str]
    review_status:     Optional[str]
    new_record_reason: Optional[str]
    species_entry_mode: Optional[str]

    class Config:
        from_attributes = True


class NarrativeOut(BaseModel):
    survey_key:   Optional[str]
    plot_name:    Optional[str]
    narrative:    Optional[str]
    model:        Optional[str]
    generated_at: Optional[datetime]

    class Config:
        from_attributes = True


class DashboardStats(BaseModel):
    run_id:            Optional[int]
    run_at:            Optional[datetime]
    status:            Optional[str]
    n_plots_registered: int
    n_plots_surveyed:  int
    n_plots_viable:    int
    n_surveys_total:   int
    n_surveys_approved: int
    n_surveys_rejected: int
    n_quadrats:        int
    pct_quadrats_with_herbs: Optional[float]
    n_flags_high:      int
    n_flags_medium:    int
    n_flags_low:       int
    n_pending_species: int
    flag_type_summary: list[dict]


class RunRequest(BaseModel):
    data_source: str = Field(
        default="csv",
        description='"csv" = read from configured CSV paths; "postgres" = read from SOURCE_DB_URL'
    )


# ── Helper: get latest completed run_id ───────────────────────────────────────

def _latest_run_id(db: Session) -> Optional[int]:
    run = db.query(QCRun).filter(QCRun.status == "complete").order_by(desc(QCRun.id)).first()
    return run.id if run else None


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/dashboard", response_model=DashboardStats,
            summary="Dashboard summary statistics")
def get_dashboard(db: Session = Depends(get_db)):
    """
    Returns the key stats for the main dashboard card view.
    Reads from the latest completed QC run.
    """
    run_id = _latest_run_id(db)

    # Plots
    n_plots_registered = db.query(Plot).filter(Plot.run_id == run_id).count() if run_id else 0
    n_plots_viable     = db.query(Plot).filter(Plot.run_id == run_id, Plot.is_viable == True).count() if run_id else 0
    n_plots_surveyed   = db.query(Plot).filter(Plot.run_id == run_id, Plot.was_surveyed == True).count() if run_id else 0

    # Surveys
    n_surveys_total    = db.query(Survey).filter(Survey.run_id == run_id).count() if run_id else 0
    n_surveys_approved = db.query(Survey).filter(
        Survey.run_id == run_id,
        Survey.review_state != "rejected"
    ).count() if run_id else 0
    n_surveys_rejected = n_surveys_total - n_surveys_approved

    # Quadrats / herb presence
    n_quadrats = 0
    pct_herbs  = None
    if run_id:
        approved_plots = db.query(Survey.quadrats_completed).filter(
            Survey.run_id == run_id,
            Survey.review_state != "rejected"
        ).all()
        n_quadrats = sum(r[0] or 0 for r in approved_plots)
        herbs_counts = db.query(Survey.quadrats_with_herbs).filter(
            Survey.run_id == run_id,
            Survey.review_state != "rejected"
        ).all()
        n_herbs = sum(r[0] or 0 for r in herbs_counts)
        pct_herbs = round(100 * n_herbs / n_quadrats, 1) if n_quadrats else None

    # Flags
    n_high   = db.query(QCFlag).filter(QCFlag.run_id == run_id, QCFlag.severity == "HIGH").count()   if run_id else 0
    n_medium = db.query(QCFlag).filter(QCFlag.run_id == run_id, QCFlag.severity == "MEDIUM").count() if run_id else 0
    n_low    = db.query(QCFlag).filter(QCFlag.run_id == run_id, QCFlag.severity == "LOW").count()    if run_id else 0

    # Pending species
    n_pending = db.query(PendingSpecies).filter(PendingSpecies.run_id == run_id).count() if run_id else 0

    # Flag type breakdown
    flag_summary = []
    if run_id:
        rows = (
            db.query(QCFlag.flag_type, QCFlag.severity, func.count(QCFlag.id).label("n"))
            .filter(QCFlag.run_id == run_id)
            .group_by(QCFlag.flag_type, QCFlag.severity)
            .order_by(desc("n"))
            .all()
        )
        flag_summary = [{"flag_type": r[0], "severity": r[1], "n": r[2]} for r in rows]

    # Run info
    run_at = run_status = None
    if run_id:
        run = db.query(QCRun).filter(QCRun.id == run_id).first()
        if run:
            run_at     = run.run_at
            run_status = run.status

    return DashboardStats(
        run_id=run_id,
        run_at=run_at,
        status=run_status,
        n_plots_registered=n_plots_registered,
        n_plots_viable=n_plots_viable,
        n_plots_surveyed=n_plots_surveyed,
        n_surveys_total=n_surveys_total,
        n_surveys_approved=n_surveys_approved,
        n_surveys_rejected=n_surveys_rejected,
        n_quadrats=n_quadrats,
        pct_quadrats_with_herbs=pct_herbs,
        n_flags_high=n_high,
        n_flags_medium=n_medium,
        n_flags_low=n_low,
        n_pending_species=n_pending,
        flag_type_summary=flag_summary,
    )


@router.get("/runs", response_model=list[RunSummary], summary="List QC runs")
def list_runs(db: Session = Depends(get_db)):
    return db.query(QCRun).order_by(desc(QCRun.id)).limit(20).all()


@router.post("/runs", status_code=202, summary="Trigger a new QC run")
def trigger_run(
    req: RunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Starts a new QC pipeline run in the background.
    Returns a run_id immediately. Poll GET /runs/{run_id} for status.
    """
    from app.pipeline.loader import load_data
    from app.pipeline.qc_service import run_qc_pipeline
    from app.narrative.groq_narrative import generate_all_narratives

    # Create run record
    run = QCRun(
        run_at=datetime.utcnow(),
        data_source=req.data_source,
        status="queued",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id

    def _background_job():
        try:
            log.info(f"Starting QC run {run_id} (source={req.data_source})")
            # Mark running
            _db = SessionLocal()
            rec = _db.query(QCRun).filter(QCRun.id == run_id).first()
            if rec:
                rec.status = "running"
                _db.commit()
            _db.close()

            # Load + run pipeline
            data = load_data()
            run_qc_pipeline(data, run_id)

            # Generate AI narratives
            if settings.NARRATIVE_ENABLED:
                generate_all_narratives(run_id)

        except Exception as exc:
            log.error(f"Run {run_id} failed: {exc}", exc_info=True)
            _db = SessionLocal()
            rec = _db.query(QCRun).filter(QCRun.id == run_id).first()
            if rec:
                rec.status    = "error"
                rec.error_msg = str(exc)
                _db.commit()
            _db.close()

    background_tasks.add_task(_background_job)

    return {
        "run_id":  run_id,
        "status":  "queued",
        "message": f"QC run queued. Poll GET /api/v1/veg/runs/{run_id} for status.",
    }


@router.get("/runs/{run_id}", response_model=RunSummary,
            summary="Get QC run status and summary")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(QCRun).filter(QCRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


@router.get("/surveys", response_model=list[SurveyOut], summary="List surveys")
def list_surveys(
    run_id:      Optional[int] = Query(default=None, description="Defaults to latest run"),
    qc_status:   Optional[str] = Query(default=None, description="pass | warning | fail"),
    recorder:    Optional[str] = Query(default=None),
    review_state: Optional[str] = Query(default=None, description="approved | rejected"),
    db: Session = Depends(get_db),
):
    rid = run_id or _latest_run_id(db)
    if not rid:
        return []

    q = db.query(Survey).filter(Survey.run_id == rid)
    if qc_status:
        q = q.filter(Survey.qc_status == qc_status)
    if recorder:
        q = q.filter(Survey.recorder.ilike(f"%{recorder}%"))
    if review_state:
        if review_state == "approved":
            q = q.filter(Survey.review_state != "rejected")
        else:
            q = q.filter(Survey.review_state == review_state)

    return q.order_by(Survey.plot_name).all()


@router.get("/surveys/{survey_key}", summary="Survey detail with flags")
def get_survey(
    survey_key: str,
    run_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    rid = run_id or _latest_run_id(db)
    survey = db.query(Survey).filter(
        Survey.odk_key == survey_key,
        Survey.run_id == rid
    ).first()
    if not survey:
        raise HTTPException(status_code=404, detail=f"Survey {survey_key} not found")

    flags = db.query(QCFlag).filter(
        QCFlag.run_id == rid,
        QCFlag.survey_key == survey_key
    ).order_by(QCFlag.severity).all()

    narrative_row = db.query(Narrative).filter(
        Narrative.survey_key == survey_key,
        Narrative.run_id == rid
    ).first()

    return {
        "survey": SurveyOut.model_validate(survey),
        "flags":  [FlagOut.model_validate(f) for f in flags],
        "narrative": NarrativeOut.model_validate(narrative_row) if narrative_row else None,
    }


@router.get("/plots", response_model=list[PlotOut], summary="List plots")
def list_plots(
    run_id:    Optional[int] = Query(default=None),
    qc_status: Optional[str] = Query(default=None),
    surveyed:  Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
):
    rid = run_id or _latest_run_id(db)
    if not rid:
        return []

    q = db.query(Plot).filter(Plot.run_id == rid)
    if qc_status:
        q = q.filter(Plot.qc_status == qc_status)
    if surveyed is not None:
        q = q.filter(Plot.was_surveyed == surveyed)

    return q.order_by(Plot.plot_name).all()


@router.get("/plots/{plot_name}", summary="Plot detail with flags")
def get_plot(
    plot_name: str,
    run_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    rid = run_id or _latest_run_id(db)
    plot = db.query(Plot).filter(
        Plot.plot_name == plot_name,
        Plot.run_id == rid
    ).first()
    if not plot:
        raise HTTPException(status_code=404, detail=f"Plot '{plot_name}' not found")

    flags = db.query(QCFlag).filter(
        QCFlag.run_id == rid,
        QCFlag.plot_name == plot_name
    ).order_by(QCFlag.severity).all()

    surveys = db.query(Survey).filter(
        Survey.run_id == rid,
        Survey.plot_name == plot_name
    ).all()

    return {
        "plot":    PlotOut.model_validate(plot),
        "flags":   [FlagOut.model_validate(f) for f in flags],
        "surveys": [SurveyOut.model_validate(s) for s in surveys],
    }


@router.get("/flags", response_model=FlagsPage, summary="List QC flags")
def list_flags(
    run_id:    Optional[int] = Query(default=None),
    severity:  Optional[str] = Query(default=None, description="HIGH | MEDIUM | LOW"),
    flag_type: Optional[str] = Query(default=None),
    plot_name: Optional[str] = Query(default=None),
    page:      int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    rid = run_id or _latest_run_id(db)
    if not rid:
        return FlagsPage(total=0, page=page, page_size=page_size, results=[])

    q = db.query(QCFlag).filter(QCFlag.run_id == rid)
    if severity:
        q = q.filter(QCFlag.severity == severity.upper())
    if flag_type:
        q = q.filter(QCFlag.flag_type == flag_type)
    if plot_name:
        q = q.filter(QCFlag.plot_name.ilike(f"%{plot_name}%"))

    # Sort: HIGH first, then MEDIUM, then LOW
    order_map = {"HIGH": 1, "MEDIUM": 2, "LOW": 3}
    from sqlalchemy import case
    q = q.order_by(
        case(order_map, value=QCFlag.severity),
        QCFlag.plot_name,
    )

    total   = q.count()
    results = q.offset((page - 1) * page_size).limit(page_size).all()

    return FlagsPage(total=total, page=page, page_size=page_size, results=results)


@router.get("/species-queue", response_model=list[PendingSpeciesOut],
            summary="Pending species awaiting identification")
def list_pending_species(
    run_id:    Optional[int] = Query(default=None),
    plot_name: Optional[str] = Query(default=None),
    recorder:  Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    rid = run_id or _latest_run_id(db)
    if not rid:
        return []

    q = db.query(PendingSpecies).filter(PendingSpecies.run_id == rid)
    if plot_name:
        q = q.filter(PendingSpecies.plot_name.ilike(f"%{plot_name}%"))
    if recorder:
        q = q.filter(PendingSpecies.recorder.ilike(f"%{recorder}%"))

    return q.order_by(PendingSpecies.plot_name, PendingSpecies.submission_date).all()


@router.get("/narrative/{survey_key}", response_model=NarrativeOut,
            summary="Get AI narrative for a survey")
def get_narrative(
    survey_key: str,
    run_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    rid = run_id or _latest_run_id(db)
    row = db.query(Narrative).filter(
        Narrative.survey_key == survey_key,
        Narrative.run_id == rid
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Narrative not yet generated")
    return row


@router.post("/narrative/{survey_key}", response_model=NarrativeOut,
             summary="(Re-)generate AI narrative for a survey")
def regenerate_narrative(
    survey_key: str,
    run_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    from app.narrative.groq_narrative import generate_narrative

    rid = run_id or _latest_run_id(db)
    if not rid:
        raise HTTPException(status_code=404, detail="No QC run found")

    text = generate_narrative(survey_key, rid)

    row = db.query(Narrative).filter(
        Narrative.survey_key == survey_key,
        Narrative.run_id == rid
    ).first()

    if not row:
        # Return a minimal NarrativeOut
        return NarrativeOut(
            survey_key=survey_key,
            plot_name=None,
            narrative=text,
            model=settings.GROQ_MODEL if settings.GROQ_API_KEY else "rule-based",
            generated_at=datetime.utcnow(),
        )
    return row
