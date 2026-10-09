"""
app/db/models.py
----------------
SQLAlchemy ORM models for the BirdNET Calibration API.

Compatible with SQLite (dev/demo) and PostgreSQL (production).
Migration: change DATABASE_URL in config — no code changes needed.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, Index
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class CalibrationRun(Base):
    """Metadata for each pipeline execution."""
    __tablename__ = "calibration_runs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    run_at          = Column(DateTime, default=datetime.utcnow, nullable=False)
    birdnet_version = Column(String,  nullable=False)
    data_source     = Column(String,  nullable=False)   # "csv" | "postgres"
    val_path        = Column(String,  nullable=True)    # CSV path or table name
    pred_path       = Column(String,  nullable=True)
    target_precision= Column(Float,   nullable=False)
    random_state    = Column(Integer, nullable=False)
    n_species       = Column(Integer, nullable=True)
    n_predictions   = Column(Integer, nullable=True)
    n_observations  = Column(Integer, nullable=True)
    status          = Column(String,  default="complete")  # complete | error
    error_msg       = Column(Text,    nullable=True)


class SpeciesThreshold(Base):
    """
    Per-species confidence thresholds derived by the calibration pipeline.

    One active row per (common_name, birdnet_version).
    Never overwrite — insert new rows to preserve history.
    """
    __tablename__ = "species_thresholds"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    run_id             = Column(Integer, nullable=True)
    common_name        = Column(String,  nullable=False)
    birdnet_version    = Column(String,  nullable=False)
    threshold_p99      = Column(Float,   nullable=False)
    threshold_reliable = Column(Boolean, nullable=False)
    intercept_b0       = Column(Float,   nullable=True)
    coef_logit_b1      = Column(Float,   nullable=True)
    n_validated        = Column(Integer, nullable=True)
    n_true_positives   = Column(Integer, nullable=True)
    method             = Column(String,  nullable=True)  # logistic_logit_score | fallback_min_confidence
    target_precision   = Column(Float,   default=0.99)
    random_state       = Column(Integer, default=42)
    derived_at         = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_threshold_species_version", "common_name", "birdnet_version"),
    )


class ModelEvaluation(Base):
    """Per-species model quality metrics from each calibration run."""
    __tablename__ = "model_evaluations"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    run_id             = Column(Integer, nullable=True)
    common_name        = Column(String,  nullable=False)
    birdnet_version    = Column(String,  nullable=False)
    threshold_p99      = Column(Float,   nullable=True)
    threshold_reliable = Column(Boolean, nullable=True)
    auc                = Column(Float,   nullable=True)
    brier_score        = Column(Float,   nullable=True)
    log_loss           = Column(Float,   nullable=True)
    note               = Column(String,  nullable=True)
    evaluated_at       = Column(DateTime, default=datetime.utcnow)


class LabelledPrediction(Base):
    """
    Labelled BirdNET predictions.

    Populated by the pipeline. If predictions already live in PostgreSQL,
    this table mirrors only the labelling columns — the full prediction
    record stays in the source DB.
    """
    __tablename__ = "labelled_predictions"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    run_id          = Column(Integer, nullable=True)
    common_name     = Column(String,  nullable=False)
    confidence      = Column(Float,   nullable=False)
    folder          = Column(String,  nullable=True)   # site code
    begin_path      = Column(String,  nullable=True)   # WAV file path
    birdnet_version = Column(String,  nullable=True)
    threshold_p99   = Column(Float,   nullable=True)
    observation     = Column(Integer, nullable=True)   # 1 | 0 | NULL
    labelled_at     = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_pred_species", "common_name"),
        Index("ix_pred_folder",  "folder"),
        Index("ix_pred_obs",     "observation"),
    )
