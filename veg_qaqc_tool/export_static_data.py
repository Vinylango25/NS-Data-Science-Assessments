"""
export_static_data.py
---------------------
Runs the QC pipeline against the real vegetation data and exports
everything to JSON files in frontend/public/data/.

These JSON files power the static Vercel demo — no backend needed.
Run once: python export_static_data.py
"""
import sys, json, os, math, re
from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
BACKEND    = SCRIPT_DIR / "backend"
NS_DIR     = SCRIPT_DIR.parent.parent / "NS"   # C:\Users\GCA17695\Desktop\NS
ALT_NS     = SCRIPT_DIR.parent / "NS"
OUT_DIR    = SCRIPT_DIR / "frontend" / "public" / "data"

sys.path.insert(0, str(BACKEND))
os.chdir(str(BACKEND))

import pandas as pd
import numpy as np

# ── Load data ──────────────────────────────────────────────────────────────────
# Try Natural State folder first, fall back to NS
def find_data():
    candidates = [
        Path("C:/Users/GCA17695/Desktop/Natural State/Data Vegetation"),
        Path("C:/Users/GCA17695/Desktop/NS/Data Vegetation"),
    ]
    for c in candidates:
        if (c / "ODK Data Exports" / "herbaceous_veg_survey.csv").exists():
            return c
    raise FileNotFoundError("Data Vegetation folder not found")

data_dir = find_data()
odk_dir  = data_dir / "ODK Data Exports"
ent_dir  = data_dir / "Entity lists"

print(f"Loading data from: {data_dir}")

reg    = pd.read_csv(odk_dir / "register_vegetation_plots.csv")
surv   = pd.read_csv(odk_dir / "herbaceous_veg_survey.csv")
quad   = pd.read_csv(odk_dir / "herbaceous_veg_survey-quadrat_repeat.csv")
addsp  = pd.read_csv(odk_dir / "herbaceous_veg_survey-additional_species_repeat.csv")
plots  = pd.read_csv(ent_dir / "vegplots.csv")
sp_extra = pd.read_csv(ent_dir / "species_extra.csv")

print(f"  surveys:{len(surv)}  quadrats:{len(quad)}  addsp:{len(addsp)}  plots:{len(plots)}")

# ── Helpers ────────────────────────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6_371_000
    p = math.pi / 180
    dlat = (lat2 - lat1) * p
    dlon = (lon2 - lon1) * p
    a = math.sin(dlat/2)**2 + math.cos(lat1*p)*math.cos(lat2*p)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def safe_hav(r, la1, lo1, la2, lo2):
    vals = [r.get(la1), r.get(lo1), r.get(la2), r.get(lo2)]
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in vals):
        return None
    return round(haversine(float(vals[0]), float(vals[1]), float(vals[2]), float(vals[3])), 1)

def parse_geom(g):
    if pd.isna(g): return None, None
    parts = str(g).strip().split()
    try: return float(parts[0]), float(parts[1])
    except: return None, None

def safe_float(v):
    try:
        f = float(v)
        return None if math.isnan(f) else round(f, 4)
    except: return None

def safe_int(v):
    try:
        f = float(v)
        return None if math.isnan(f) else int(f)
    except: return None

VALID_CANON = re.compile(r"^([A-Z][a-z]+_[a-z]|[Uu]nknown_|herb_\d|wood_\d)")

# ── Parse & enrich ─────────────────────────────────────────────────────────────
plots[["centroid_lat","centroid_lon"]] = pd.DataFrame(
    plots["geometry"].apply(parse_geom).tolist(), index=plots.index
)

surv = surv.copy()
surv["start_dt"] = pd.to_datetime(surv["survey_begin-start_time"], errors="coerce")
surv["end_dt"]   = pd.to_datetime(surv["survey_end-end_time"],     errors="coerce")
surv["duration_min"] = (surv["end_dt"] - surv["start_dt"]).dt.total_seconds() / 60

reg = reg.copy()
for prefix, short in [
    ("plot_metadata-collect_points-endpoint_a-location_endpoint_a-", "ep_a_"),
    ("plot_metadata-collect_points-midpoint-location_midpoint-",     "mid_"),
    ("plot_metadata-collect_points-endpoint_b-location_endpoint_b-", "ep_b_"),
]:
    for coord in ["Latitude","Longitude"]:
        src = prefix + coord
        dst = short + coord.lower()
        if src in reg.columns:
            reg[dst] = pd.to_numeric(reg[src], errors="coerce")

