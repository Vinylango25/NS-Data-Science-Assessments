"""
app/narrative/groq_narrative.py
--------------------------------
AI narrative generation using Groq.

Generates plain-English QC summaries per survey from the flag data.
Falls back gracefully if GROQ_API_KEY is not set or Groq is unavailable.
"""
import logging
from datetime import datetime
from typing import Optional

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models import QCFlag, Survey, Narrative

log = logging.getLogger(__name__)


def _build_prompt(survey_data: dict, flags: list[dict]) -> str:
    """Build the prompt for Groq from survey data and its flags."""
    plot       = survey_data.get("plot_name", "unknown")
    recorder   = survey_data.get("recorder", "unknown")
    date       = survey_data.get("submission_date", "")[:10]
    duration   = survey_data.get("duration_min")
    quadrats   = survey_data.get("quadrats_completed", 20)
    herbs      = survey_data.get("quadrats_with_herbs", 0)
    species    = survey_data.get("species_occurrences", 0)
    addsp      = survey_data.get("additional_species", 0)
    review     = survey_data.get("review_state", "")

    high_flags   = [f for f in flags if f["severity"] == "HIGH"]
    medium_flags = [f for f in flags if f["severity"] == "MEDIUM"]
    low_flags    = [f for f in flags if f["severity"] == "LOW"]

    flag_text = ""
    if flags:
        lines = []
        for f in flags:
            lines.append(
                f"  [{f['severity']}] {f['flag_type']}: {f['description']}"
            )
        flag_text = "\n".join(lines)
    else:
        flag_text = "  None — survey passed all QC checks."

    prompt = f"""You are a data quality analyst for Natural State, a biodiversity analytics company.
You are reviewing herbaceous vegetation survey data from a savanna monitoring project in Lewa, Kenya.

Write a concise, professional QC summary for the following survey.
Be direct. Use plain English. No bullet points — write in short paragraphs (2-4 sentences each).
Focus on: what was found, what issues need action, and what can be ignored.
Do not repeat the raw numbers verbatim — interpret them.

SURVEY DETAILS:
- Plot: {plot}
- Recorder: {recorder}
- Date: {date}
- Duration: {f"{duration:.0f} min" if duration else "unknown"}
- Review state: {review or "approved"}
- Quadrats completed: {quadrats}/20
- Quadrats with herbs: {herbs}/20
- Species occurrences: {species}
- Additional species entries: {addsp}

QC FLAGS ({len(flags)} total — {len(high_flags)} HIGH, {len(medium_flags)} MEDIUM, {len(low_flags)} LOW):
{flag_text}

Write the QC summary now (3-5 sentences, plain prose):"""

    return prompt


def generate_narrative(
    survey_key: str,
    run_id: int,
    survey_data: Optional[dict] = None,
) -> str:
    """
    Generate an AI narrative for a survey using Groq.

    Parameters
    ----------
    survey_key  : ODK KEY of the survey
    run_id      : QC run ID (to look up flags)
    survey_data : optional pre-loaded survey dict; fetched from DB if None

    Returns
    -------
    Narrative text (str)
    """
    if not settings.NARRATIVE_ENABLED or not settings.GROQ_API_KEY:
        return _fallback_narrative(survey_key, run_id, survey_data)

    db = SessionLocal()
    try:
        # Load survey if not provided
        if survey_data is None:
            row = db.query(Survey).filter(
                Survey.odk_key == survey_key,
                Survey.run_id == run_id
            ).first()
            if not row:
                return "Survey not found."
            survey_data = {
                "plot_name":          row.plot_name,
                "recorder":           row.recorder,
                "submission_date":    row.submission_date,
                "duration_min":       row.duration_min,
                "review_state":       row.review_state,
                "quadrats_completed": row.quadrats_completed,
                "quadrats_with_herbs": row.quadrats_with_herbs,
                "species_occurrences": row.species_occurrences,
                "additional_species": row.additional_species,
            }

        # Load flags for this survey
        flag_rows = db.query(QCFlag).filter(
            QCFlag.run_id == run_id,
            QCFlag.survey_key == survey_key
        ).all()

        flags = [
            {
                "severity":    f.severity,
                "flag_type":   f.flag_type,
                "description": f.description,
            }
            for f in flag_rows
        ]

        prompt = _build_prompt(survey_data, flags)

        # Call Groq
        from groq import Groq
        client  = Groq(api_key=settings.GROQ_API_KEY)
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.3,
        )
        text = response.choices[0].message.content.strip()

        # Persist narrative
        existing = db.query(Narrative).filter(
            Narrative.survey_key == survey_key,
            Narrative.run_id == run_id
        ).first()

        if existing:
            existing.narrative    = text
            existing.generated_at = datetime.utcnow()
        else:
            db.add(Narrative(
                run_id=run_id,
                survey_key=survey_key,
                plot_name=survey_data.get("plot_name"),
                narrative=text,
                model=settings.GROQ_MODEL,
            ))
        db.commit()

        log.info(f"Narrative generated for {survey_data.get('plot_name')} (run {run_id})")
        return text

    except Exception as exc:
        log.error(f"Narrative generation failed: {exc}")
        return _fallback_narrative(survey_key, run_id, survey_data)

    finally:
        db.close()


