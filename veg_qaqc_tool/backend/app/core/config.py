"""
app/core/config.py
------------------
Configuration for the Vegetation QA/QC API.

DATA_SOURCE controls where the pipeline reads input data:
  "csv"      — reads from CSV files in DATA_DIR (local dev / demo)
  "postgres" — reads from SOURCE_DB_URL database tables (production)

Set via environment variables or .env file.
"""
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent   # veg_qaqc_tool/backend/
NS_DIR   = BASE_DIR.parent.parent                          # Natural State/ or NS/


class Settings(BaseSettings):
    # ── API ────────────────────────────────────────────────────────────────────
    APP_NAME: str = "Vegetation QA/QC API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── Data source ────────────────────────────────────────────────────────────
    # "csv" = local files, "postgres" = live database
    DATA_SOURCE: str = "csv"

    # ── CSV mode paths (relative to NS project folder) ────────────────────────
    DATA_DIR: Path = NS_DIR / "Data Vegetation"
    ODK_DIR:  Path = NS_DIR / "Data Vegetation" / "ODK Data Exports"
    ENT_DIR:  Path = NS_DIR / "Data Vegetation" / "Entity lists"

    # ── PostgreSQL source (DATA_SOURCE=postgres) ───────────────────────────────
    SOURCE_DB_URL:             str = "postgresql+psycopg2://user:pass@localhost:5432/ns_analytics"
    TABLE_SURVEY:              str = "herbaceous_veg_survey"
    TABLE_QUADRAT:             str = "herbaceous_veg_survey_quadrat_repeat"
    TABLE_ADDSP:               str = "herbaceous_veg_survey_additional_species_repeat"
    TABLE_REGISTER_PLOTS:      str = "register_vegetation_plots"
    TABLE_VEGPLOTS:            str = "vegplots"
    TABLE_SPECIES:             str = "species"
    TABLE_SPECIES_EXTRA:       str = "species_extra"
    TABLE_CENTROIDS:           str = "centroids"

    # ── API internal database (stores QC run results) ─────────────────────────
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/vegqaqc.db"

    # ── Output directory ───────────────────────────────────────────────────────
    OUT_DIR: Path = BASE_DIR / "outputs"

    # ── QC scorecard parameters (configurable per project) ────────────────────
    MAX_SURVEY_DURATION_MIN:    float = 180.0   # S3: flag if survey > N minutes
    MIN_TRANSECT_LENGTH_M:      float = 40.0    # P3: flag if transect < N metres
    MAX_TRANSECT_LENGTH_M:      float = 60.0    # P3: flag if transect > N metres
    MAX_MIDPOINT_DISPLACEMENT_M: float = 25.0   # P4: SOP maximum displacement
    MAX_QUADRAT_GPS_ACCURACY_M: float = 5.0     # Q1: device config requirement
    EXPECTED_QUADRATS_PER_SURVEY: int = 20      # must be exactly 20 per SOP

    # ── AI Narrative (Groq) ────────────────────────────────────────────────────
    GROQ_API_KEY: str = ""
    GROQ_MODEL:   str = "llama-3.1-8b-instant"
    NARRATIVE_ENABLED: bool = True

    # ── CORS (set to your Vercel frontend URL in production) ──────────────────
    CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:3000", "*"]

    class Config:
        env_file = str(BASE_DIR / ".env")
        extra = "ignore"


settings = Settings()