quad = quad.copy()
for coord in ["Latitude","Longitude","Accuracy"]:
    src = f"location_quadrat-{coord}"
    if src in quad.columns:
        quad[f"q_{coord.lower()}"] = pd.to_numeric(quad[src], errors="coerce")

reg["transect_length_m"] = reg.apply(
    lambda r: safe_hav(r,"ep_a_latitude","ep_a_longitude","ep_b_latitude","ep_b_longitude"), axis=1
)

reg_with_plots = reg.merge(
    plots[["plot_uuid","plot_name","centroid_lat","centroid_lon","is_viable","stratum_label","geohash"]],
    left_on="plot_selection-selected_plot_uuid", right_on="plot_uuid", how="left"
)
reg_with_plots["midpoint_vs_centroid_m"] = reg_with_plots.apply(
    lambda r: safe_hav(r,"mid_latitude","mid_longitude","centroid_lat","centroid_lon"), axis=1
)

surv_enriched = surv.merge(
    plots[["__id","plot_name","centroid_lat","centroid_lon","is_viable","stratum_label","area_label"]].rename(columns={"__id":"plot_uuid"}),
    left_on="plot_selection-selected_plot_uuid", right_on="plot_uuid", how="left"
)

quad_enriched = quad.merge(
    surv_enriched[["KEY","plot_name","stratum_label","start_dt","plot_selection-selected_plot_uuid"]],
    left_on="PARENT_KEY", right_on="KEY", how="left"
)
quad_enriched = quad_enriched.rename(columns={"KEY_x":"KEY","KEY_y":"survey_KEY"})

# ── QC Checks ──────────────────────────────────────────────────────────────────
flags = []
def add_flag(flag_id, flag_type, severity, survey_key, plot_name, quadrat_number,
             field_value, expected_value, description):
    flags.append({
        "flag_id": flag_id, "flag_type": flag_type, "severity": severity,
        "survey_key": str(survey_key) if survey_key else None,
        "plot_name": str(plot_name) if plot_name else None,
        "quadrat_number": quadrat_number,
        "field_value": str(field_value) if field_value is not None else None,
        "expected_value": str(expected_value) if expected_value is not None else None,
        "description": description,
    })

rejected = surv[surv["ReviewState"] == "rejected"]
for _, row in rejected.iterrows():
    add_flag("S1","survey_rejected","HIGH", row["KEY"], row.get("plot_name"), None,
             "rejected","approved", f"Survey by {row.get('SubmitterName','?')} on {str(row.get('SubmissionDate','?'))[:10]} is rejected.")

dup = surv[surv["plot_selection-selected_plot_uuid"].duplicated(keep=False)]
for uuid, grp in dup.groupby("plot_selection-selected_plot_uuid"):
    pname = surv_enriched[surv_enriched["plot_selection-selected_plot_uuid"]==uuid]["plot_name"].iloc[0] if len(surv_enriched[surv_enriched["plot_selection-selected_plot_uuid"]==uuid]) else uuid
    add_flag("S2","duplicate_survey","HIGH", "; ".join(grp["KEY"].tolist()), pname, None,
             f"{len(grp)} submissions","1 per plot", f"Plot '{pname}' has {len(grp)} survey submissions.")

for _, row in surv_enriched[surv_enriched["duration_min"] > 180].iterrows():
    add_flag("S3","survey_duration_outlier","MEDIUM", row["KEY"], row.get("plot_name"), None,
             f"{row['duration_min']:.1f} min","<180 min", f"Survey ran {row['duration_min']:.0f} min — may be a delayed submission.")

reg_uuids  = set(plots["__id"].tolist())
surv_uuids = set(surv["plot_selection-selected_plot_uuid"].tolist())
for u in (reg_uuids - surv_uuids):
    r = plots[plots["__id"]==u]
    if len(r) and r.iloc[0]["is_viable"] == "yes":
        add_flag("P1","plot_not_surveyed","MEDIUM", None, r.iloc[0]["plot_name"], None,
                 "no survey","survey expected", f"Plot '{r.iloc[0]['plot_name']}' is viable but has no survey.")

