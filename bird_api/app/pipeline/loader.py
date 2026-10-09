"""
app/pipeline/loader.py
----------------------
Loads validation clips and BirdNET predictions from either:
  - CSV files (DATA_SOURCE=csv)
  - PostgreSQL tables (DATA_SOURCE=postgres)

Returns identical DataFrames regardless of source — the calibration
pipeline sees the same interface in both cases.
"""
import logging
import pandas as pd
from app.core.config import settings

log = logging.getLogger(__name__)


def load_data(
    val_path:  str = None,
    pred_path: str = None,
    data_source: str = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load validation clips and predictions.

    Parameters
    ----------
    val_path    : CSV path or PostgreSQL table name for validation clips.
                  Defaults to settings.VAL_PATH / settings.VALIDATION_TABLE.
    pred_path   : CSV path or PostgreSQL table name for predictions.
                  Defaults to settings.PRED_PATH / settings.PREDICTIONS_TABLE.
    data_source : "csv" or "postgres". Defaults to settings.DATA_SOURCE.

    Returns
    -------
    (val, pred) — cleaned DataFrames ready for the calibration pipeline.
    """
    source = data_source or settings.DATA_SOURCE

    if source == "csv":
        return _load_csv(
            val_path  or settings.VAL_PATH,
            pred_path or settings.PRED_PATH,
        )
    elif source == "postgres":
        return _load_postgres(
            val_path  or settings.VALIDATION_TABLE,
            pred_path or settings.PREDICTIONS_TABLE,
        )
    else:
        raise ValueError(f"Unknown DATA_SOURCE: '{source}'. Use 'csv' or 'postgres'.")


def _load_csv(val_path: str, pred_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load from local CSV files."""
    log.info(f"Loading CSV: {val_path}")
    val = pd.read_csv(val_path)

    log.info(f"Loading CSV: {pred_path}")
    pred = pd.read_csv(pred_path)

    val, pred = _clean(val, pred)
    log.info(f"  Validation  : {len(val):,} rows")
    log.info(f"  Predictions : {len(pred):,} rows")
    return val, pred


def _load_postgres(val_table: str, pred_table: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load from PostgreSQL tables.

    Requires SOURCE_DB_URL to be set in config/.env.
    Uses pandas read_sql — no ORM needed for raw data loading.
    """
    from sqlalchemy import create_engine, text

    log.info(f"Connecting to PostgreSQL: {settings.SOURCE_DB_URL[:40]}...")
    engine = create_engine(settings.SOURCE_DB_URL)

    with engine.connect() as conn:
        log.info(f"Loading table: {val_table}")
        val = pd.read_sql(text(f"SELECT * FROM {val_table}"), conn)

        log.info(f"Loading table: {pred_table}")
        pred = pd.read_sql(text(f"SELECT * FROM {pred_table}"), conn)

    val, pred = _clean(val, pred)
    log.info(f"  Validation  : {len(val):,} rows")
    log.info(f"  Predictions : {len(pred):,} rows")
    return val, pred


def _clean(val: pd.DataFrame, pred: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Minimal cleaning applied regardless of source.
    Column names are normalised so the pipeline works
    whether data comes from CSV exports or a database.
    """
    val.columns  = val.columns.str.strip()
    pred.columns = pred.columns.str.strip()

    # Enforce types
    val["outcome"]    = pd.to_numeric(val["outcome"],    errors="coerce").astype("Int64")
    val["confidence"] = pd.to_numeric(val["confidence"], errors="coerce")
    pred["confidence"]= pd.to_numeric(pred["confidence"],errors="coerce")

    # Drop unresolvable rows
    val  = val.dropna(subset=["confidence", "commonName"]).drop_duplicates().reset_index(drop=True)
    pred = pred.dropna(subset=["confidence", "common_name"]).drop_duplicates().reset_index(drop=True)

    # Align species column name
    val = val.rename(columns={"commonName": "common_name"})

    return val, pred
