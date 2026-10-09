"""
app/db/models.py
----------------
SQLAlchemy ORM models for the Vegetation QA/QC API.

Tables created automatically on startup via init_db().
Compatible with SQLite (dev) and PostgreSQL (production).
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    DateTime, Text, Index, JSON
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# ── QC Run ────────────────────────────────────────────────────────────────────

class QCRun(Base):
    """One row per pipeline execution."""
    __tablename__ = "qc_runs"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    run_at           = Column(DateTime, default=datetime.utcnow)
    data_source      = Column(String,  nullable=False, default="csv")
    status           = Column(String,  nullable=False, default="queued")
    # queued | running | complete | error
    n_surveys        = Column(Integer, nullable=True)
    n_plots          = Column(Integer, nullable=True)
    n_quadrats       = Column(Integer, nullable=True)
    n_flags_high     = Column(Integer, nullable=True)
    n_flags_medium   = Column(Integer, nullable=True)
    n_flags_low      = Column(Integer, nullable=True)
    n_pending_species= Column(Integer, nullable=True)
    completed_at     = Column(DateTime, nullable=True)
    error_msg        = Column(Text, nullable=True)
    # Scorecard params used for this run (JSON snapshot)
    scorecard_params = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_qcrun_status", "status"),
    )


# ── Survey ────────────────────────────────────────────────────────────────────

class Survey(Base):
    """One row per survey submission (mirrors herbaceous_veg_survey)."""
    __tablename__ = "surveys"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    run_id              = Column(Integer, nullable=True)
    odk_key             = Column(String,  nullable=False, index=True)   # ODK submission KEY
    plot_uuid           = Column(String,  nullable=True)
    plot_name           = Column(String,  nullable=True, index=True)
    submission_date     = Column(String,  nullable=True)
    submitter           = Column(String,  nullable=True)
    recorder            = Column(String,  nullable=True)
    start_time          = Column(String,  nullable=True)
    end_time            = Column(String,  nullable=True)
    duration_min        = Column(Float,   nullable=True)
    review_state        = Column(String,  nullable=True)   # approved | rejected | null
    quadrats_completed  = Column(Integer, nullable=True)
    quadrats_with_herbs = Column(Integer, nullable=True)
    species_occurrences = Column(Integer, nullable=True)
    additional_species  = Column(Integer, nullable=True)
    n_flags             = Column(Integer, nullable=True, default=0)
    qc_status           = Column(String,  nullable=True)   # pass | warning | fail
    stratum_label       = Column(String,  nullable=True)
    area_label          = Column(String,  nullable=True)

    __table_args__ = (
        Index("ix_survey_run", "run_id"),
        Index("ix_survey_plot", "plot_name"),
    )


# ── Plot ──────────────────────────────────────────────────────────────────────

class Plot(Base):
    """One row per registered vegetation plot."""
    __tablename__ = "plots"

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    run_id                = Column(Integer, nullable=True)
    plot_uuid             = Column(String,  nullable=True, index=True)
    plot_name             = Column(String,  nullable=False, index=True)
    stratum_label         = Column(String,  nullable=True)
    area_label            = Column(String,  nullable=True)
    is_viable             = Column(Boolean, nullable=True)
    centroid_lat          = Column(Float,   nullable=True)
    centroid_lon          = Column(Float,   nullable=True)
    geohash               = Column(String,  nullable=True)
    # Registration measurements
    transect_length_m     = Column(Float,   nullable=True)
    midpoint_displacement_m = Column(Float, nullable=True)
    ep_a_lat              = Column(Float,   nullable=True)
    ep_a_lon              = Column(Float,   nullable=True)
    ep_b_lat              = Column(Float,   nullable=True)
    ep_b_lon              = Column(Float,   nullable=True)
    mid_lat               = Column(Float,   nullable=True)
    mid_lon               = Column(Float,   nullable=True)
    # Survey status
    was_surveyed          = Column(Boolean, nullable=True)
    approved_survey_count = Column(Integer, nullable=True, default=0)
    total_species_occurrences = Column(Integer, nullable=True)
    quadrats_with_herbs   = Column(Integer, nullable=True)
    total_quadrats        = Column(Integer, nullable=True)
    n_flags               = Column(Integer, nullable=True, default=0)
    qc_status             = Column(String,  nullable=True)   # pass | warning | fail

    __table_args__ = (
        Index("ix_plot_run", "run_id"),
    )


# ── QC Flag ───────────────────────────────────────────────────────────────────

class QCFlag(Base):
    """One row per flagged issue — the core output of the QC pipeline."""
    __tablename__ = "qc_flags"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    run_id           = Column(Integer, nullable=True, index=True)
    flag_id          = Column(String,  nullable=False)   # S1, S2, P3, Q1 ...
    flag_type        = Column(String,  nullable=False, index=True)
    severity         = Column(String,  nullable=False, index=True)  # HIGH|MEDIUM|LOW
    survey_key       = Column(String,  nullable=True)
    plot_name        = Column(String,  nullable=True, index=True)
    quadrat_number   = Column(Integer, nullable=True)
    field_value      = Column(Text,    nullable=True)
    expected_value   = Column(Text,    nullable=True)
    description      = Column(Text,    nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_flag_severity", "severity"),
        Index("ix_flag_type", "flag_type"),
    )


# ── Pending Species ───────────────────────────────────────────────────────────

class PendingSpecies(Base):
    """Additional species entries awaiting taxonomic identification."""
    __tablename__ = "pending_species"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    run_id              = Column(Integer, nullable=True, index=True)
    survey_key          = Column(String,  nullable=True)
    plot_name           = Column(String,  nullable=True, index=True)
    quadrat_number      = Column(Integer, nullable=True)
    recorder            = Column(String,  nullable=True)
    submission_date     = Column(String,  nullable=True)
    provisional_name    = Column(String,  nullable=True)
    validated_name      = Column(String,  nullable=True)
    review_status       = Column(String,  nullable=True)   # pending | confirmed | rejected
    new_record_reason   = Column(String,  nullable=True)
    species_entry_mode  = Column(String,  nullable=True)

    __table_args__ = (
        Index("ix_pending_plot", "plot_name"),
        Index("ix_pending_status", "review_status"),
    )


# ── AI Narrative ──────────────────────────────────────────────────────────────

class Narrative(Base):
    """AI-generated QC narrative per survey."""
    __tablename__ = "narratives"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    run_id       = Column(Integer, nullable=True, index=True)
    survey_key   = Column(String,  nullable=True, index=True)
    plot_name    = Column(String,  nullable=True)
    narrative    = Column(Text,    nullable=True)
    model        = Column(String,  nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow)