nv_ids = set(plots[plots["is_viable"]=="no"]["__id"].tolist())
for _, row in surv_enriched[surv_enriched["plot_selection-selected_plot_uuid"].isin(nv_ids)].iterrows():
    add_flag("P2","non_viable_plot_surveyed","HIGH", row["KEY"], row.get("plot_name"), None,
             "is_viable=no","should not be surveyed", f"Plot '{row.get('plot_name')}' is non-viable but has a survey.")

for _, row in reg_with_plots.iterrows():
    tlen  = row["transect_length_m"]
    pname = row.get("plot_name", "?")
    if tlen is None or (isinstance(tlen, float) and math.isnan(tlen)):
        add_flag("P3","transect_length_missing","MEDIUM", row["KEY"], pname, None,
                 "no GPS","~50m","Cannot compute transect length — endpoint GPS missing.")
    elif tlen < 40:
        add_flag("P3","transect_too_short","MEDIUM", row["KEY"], pname, None,
                 f"{tlen:.1f}m","40-60m", f"Transect is {tlen:.1f}m — below expected 50m.")
    elif tlen > 60:
        add_flag("P3","transect_too_long","LOW", row["KEY"], pname, None,
                 f"{tlen:.1f}m","40-60m", f"Transect is {tlen:.1f}m — slightly over expected 50m (GPS noise likely).")

if "q_accuracy" in quad_enriched.columns:
    for _, row in quad_enriched[quad_enriched["q_accuracy"] > 5].iterrows():
        add_flag("Q1","quadrat_gps_poor_accuracy","LOW", row["PARENT_KEY"], row.get("plot_name"),
                 row.get("quadrat_number"), f"{row['q_accuracy']:.1f}m","<=5m",
                 f"Quadrat {row.get('quadrat_number')} GPS accuracy {row['q_accuracy']:.1f}m.")

herb_yes = quad_enriched[quad_enriched["herbs_present"] == "yes"]
no_sp    = herb_yes[herb_yes["herb_species-selected_herb_species_uuids"].isna() &
                    (herb_yes["additional_species_present"] != "yes")]
for _, row in no_sp.iterrows():
    add_flag("Q2","herbs_present_no_species","HIGH", row["PARENT_KEY"], row.get("plot_name"),
             row.get("quadrat_number"), "herbs=yes, 0 species",">=1 species",
             f"Quadrat {row.get('quadrat_number')} has herbs but no species recorded.")

for _, row in addsp[addsp["validated_name"].str.endswith(" ", na=False)].iterrows():
    add_flag("Q4","canonical_trailing_whitespace","LOW", row["PARENT_KEY"], None, None,
             repr(row["validated_name"]),"no trailing spaces", f"Name has trailing whitespace.")

bad = addsp[addsp["new_missing_canonical"].notna() &
            ~addsp["new_missing_canonical"].str.strip().str.match(VALID_CANON).fillna(False)]
for _, row in bad.iterrows():
    add_flag("Q5","non_standard_canonical","LOW", row["PARENT_KEY"], None, None,
             str(row["new_missing_canonical"]),"Genus_species", f"Not in Genus_species format.")

pending = addsp[addsp["review_status"] == "pending"]
for pk, grp in pending.groupby("PARENT_KEY"):
    r = surv_enriched[surv_enriched["KEY"] == pk]
    pname = r["plot_name"].iloc[0] if len(r) else pk
    add_flag("R1","species_pending_review","MEDIUM", pk, pname, None,
             f"{len(grp)} pending","all identified",
             f"{len(grp)} additional species pending taxonomic review.")

flags_df = pd.DataFrame(flags)
n_high   = int((flags_df["severity"]=="HIGH").sum())
n_medium = int((flags_df["severity"]=="MEDIUM").sum())
n_low    = int((flags_df["severity"]=="LOW").sum())
print(f"Flags: {len(flags_df)} total  HIGH:{n_high}  MEDIUM:{n_medium}  LOW:{n_low}")

# ── Build survey JSON ──────────────────────────────────────────────────────────
sp_counts = quad_enriched.groupby("PARENT_KEY").agg(
    quadrats_completed=("quadrat_number","count"),
    quadrats_with_herbs=("herbs_present", lambda x:(x=="yes").sum()),
    species_occurrences=("herb_species-count_herb_species",
                         lambda x: pd.to_numeric(x,errors="coerce").sum())
).reset_index().rename(columns={"PARENT_KEY":"KEY"})