def generate_all_narratives(run_id: int) -> int:
    """Generate narratives for all surveys in a run. Returns count generated."""
    db = SessionLocal()
    try:
        surveys = db.query(Survey).filter(Survey.run_id == run_id).all()
        count   = 0
        for s in surveys:
            try:
                generate_narrative(s.odk_key, run_id)
                count += 1
            except Exception as exc:
                log.warning(f"Skipped narrative for {s.plot_name}: {exc}")
        log.info(f"Generated {count}/{len(surveys)} narratives for run {run_id}")
        return count
    finally:
        db.close()


def _fallback_narrative(
    survey_key: str,
    run_id: int,
    survey_data: Optional[dict] = None,
) -> str:
    """
    Rule-based narrative when Groq is unavailable.
    Generates a readable summary from the flag data alone.
    """
    db = SessionLocal()
    try:
        if survey_data is None:
            row = db.query(Survey).filter(
                Survey.odk_key == survey_key,
                Survey.run_id  == run_id
            ).first()
            if not row:
                return "Survey data not available."
            survey_data = {
                "plot_name":          row.plot_name,
                "recorder":           row.recorder,
                "review_state":       row.review_state,
                "quadrats_completed": row.quadrats_completed,
                "quadrats_with_herbs": row.quadrats_with_herbs,
                "species_occurrences": row.species_occurrences,
                "additional_species": row.additional_species,
                "duration_min":       row.duration_min,
                "n_flags":            row.n_flags,
                "qc_status":          row.qc_status,
            }

        flag_rows = db.query(QCFlag).filter(
            QCFlag.run_id    == run_id,
            QCFlag.survey_key == survey_key
        ).all()

        plot     = survey_data.get("plot_name", "this plot")
        recorder = survey_data.get("recorder", "the field team")
        quadrats = survey_data.get("quadrats_completed") or 20
        herbs    = survey_data.get("quadrats_with_herbs") or 0
        species  = survey_data.get("species_occurrences") or 0
        addsp    = survey_data.get("additional_species") or 0
        n_flags  = len(flag_rows)

        high   = [f for f in flag_rows if f.severity == "HIGH"]
        medium = [f for f in flag_rows if f.severity == "MEDIUM"]
        low    = [f for f in flag_rows if f.severity == "LOW"]

        parts = []

        parts.append(
            f"Survey of {plot} by {recorder} completed {quadrats}/20 quadrats, "
            f"with herbaceous species present in {herbs} quadrats "
            f"({species} total species occurrences)."
        )

        if addsp > 0:
            parts.append(
                f"{addsp} additional species entries were recorded outside the pre-loaded list"
                + (" and are awaiting taxonomic review." if any(f.flag_type == "species_pending_review" for f in flag_rows) else ".")
            )

        if not flag_rows:
            parts.append("This survey passed all QC checks with no issues identified.")
        else:
            if high:
                issues = "; ".join(f.description for f in high[:3])
                parts.append(
                    f"{len(high)} HIGH-severity issue(s) require immediate attention: {issues}"
                )
            if medium:
                parts.append(
                    f"{len(medium)} MEDIUM-severity flag(s) warrant investigation before analysis."
                )
            if low and not high and not medium:
                parts.append(
                    f"{len(low)} minor formatting issue(s) flagged — data values are unaffected."
                )

        return " ".join(parts)

    finally:
        db.close()
