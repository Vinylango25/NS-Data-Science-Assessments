"""
app/pipeline/qc_service.py
--------------------------
Vegetation QA/QC Pipeline.

Runs the full scorecard against ODK survey data.
All logic ported from vegetation_challenge.py (NS project).

Scorecard checks:
  Survey level : S1 rejected, S2 duplicate, S3 duration outlier,
                 S4 unregistered plot
  Plot level   : P1 not surveyed, P2 non-viable surveyed,
                 P3 transect length, P4 midpoint displacement
  Quadrat level: Q1 GPS accuracy, Q2 herbs/no species, Q3 no herbs/species
  Species      : Q4 trailing whitespace, Q5 non-standard canonical
  Review       : R1 pending species

Outputs are persisted to the API database (surveys, plots, qc_flags,
pending_species tables).
"""
import logging
import math
import re
from datetime import datetime

import numpy as np
import pandas as pd

from app.core.config import settings
from app.db.database import SessionLocal, init_db
from app.db.models import QCRun, Survey, Plot, QCFlag, PendingSpecies

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    p = math.pi / 180
    dlat = (lat2 - lat1) * p
    dlon = (lon2 - lon1) * p
    a = (math.sin(dlat / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def safe_haversine(row, la1, lo1, la2, lo2):
    vals = [row.get(la1), row.get(lo1), row.get(la2), row.get(lo2)]
    if any(pd.isna(v) for v in vals):
        return None
    return haversine(float(row[la1]), float(row[lo1]),
                     float(row[la2]), float(row[lo2]))


def parse_geom(g):
    if pd.isna(g):
        return None, None
    parts = str(g).strip().split()
    try:
        return float(parts[0]), float(parts[1])
    except (IndexError, ValueError):
        return None, None


def qc_status_from_flags(n_high: int, n_medium: int, n_low: int) -> str:
    if n_high > 0:
        return "fail"
    if n_medium > 0:
        return "warning"
    if n_low > 0:
        return "warning"
    return "pass"


VALID_CANON = re.compile(r"^([A-Z][a-z]+_[a-z]|[Uu]nknown_|herb_\d|wood_\d)")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def run_qc_pipeline(data: dict, run_id: int) -> dict:
    """
    Run the full QC scorecard against loaded data.

    Parameters
    ----------
    data   : dict from loader.load_data()
    run_id : ID of the QCRun record in the API database

    Returns
    -------
    dict with summary stats
    """
    reg    = data["reg"]
    surv   = data["surv"]
    quad   = data["quad"]
    addsp  = data["addsp"]
    plots  = data["plots"]
    sp_extra = data["sp_extra"]

    params = {
        "max_duration_min":       settings.MAX_SURVEY_DURATION_MIN,
        "min_transect_m":         settings.MIN_TRANSECT_LENGTH_M,
        "max_transect_m":         settings.MAX_TRANSECT_LENGTH_M,
        "max_displacement_m":     settings.MAX_MIDPOINT_DISPLACEMENT_M,
        "max_gps_accuracy_m":     settings.MAX_QUADRAT_GPS_ACCURACY_M,
        "expected_quadrats":      settings.EXPECTED_QUADRATS_PER_SURVEY,
    }

    log.info("=" * 60)
    log.info("Vegetation QA/QC Pipeline")
    log.info(f"  Run ID   : {run_id}")
    log.info(f"  Surveys  : {len(surv)}")
    log.info(f"  Quadrats : {len(quad)}")
    log.info("=" * 60)

    # ── 1. Parse geometry ─────────────────────────────────────────────────────
    plots = plots.copy()
    plots[["centroid_lat", "centroid_lon"]] = pd.DataFrame(
        plots["geometry"].apply(parse_geom).tolist(), index=plots.index
    )

    # ── 2. Parse timestamps and GPS ──────────────────────────────────────────
    surv = surv.copy()
    surv["start_dt"] = pd.to_datetime(surv["survey_begin-start_time"], errors="coerce")
    surv["end_dt"]   = pd.to_datetime(surv["survey_end-end_time"],     errors="coerce")
    surv["duration_min"] = (surv["end_dt"] - surv["start_dt"]).dt.total_seconds() / 60

    # Registration GPS
    reg = reg.copy()
    for prefix, short in [
        ("plot_metadata-collect_points-endpoint_a-location_endpoint_a-", "ep_a_"),
        ("plot_metadata-collect_points-midpoint-location_midpoint-",     "mid_"),
        ("plot_metadata-collect_points-endpoint_b-location_endpoint_b-", "ep_b_"),
    ]:
        for coord in ["Latitude", "Longitude"]:
            src = prefix + coord
            dst = short + coord.lower()
            if src in reg.columns:
                reg[dst] = pd.to_numeric(reg[src], errors="coerce")

    # Quadrat GPS
    quad = quad.copy()
    for coord in ["Latitude", "Longitude", "Accuracy"]:
        src = f"location_quadrat-{coord}"
        if src in quad.columns:
            quad[f"q_{coord.lower()}"] = pd.to_numeric(quad[src], errors="coerce")

    # ── 3. Compute transect lengths and midpoint displacements ───────────────
    reg["transect_length_m"] = reg.apply(
        lambda r: safe_haversine(r, "ep_a_latitude", "ep_a_longitude",
                                 "ep_b_latitude", "ep_b_longitude"), axis=1
    )

    reg_with_plots = reg.merge(
        plots[["plot_uuid", "plot_name", "centroid_lat", "centroid_lon",
               "is_viable", "stratum_label", "geohash"]],
        left_on="plot_selection-selected_plot_uuid",
        right_on="plot_uuid",
        how="left"
    )
    reg_with_plots["midpoint_vs_centroid_m"] = reg_with_plots.apply(
        lambda r: safe_haversine(r, "mid_latitude", "mid_longitude",
                                 "centroid_lat", "centroid_lon"), axis=1
    )

    # ── 4. Enrich surveys ────────────────────────────────────────────────────
    surv_enriched = surv.merge(
        plots[["__id", "plot_name", "centroid_lat", "centroid_lon",
               "is_viable", "stratum_label", "area_label"]].rename(
                   columns={"__id": "plot_uuid"}),
        left_on="plot_selection-selected_plot_uuid",
        right_on="plot_uuid",
        how="left"
    )

    # ── 5. Enrich quadrats ───────────────────────────────────────────────────
    quad_enriched = quad.merge(
        surv_enriched[["KEY", "plot_name", "stratum_label",
                       "start_dt", "plot_selection-selected_plot_uuid"]],
        left_on="PARENT_KEY", right_on="KEY", how="left"
    )
    quad_enriched = quad_enriched.rename(
        columns={"KEY_x": "KEY", "KEY_y": "survey_KEY"}
    )

    # ── 6. Run QC checks ─────────────────────────────────────────────────────
    flags = []

    def add_flag(flag_id, flag_type, severity, survey_key, plot_name,
                 quadrat_number, field_value, expected_value, description):
        flags.append({
            "run_id":          run_id,
            "flag_id":         flag_id,
            "flag_type":       flag_type,
            "severity":        severity,
            "survey_key":      survey_key,
            "plot_name":       plot_name,
            "quadrat_number":  quadrat_number,
            "field_value":     str(field_value) if field_value is not None else None,
            "expected_value":  str(expected_value) if expected_value is not None else None,
            "description":     description,
        })

    # S1 — Rejected surveys
    rejected = surv[surv["ReviewState"] == "rejected"]
    for _, row in rejected.iterrows():
        add_flag("S1", "survey_rejected", "HIGH",
                 row["KEY"], row.get("plot_name"), None,
                 "rejected", "approved",
                 f"Survey by {row.get('SubmitterName','?')} on {row.get('SubmissionDate','?')} is rejected.")

    # S2 — Duplicate surveys
    dup_uuids = surv[surv["plot_selection-selected_plot_uuid"].duplicated(keep=False)]
    for uuid, grp in dup_uuids.groupby("plot_selection-selected_plot_uuid"):
        pname = grp.iloc[0].get("plot_name", uuid)
        keys  = "; ".join(grp["KEY"].tolist())
        add_flag("S2", "duplicate_survey", "HIGH",
                 keys, pname, None,
                 f"{len(grp)} submissions", "1 per plot",
                 f"Plot '{pname}' has {len(grp)} survey submissions.")

    # S3 — Duration outlier
    for _, row in surv_enriched[surv_enriched["duration_min"] > params["max_duration_min"]].iterrows():
        add_flag("S3", "survey_duration_outlier", "MEDIUM",
                 row["KEY"], row.get("plot_name"), None,
                 f"{row['duration_min']:.1f} min",
                 f"< {params['max_duration_min']} min",
                 f"Survey ran {row['duration_min']:.0f} min — may be a delayed submission.")

    # S4 — Unregistered plot
    reg_uuids  = set(plots["__id"].tolist())
    surv_uuids = set(surv["plot_selection-selected_plot_uuid"].tolist())
    for u in (surv_uuids - reg_uuids):
        for _, row in surv[surv["plot_selection-selected_plot_uuid"] == u].iterrows():
            add_flag("S4", "unregistered_plot", "HIGH",
                     row["KEY"], u, None, u,
                     "UUID in vegplots entity list",
                     "Survey references a plot UUID not in the entity list.")

    # P1 — Registered not surveyed
    not_surveyed = reg_uuids - surv_uuids
    for u in not_surveyed:
        row = plots[plots["__id"] == u]
        if len(row) and row.iloc[0]["is_viable"] == "yes":
            pname = row.iloc[0]["plot_name"]
            add_flag("P1", "plot_not_surveyed", "MEDIUM",
                     None, pname, None,
                     "no survey", "survey expected",
                     f"Plot '{pname}' is registered and viable but has no survey.")

    # P2 — Non-viable plot surveyed
    nv_ids = set(plots[plots["is_viable"] == "no"]["__id"].tolist())
    for _, row in surv_enriched[surv_enriched["plot_selection-selected_plot_uuid"].isin(nv_ids)].iterrows():
        add_flag("P2", "non_viable_plot_surveyed", "HIGH",
                 row["KEY"], row.get("plot_name"), None,
                 "is_viable=no", "should not be surveyed",
                 f"Plot '{row.get('plot_name')}' is non-viable but has a survey.")

    # P3 — Transect length
    for _, row in reg_with_plots.iterrows():
        tlen  = row["transect_length_m"]
        pname = row.get("plot_name", row.get("plot_selection-selected_plot_uuid", "?"))
        if pd.isna(tlen):
            add_flag("P3", "transect_length_missing", "MEDIUM",
                     row["KEY"], pname, None, "no GPS", "~50 m",
                     f"Cannot compute transect length for '{pname}' — endpoint GPS missing.")
        elif tlen < params["min_transect_m"]:
            add_flag("P3", "transect_too_short", "MEDIUM",
                     row["KEY"], pname, None,
                     f"{tlen:.1f} m", f"{params['min_transect_m']}–{params['max_transect_m']} m",
                     f"Transect is {tlen:.1f} m — well below the expected 50 m.")
        elif tlen > params["max_transect_m"]:
            add_flag("P3", "transect_too_long", "LOW",
                     row["KEY"], pname, None,
                     f"{tlen:.1f} m", f"{params['min_transect_m']}–{params['max_transect_m']} m",
                     f"Transect is {tlen:.1f} m — slightly over expected 50 m (GPS noise likely).")

    # P4 — Midpoint displacement
    for _, row in reg_with_plots.iterrows():
        dist  = row["midpoint_vs_centroid_m"]
        pname = row.get("plot_name", "?")
        if dist is not None and dist > params["max_displacement_m"]:
            add_flag("P4", "midpoint_displacement", "HIGH",
                     row["KEY"], pname, None,
                     f"{dist:.1f} m", f"≤ {params['max_displacement_m']} m (SOP max)",
                     f"Midpoint is {dist:.1f} m from prescribed centroid — exceeds SOP limit.")

    # Q1 — Quadrat GPS accuracy
    for _, row in quad_enriched[quad_enriched.get("q_accuracy", pd.Series(dtype=float)) > params["max_gps_accuracy_m"]].iterrows():
        add_flag("Q1", "quadrat_gps_poor_accuracy", "LOW",
                 row["PARENT_KEY"], row.get("plot_name"), row.get("quadrat_number"),
                 f"{row['q_accuracy']:.1f} m", f"≤ {params['max_gps_accuracy_m']} m",
                 f"Quadrat {row.get('quadrat_number')} GPS accuracy {row['q_accuracy']:.1f} m.")

    # Q2 — Herbs present but no species
    herb_yes = quad_enriched[quad_enriched["herbs_present"] == "yes"]
    no_sp    = herb_yes[
        herb_yes["herb_species-selected_herb_species_uuids"].isna() &
        (herb_yes["additional_species_present"] != "yes")
    ]
    for _, row in no_sp.iterrows():
        add_flag("Q2", "herbs_present_no_species", "HIGH",
                 row["PARENT_KEY"], row.get("plot_name"), row.get("quadrat_number"),
                 "herbs_present=yes, 0 species", "≥1 species",
                 f"Quadrat {row.get('quadrat_number')} has herbs but no species recorded.")

    # Q3 — No herbs but species listed
    herb_no    = quad_enriched[quad_enriched["herbs_present"] == "no"]
    sp_anyway  = herb_no[herb_no["herb_species-selected_herb_species_uuids"].notna()]
    for _, row in sp_anyway.iterrows():
        add_flag("Q3", "no_herbs_but_species", "HIGH",
                 row["PARENT_KEY"], row.get("plot_name"), row.get("quadrat_number"),
                 "herbs_present=no, species listed", "no species",
                 f"Quadrat {row.get('quadrat_number')} has no herbs but species UUIDs populated.")

    # Q4 — Trailing whitespace in validated_name
    for _, row in addsp[addsp["validated_name"].str.endswith(" ", na=False)].iterrows():
        add_flag("Q4", "canonical_trailing_whitespace", "LOW",
                 row["PARENT_KEY"], row.get("plot_name"), None,
                 repr(row["validated_name"]), "no trailing spaces",
                 f"Canonical '{row['validated_name']}' has trailing whitespace.")

    # Q5 — Non-standard canonical format
    bad_names = addsp[
        addsp["new_missing_canonical"].notna() &
        ~addsp["new_missing_canonical"].str.strip().str.match(VALID_CANON).fillna(False)
    ]
    for _, row in bad_names.iterrows():
        add_flag("Q5", "non_standard_canonical", "LOW",
                 row["PARENT_KEY"], row.get("plot_name"), None,
                 row["new_missing_canonical"], "Genus_species format",
                 f"'{row['new_missing_canonical']}' does not follow Genus_species format.")

    # R1 — Pending species review
    pending = addsp[addsp["review_status"] == "pending"]
    for parent_key, grp in pending.groupby("PARENT_KEY"):
        rows = surv_enriched[surv_enriched["KEY"] == parent_key]
        pname = rows["plot_name"].iloc[0] if len(rows) else parent_key
        add_flag("R1", "species_pending_review", "MEDIUM",
                 parent_key, pname, None,
                 f"{len(grp)} pending", "all species identified",
                 f"{len(grp)} additional species pending taxonomic review in this survey.")

    flags_df = pd.DataFrame(flags)

    log.info(f"  Total flags: {len(flags_df)}")
    if len(flags_df):
        for sev in ["HIGH", "MEDIUM", "LOW"]:
            n = (flags_df["severity"] == sev).sum()
            log.info(f"    {sev:<8}: {n}")

    # ── 7. Build survey summaries ─────────────────────────────────────────────
    sp_counts = (
        quad_enriched.groupby("PARENT_KEY").agg(
            quadrats_completed=("quadrat_number", "count"),
            quadrats_with_herbs=("herbs_present", lambda x: (x == "yes").sum()),
            total_species_occurrences=(
                "herb_species-count_herb_species",
                lambda x: pd.to_numeric(x, errors="coerce").sum()
            ),
        ).reset_index().rename(columns={"PARENT_KEY": "KEY"})
    )

    addsp_counts = (
        addsp.groupby("PARENT_KEY").size()
        .reset_index(name="additional_species_entries")
        .rename(columns={"PARENT_KEY": "KEY"})
    )

    survey_summary = (
        surv_enriched
        .merge(sp_counts, on="KEY", how="left")
        .merge(addsp_counts, on="KEY", how="left")
    )
    survey_summary["additional_species_entries"] = (
        survey_summary["additional_species_entries"].fillna(0).astype(int)
    )

    # Flag counts per survey
    if len(flags_df):
        sflag_high   = flags_df[flags_df["severity"] == "HIGH"].groupby("survey_key").size()
        sflag_medium = flags_df[flags_df["severity"] == "MEDIUM"].groupby("survey_key").size()
        sflag_low    = flags_df[flags_df["severity"] == "LOW"].groupby("survey_key").size()
    else:
        sflag_high = sflag_medium = sflag_low = pd.Series(dtype=int)

    # ── 8. Build plot summaries ───────────────────────────────────────────────
    plot_summary = plots[["__id", "plot_name", "stratum_label", "area_label",
                           "is_viable", "centroid_lat", "centroid_lon", "geohash"]].copy()

    surveyed_uuids = set(surv["plot_selection-selected_plot_uuid"].tolist())
    plot_summary["was_surveyed"] = plot_summary["__id"].isin(surveyed_uuids)

    approved_surv = surv[surv["ReviewState"] != "rejected"]
    approved_per_plot = (
        approved_surv.groupby("plot_selection-selected_plot_uuid").size()
        .reset_index(name="approved_survey_count")
        .rename(columns={"plot_selection-selected_plot_uuid": "__id"})
    )
    plot_summary = plot_summary.merge(approved_per_plot, on="__id", how="left")
    plot_summary["approved_survey_count"] = plot_summary["approved_survey_count"].fillna(0).astype(int)

    approved_keys  = set(approved_surv["KEY"].tolist())
    approved_quads = quad_enriched[quad_enriched["PARENT_KEY"].isin(approved_keys)]

    richness = (
        approved_quads.groupby("plot_name").agg(
            total_species_occurrences=(
                "herb_species-count_herb_species",
                lambda x: pd.to_numeric(x, errors="coerce").sum()
            ),
            quadrats_with_herbs=("herbs_present", lambda x: (x == "yes").sum()),
            total_quadrats=("quadrat_number", "count"),
        ).reset_index()
    )
    plot_summary = plot_summary.merge(richness, on="plot_name", how="left")

    reg_cols = {}
    for _, row in reg_with_plots.iterrows():
        reg_cols[row.get("plot_name", "")] = {
            "transect_length_m":      row.get("transect_length_m"),
            "midpoint_displacement_m": row.get("midpoint_vs_centroid_m"),
            "ep_a_lat":  row.get("ep_a_latitude"),
            "ep_a_lon":  row.get("ep_a_longitude"),
            "ep_b_lat":  row.get("ep_b_latitude"),
            "ep_b_lon":  row.get("ep_b_longitude"),
            "mid_lat":   row.get("mid_latitude"),
            "mid_lon":   row.get("mid_longitude"),
        }

    # ── 9. Collect pending species ────────────────────────────────────────────
    pending_rows = []
    if len(pending):
        # Join to get recorder/plot info
        pending_enriched = pending.merge(
            surv_enriched[["KEY", "plot_name",
                           "field_team_specifics-recorder_label",
                           "SubmissionDate"]].rename(
                               columns={
                                   "KEY": "survey_key",
                                   "field_team_specifics-recorder_label": "recorder"
                               }),
            left_on="PARENT_KEY", right_on="survey_key", how="left"
        )
        for _, row in pending_enriched.iterrows():
            pending_rows.append({
                "run_id":             run_id,
                "survey_key":         row.get("PARENT_KEY"),
                "plot_name":          row.get("plot_name"),
                "quadrat_number":     None,
                "recorder":           row.get("recorder"),
                "submission_date":    str(row.get("SubmissionDate", "")),
                "provisional_name":   row.get("target_extra_name"),
                "validated_name":     row.get("validated_name"),
                "review_status":      row.get("review_status"),
                "new_record_reason":  row.get("new_record_reason"),
                "species_entry_mode": row.get("species_entry_mode"),
            })

    # ── 10. Persist to database ───────────────────────────────────────────────
    init_db()
    db = SessionLocal()

    try:
        # Clear previous run data
        db.query(Survey).filter(Survey.run_id == run_id).delete()
        db.query(Plot).filter(Plot.run_id == run_id).delete()
        db.query(QCFlag).filter(QCFlag.run_id == run_id).delete()
        db.query(PendingSpecies).filter(PendingSpecies.run_id == run_id).delete()
        db.commit()

        # Persist surveys
        for _, row in survey_summary.iterrows():
            key  = row["KEY"]
            n_h  = int(sflag_high.get(key, 0))
            n_m  = int(sflag_medium.get(key, 0))
            n_l  = int(sflag_low.get(key, 0))
            n_fl = n_h + n_m + n_l

            db.add(Survey(
                run_id=run_id,
                odk_key=key,
                plot_uuid=row.get("plot_selection-selected_plot_uuid"),
                plot_name=row.get("plot_name"),
                submission_date=str(row.get("SubmissionDate", "")),
                submitter=row.get("SubmitterName"),
                recorder=row.get("field_team_specifics-recorder_label"),
                start_time=str(row.get("start_dt", "")),
                end_time=str(row.get("end_dt", "")),
                duration_min=float(row["duration_min"]) if pd.notna(row.get("duration_min")) else None,
                review_state=row.get("ReviewState"),
                quadrats_completed=int(row["quadrats_completed"]) if pd.notna(row.get("quadrats_completed")) else None,
                quadrats_with_herbs=int(row["quadrats_with_herbs"]) if pd.notna(row.get("quadrats_with_herbs")) else None,
                species_occurrences=int(row["total_species_occurrences"]) if pd.notna(row.get("total_species_occurrences")) else None,
                additional_species=int(row["additional_species_entries"]) if pd.notna(row.get("additional_species_entries")) else None,
                n_flags=n_fl,
                qc_status=qc_status_from_flags(n_h, n_m, n_l),
                stratum_label=row.get("stratum_label"),
                area_label=row.get("area_label"),
            ))

        # Persist plots
        for _, row in plot_summary.iterrows():
            pname = row["plot_name"]
            rcols = reg_cols.get(pname, {})
            pfl   = flags_df[flags_df["plot_name"] == pname] if len(flags_df) else pd.DataFrame()
            n_h   = (pfl["severity"] == "HIGH").sum()   if len(pfl) else 0
            n_m   = (pfl["severity"] == "MEDIUM").sum() if len(pfl) else 0
            n_l   = (pfl["severity"] == "LOW").sum()    if len(pfl) else 0
            n_fl  = int(n_h + n_m + n_l)

            db.add(Plot(
                run_id=run_id,
                plot_uuid=row["__id"],
                plot_name=pname,
                stratum_label=row.get("stratum_label"),
                area_label=row.get("area_label"),
                is_viable=True if row.get("is_viable") == "yes" else False,
                centroid_lat=row.get("centroid_lat"),
                centroid_lon=row.get("centroid_lon"),
                geohash=row.get("geohash"),
                transect_length_m=rcols.get("transect_length_m"),
                midpoint_displacement_m=rcols.get("midpoint_displacement_m"),
                ep_a_lat=rcols.get("ep_a_lat"),
                ep_a_lon=rcols.get("ep_a_lon"),
                ep_b_lat=rcols.get("ep_b_lat"),
                ep_b_lon=rcols.get("ep_b_lon"),
                mid_lat=rcols.get("mid_lat"),
                mid_lon=rcols.get("mid_lon"),
                was_surveyed=bool(row["was_surveyed"]),
                approved_survey_count=int(row["approved_survey_count"]),
                total_species_occurrences=int(row["total_species_occurrences"]) if pd.notna(row.get("total_species_occurrences")) else None,
                quadrats_with_herbs=int(row["quadrats_with_herbs"]) if pd.notna(row.get("quadrats_with_herbs")) else None,
                total_quadrats=int(row["total_quadrats"]) if pd.notna(row.get("total_quadrats")) else None,
                n_flags=n_fl,
                qc_status=qc_status_from_flags(int(n_h), int(n_m), int(n_l)),
            ))

        # Persist flags
        if len(flags_df):
            for _, row in flags_df.iterrows():
                db.add(QCFlag(
                    run_id=run_id,
                    flag_id=row["flag_id"],
                    flag_type=row["flag_type"],
                    severity=row["severity"],
                    survey_key=row.get("survey_key"),
                    plot_name=row.get("plot_name"),
                    quadrat_number=int(row["quadrat_number"]) if pd.notna(row.get("quadrat_number")) else None,
                    field_value=row.get("field_value"),
                    expected_value=row.get("expected_value"),
                    description=row.get("description"),
                ))

        # Persist pending species
        for p in pending_rows:
            db.add(PendingSpecies(**p))

        # Update QCRun record
        n_flags_df = flags_df if len(flags_df) else pd.DataFrame(columns=["severity"])
        run_record = db.query(QCRun).filter(QCRun.id == run_id).first()
        if run_record:
            run_record.status           = "complete"
            run_record.n_surveys        = len(surv)
            run_record.n_plots          = len(plots)
            run_record.n_quadrats       = len(quad)
            run_record.n_flags_high     = int((n_flags_df["severity"] == "HIGH").sum())
            run_record.n_flags_medium   = int((n_flags_df["severity"] == "MEDIUM").sum())
            run_record.n_flags_low      = int((n_flags_df["severity"] == "LOW").sum())
            run_record.n_pending_species= len(pending_rows)
            run_record.completed_at     = datetime.utcnow()
            run_record.scorecard_params = params

        db.commit()
        log.info(f"Pipeline complete. Run ID: {run_id}")

        return {
            "run_id":           run_id,
            "status":           "complete",
            "n_surveys":        len(surv),
            "n_plots":          len(plots),
            "n_quadrats":       len(quad),
            "n_flags_high":     int((n_flags_df["severity"] == "HIGH").sum()),
            "n_flags_medium":   int((n_flags_df["severity"] == "MEDIUM").sum()),
            "n_flags_low":      int((n_flags_df["severity"] == "LOW").sum()),
            "n_pending_species": len(pending_rows),
            "completed_at":     datetime.utcnow().isoformat() + "Z",
        }

    except Exception as exc:
        db.rollback()
        run_record = db.query(QCRun).filter(QCRun.id == run_id).first()
        if run_record:
            run_record.status    = "error"
            run_record.error_msg = str(exc)
            db.commit()
        log.error(f"QC pipeline failed: {exc}", exc_info=True)
        raise

    finally:
        db.close()