addsp_counts = addsp.groupby("PARENT_KEY").size().reset_index(name="additional_species").rename(columns={"PARENT_KEY":"KEY"})
sm = surv_enriched.merge(sp_counts, on="KEY", how="left").merge(addsp_counts, on="KEY", how="left")
sm["additional_species"] = sm["additional_species"].fillna(0).astype(int)

def flag_counts(key_col, key_val):
    if len(flags_df) == 0: return 0,0,0
    sub = flags_df[flags_df[key_col]==key_val]
    return int((sub["severity"]=="HIGH").sum()), int((sub["severity"]=="MEDIUM").sum()), int((sub["severity"]=="LOW").sum())

def qc_st(h,m,l):
    return "fail" if h>0 else ("warning" if m>0 or l>0 else "pass")

surveys_json = []
for _, row in sm.iterrows():
    key = row["KEY"]
    h,m,l = flag_counts("survey_key", key)
    sflags = [f for f in flags if f.get("survey_key") and key in (f.get("survey_key") or "")]
    surveys_json.append({
        "odk_key":            key,
        "plot_name":          row.get("plot_name"),
        "submission_date":    str(row.get("SubmissionDate",""))[:10],
        "submitter":          row.get("SubmitterName"),
        "recorder":           row.get("field_team_specifics-recorder_label"),
        "duration_min":       safe_float(row.get("duration_min")),
        "review_state":       row.get("ReviewState"),
        "quadrats_completed": safe_int(row.get("quadrats_completed")),
        "quadrats_with_herbs":safe_int(row.get("quadrats_with_herbs")),
        "species_occurrences":safe_int(row.get("species_occurrences")),
        "additional_species": int(row["additional_species"]),
        "stratum_label":      row.get("stratum_label"),
        "area_label":         row.get("area_label"),
        "n_flags": h+m+l, "n_flags_high":h, "n_flags_medium":m, "n_flags_low":l,
        "qc_status": qc_st(h,m,l),
        "flags": sflags,
    })

# ── Build plot JSON ────────────────────────────────────────────────────────────
plot_summary = plots[["__id","plot_name","stratum_label","area_label","is_viable","centroid_lat","centroid_lon","geohash"]].copy()
plot_summary["was_surveyed"] = plot_summary["__id"].isin(surv_uuids)
approved = surv[surv["ReviewState"]!="rejected"]
ap = approved.groupby("plot_selection-selected_plot_uuid").size().reset_index(name="approved_survey_count").rename(columns={"plot_selection-selected_plot_uuid":"__id"})
plot_summary = plot_summary.merge(ap, on="__id", how="left")
plot_summary["approved_survey_count"] = plot_summary["approved_survey_count"].fillna(0).astype(int)

approved_keys = set(approved["KEY"].tolist())
aq = quad_enriched[quad_enriched["PARENT_KEY"].isin(approved_keys)]
richness = aq.groupby("plot_name").agg(
    total_species_occurrences=("herb_species-count_herb_species", lambda x: pd.to_numeric(x,errors="coerce").sum()),
    quadrats_with_herbs=("herbs_present", lambda x:(x=="yes").sum()),
    total_quadrats=("quadrat_number","count")
).reset_index()
plot_summary = plot_summary.merge(richness, on="plot_name", how="left")

reg_map = {}
for _, row in reg_with_plots.iterrows():
    pname = row.get("plot_name","")
    if pname:
        reg_map[pname] = {
            "transect_length_m":       safe_float(row.get("transect_length_m")),
            "midpoint_displacement_m": safe_float(row.get("midpoint_vs_centroid_m")),
            "ep_a_lat": safe_float(row.get("ep_a_latitude")),
            "ep_a_lon": safe_float(row.get("ep_a_longitude")),
            "ep_b_lat": safe_float(row.get("ep_b_latitude")),
            "ep_b_lon": safe_float(row.get("ep_b_longitude")),
            "mid_lat":  safe_float(row.get("mid_latitude")),
            "mid_lon":  safe_float(row.get("mid_longitude")),
        }

