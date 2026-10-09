"""
app/pipeline/loader.py
----------------------
Loads vegetation survey data from either CSV files or PostgreSQL.

Returns identical DataFrames regardless of source.
"""
import logging
import pandas as pd
from app.core.config import settings

log = logging.getLogger(__name__)


def load_data() -> dict:
    """
    Load all vegetation data tables.

    Returns
    -------
    dict with keys:
      - reg:      register_vegetation_plots
      - surv:     herbaceous_veg_survey
      - quad:     quadrat_repeat
      - addsp:    additional_species_repeat
      - plots:    vegplots entity list
      - species:  species entity list
      - sp_extra: species_extra entity list
      - centroids: centroids entity list
    """
    source = settings.DATA_SOURCE

    if source == "csv":
        return _load_from_csv()
    elif source == "postgres":
        return _load_from_postgres()
    else:
        raise ValueError(f"Unknown DATA_SOURCE: {source}")


def _load_from_csv() -> dict:
    """Load from local CSV files."""
    log.info("Loading data from CSV files ...")

    odk_dir = settings.ODK_DIR
    ent_dir = settings.ENT_DIR

    data = {
        "reg":       pd.read_csv(odk_dir / "register_vegetation_plots.csv"),
        "surv":      pd.read_csv(odk_dir / "herbaceous_veg_survey.csv"),
        "quad":      pd.read_csv(odk_dir / "herbaceous_veg_survey-quadrat_repeat.csv"),
        "addsp":     pd.read_csv(odk_dir / "herbaceous_veg_survey-additional_species_repeat.csv"),
        "plots":     pd.read_csv(ent_dir / "vegplots.csv"),
        "species":   pd.read_csv(ent_dir / "species.csv"),
        "sp_extra":  pd.read_csv(ent_dir / "species_extra.csv"),
        "centroids": pd.read_csv(ent_dir / "centroids.csv"),
    }

    for key, df in data.items():
        log.info(f"  {key:<10}: {len(df):>4} rows")

    return data


def _load_from_postgres() -> dict:
    """Load from PostgreSQL database."""
    log.info("Loading data from PostgreSQL ...")
    from sqlalchemy import create_engine

    engine = create_engine(settings.SOURCE_DB_URL)

    data = {
        "reg":       pd.read_sql_table(settings.TABLE_REGISTER_PLOTS, engine),
        "surv":      pd.read_sql_table(settings.TABLE_SURVEY, engine),
        "quad":      pd.read_sql_table(settings.TABLE_QUADRAT, engine),
        "addsp":     pd.read_sql_table(settings.TABLE_ADDSP, engine),
        "plots":     pd.read_sql_table(settings.TABLE_VEGPLOTS, engine),
        "species":   pd.read_sql_table(settings.TABLE_SPECIES, engine),
        "sp_extra":  pd.read_sql_table(settings.TABLE_SPECIES_EXTRA, engine),
        "centroids": pd.read_sql_table(settings.TABLE_CENTROIDS, engine),
    }

    for key, df in data.items():
        log.info(f"  {key:<10}: {len(df):>4} rows")

    return data
