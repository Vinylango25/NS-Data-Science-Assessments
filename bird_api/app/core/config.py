"""
app/core/config.py
------------------
Configuration for the BirdNET Calibration API.

DATA_SOURCE controls where the pipeline reads input data:
  "csv"      — reads from CSV files (local dev / demo)
  "postgres" — reads directly from a PostgreSQL database table

Set via environment variables or .env file.
"""
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # bird_api/
NS_DIR   = BASE_DIR.parent                                 # Natural State/


class Settings(BaseSettings):

    # ── API database (stores thresholds, runs, evaluations) ───────────────────
    # SQLite for local demo. Switch to PostgreSQL for production:
    #   postgresql+psycopg2://user:pass@host:5432/birdnet
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/birdnet.db"

    # ── Input data source ─────────────────────────────────────────────────────
    # "csv"      → read from CSV files defined below
    # "postgres" → read from SOURCE_DB_URL tables defined below
    DATA_SOURCE: str = "csv"

    # CSV paths (used when DATA_SOURCE=csv)
    VAL_PATH:  str = str(NS_DIR / "Data Birds" / "validation_results.csv")
    PRED_PATH: str = str(NS_DIR / "Data Birds" / "birdnet_predictions.csv")
    OUT_DIR:   str = str(NS_DIR / "outputs" / "bird")

    # PostgreSQL source (used when DATA_SOURCE=postgres)
    # Connection string to the database that holds the raw BirdNET tables
    SOURCE_DB_URL:       str = "postgresql+psycopg2://user:pass@localhost:5432/ns_analytics"
    PREDICTIONS_TABLE:   str = "birdnet_predictions"      # table with raw predictions
    VALIDATION_TABLE:    str = "birdnet_validation_clips" # table with validated clips

    # ── Pipeline parameters ───────────────────────────────────────────────────
    TARGET_PRECISION: float = 0.99
    RANDOM_STATE:     int   = 42
    BIRDNET_VERSION:  str   = "v2.4"

    class Config:
        env_file = str(BASE_DIR / ".env")
        extra = "ignore"


settings = Settings()