plots_json = []
for _, row in plot_summary.iterrows():
    pname = row["plot_name"]
    rc = reg_map.get(pname, {})
    h,m,l = flag_counts("plot_name", pname)
    survey_rows = [s for s in surveys_json if s.get("plot_name")==pname]
    plots_json.append({
        "plot_uuid":    row["__id"],
        "plot_name":    pname,
        "stratum_label":row.get("stratum_label"),
        "area_label":   row.get("area_label"),
        "is_viable":    row.get("is_viable")=="yes",
        "centroid_lat": safe_float(row.get("centroid_lat")),
        "centroid_lon": safe_float(row.get("centroid_lon")),
        "geohash":      row.get("geohash"),
        "was_surveyed": bool(row["was_surveyed"]),
        "approved_survey_count": int(row["approved_survey_count"]),
        "total_species_occurrences": safe_int(row.get("total_species_occurrences")),
        "quadrats_with_herbs": safe_int(row.get("quadrats_with_herbs")),
        "total_quadrats": safe_int(row.get("total_quadrats")),
        **rc,
        "n_flags": h+m+l,
        "qc_status": qc_st(h,m,l),
        "flags": [f for f in flags if f.get("plot_name")==pname],
        "surveys": survey_rows,
    })

# ── Build pending species JSON ─────────────────────────────────────────────────
pending_json = []
for _, row in pending.iterrows():
    sr = surv_enriched[surv_enriched["KEY"]==row["PARENT_KEY"]]
    pending_json.append({
        "survey_key":        row["PARENT_KEY"],
        "plot_name":         sr.iloc[0]["plot_name"] if len(sr) else None,
        "submission_date":   str(sr.iloc[0]["SubmissionDate"])[:10] if len(sr) else None,
        "recorder":          sr.iloc[0].get("field_team_specifics-recorder_label") if len(sr) else None,
        "provisional_name":  row.get("target_extra_name"),
        "validated_name":    row.get("validated_name"),
        "review_status":     row.get("review_status"),
        "new_record_reason": row.get("new_record_reason"),
        "species_entry_mode":row.get("species_entry_mode"),
    })

# ── Dashboard JSON ─────────────────────────────────────────────────────────────
n_q = int(len(quad))
n_h = int((quad["herbs_present"]=="yes").sum())
ft  = flags_df.groupby(["flag_type","severity"]).size().reset_index(name="n") if len(flags_df) else pd.DataFrame(columns=["flag_type","severity","n"])

dashboard = {
    "run_at": datetime.utcnow().isoformat()+"Z",
    "status": "complete",
    "data_source": "csv",
    "n_plots_registered": int(len(plots)),
    "n_plots_viable":     int((plots["is_viable"]=="yes").sum()),
    "n_plots_surveyed":   int(plot_summary["was_surveyed"].sum()),
    "n_surveys_total":    int(len(surv)),
    "n_surveys_approved": int((surv["ReviewState"]!="rejected").sum()),
    "n_surveys_rejected": int((surv["ReviewState"]=="rejected").sum()),
    "n_quadrats":         n_q,
    "pct_quadrats_with_herbs": round(100*n_h/n_q,1) if n_q else 0,
    "n_flags_high":   n_high,
    "n_flags_medium": n_medium,
    "n_flags_low":    n_low,
    "n_pending_species": len(pending_json),
    "flag_type_summary": [{"flag_type":r["flag_type"],"severity":r["severity"],"n":int(r["n"])} for _,r in ft.iterrows()],
}

# ── Write JSON ─────────────────────────────────────────────────────────────────
import math

def clean(obj):
    """Recursively replace float NaN/Inf with None so json.dumps produces valid JSON."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    return obj

os.chdir(str(SCRIPT_DIR))
out = Path("frontend/public/data")
out.mkdir(parents=True, exist_ok=True)

(out / "dashboard.json").write_text(json.dumps(clean(dashboard), indent=2), encoding="utf-8")
(out / "surveys.json").write_text(json.dumps(clean(surveys_json), indent=2), encoding="utf-8")
(out / "plots.json").write_text(json.dumps(clean(plots_json), indent=2), encoding="utf-8")
(out / "flags.json").write_text(json.dumps(clean(flags), indent=2), encoding="utf-8")
(out / "species_queue.json").write_text(json.dumps(clean(pending_json), indent=2), encoding="utf-8")

print(f"\nWritten to {out}:")
for fn in sorted(out.iterdir()):
    print(f"  {fn.name}: {fn.stat().st_size:,} bytes")
print("Done.")
