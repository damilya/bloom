"""Technogym Mywellness export (used by Stadium Kinetix) → measurements + workouts.

The GDPR export is a ZIP of four JSON files, recognised by shape rather than name:
  biometrics         [{name, measuredOn, value}]                 → body composition (Tanita scans), fitness tests, 1RMs
  indooractivities   [{phId, on, performedData{pr[], st[]}}]     → one record per machine exercise → grouped per day
  outdooractivities  [{activityName, performedDate, physicalActivityData{pr[]}}] → workouts (deduped vs Apple Watch)
  masterdata         {id, firstName, email, birthDate, ...}      → profile PII, deliberately skipped
"""
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from app.config import get_settings
from app.data import db

LOCAL_TZ = get_settings().tz

BIOMETRIC_MAP = {  # Technogym name → (metric, unit)
    "Weight": ("weight_kg", "kg"),
    "Fat mass Perc": ("body_fat_pct", "%"),
    "Fat Mass": ("fat_mass_kg", "kg"),
    "Muscle Mass": ("muscle_mass_kg", "kg"),
    "Bone Mass": ("bone_mass_kg", "kg"),
    "Total Body Water Perc": ("water_pct", "%"),
    "Visceral Fat Rating": ("visceral_fat", "level"),
    "Basal Metabolic Rate": ("bmr_kcal", "kcal"),
    "Metabolic Age": ("metabolic_age", "years"),
    "BMI": ("bmi", "kg/m²"),
    "Fitness Age": ("fitness_age", "years"),
    "VO2 Max": ("vo2max", "ml/kg/min"),
}
OUTDOOR_TYPES = {
    "walking": "walking", "swimming": "swimming", "hiking": "hiking", "elliptical": "cardio",
    "cardiovascular training": "cardio", "functional training": "strength", "strength training": "strength",
    "gym": "strength", "workout": "strength", "running": "running", "cycling": "cycling", "yoga": "yoga",
}


def kind(data: Any) -> str | None:
    """Identify a Technogym file by its shape (file names are GUID-suffixed and not reliable)."""
    if isinstance(data, dict) and {"credentialId", "firstName"} <= set(data):
        return "masterdata"
    if isinstance(data, list) and data and isinstance(data[0], dict):
        keys = set(data[0])
        if {"name", "measuredOn", "value"} <= keys:
            return "biometrics"
        if {"phId", "on", "performedData"} <= keys:
            return "indoor"
        if {"activityName", "performedDate", "physicalActivityData"} <= keys:
            return "outdoor"
    return None


def _local(ts: str) -> datetime:
    """ISO timestamp (any offset, or naive = local) → naive Brussels local time."""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.astimezone(LOCAL_TZ).replace(tzinfo=None) if dt.tzinfo else dt


def _pr(items: list[dict]) -> dict[str, float]:
    return {str(p.get("n")): p.get("v") for p in items or [] if isinstance(p.get("v"), (int, float))}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def import_biometrics(rows: list[dict]) -> dict:
    out = []
    for r in rows:
        name = str(r.get("name", ""))
        try:
            value = float(r["value"])
        except (KeyError, TypeError, ValueError):
            continue
        ts = _local(r["measuredOn"]).strftime("%Y-%m-%dT%H:%M:%S")
        if name in BIOMETRIC_MAP:
            metric, unit = BIOMETRIC_MAP[name]
        elif name.startswith("1RM "):  # strength tests: "1RM Legs", "1RM Leg Press Biostrength", ...
            metric, unit = "rm1_" + _slug(name[4:].replace("Biostrength", "")), "kg"
        else:
            continue  # segmental / balance / mobility scores: not used by the app
        out.append({"ts": ts, "source": "tanita", "metric": metric, "value": round(value, 2), "unit": unit})
    return {"kind": "biometrics", "measurements": db.upsert_measurements(out) if out else 0, "workouts": 0}


def import_indoor(rows: list[dict]) -> dict:
    """Each record is one exercise on one machine; a gym visit is all exercises on the same day."""
    days: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        days[_local(r["on"]).date().isoformat()].append(r)
    workouts = []
    for items in days.values():
        items.sort(key=lambda r: r["on"])
        pr = [_pr(r["performedData"].get("pr")) for r in items]
        sets = [s for r in items for s in r["performedData"].get("st") or []]
        set_pr = [_pr(s.get("pr")) for s in sets]
        hr = [p["AvgHr"] for p in pr if p.get("AvgHr")]
        strength = bool(sets) or any(p.get("TotalIsoWeight") for p in pr)
        duration_min = sum(p.get("Duration", 0) for p in pr) / 60
        workouts.append({
            "start_ts": _local(items[0]["on"]).strftime("%Y-%m-%dT%H:%M:%S"),
            "source": "kinetix", "type": "strength" if strength else "cardio",
            "duration_min": round(max(duration_min, 1), 1),
            "kcal": round(sum(p.get("Calories", 0) for p in pr)) or None,
            "distance_km": round(sum(p.get("HDistance", 0) for p in pr) / 1000, 2) or None,
            "avg_hr": round(sum(hr) / len(hr)) if hr else None,
            "details": {
                "name": "Kinetix gym session", "exercises": len(items), "sets": len(sets),
                "reps": int(sum(s.get("IsoReps", 0) for s in set_pr)),
                "volume_kg": round(sum(s.get("IsoReps", 0) * s.get("IsoWeight", 0) for s in set_pr)),
                "cardio_exercises": sum(1 for r in items if not r["performedData"].get("st")),
            },
        })
    return {"kind": "indoor", "measurements": 0, "workouts": db.upsert_workouts(workouts) if workouts else 0,
            "exercises": len(rows)}


def import_outdoor(rows: list[dict]) -> dict:
    """Outdoor/app-logged activities; Mywellness often mirrors Apple Watch workouts, so skip near-duplicates."""
    apple = [datetime.fromisoformat(r["start_ts"]) for r in db.rows("SELECT start_ts FROM workouts WHERE source='apple_health'")]
    workouts, dupes = [], 0
    for r in rows:
        start = _local(r["performedDate"])
        if any(abs((start - a).total_seconds()) <= 15 * 60 for a in apple):
            dupes += 1
            continue
        p = _pr(r["physicalActivityData"].get("pr"))
        name = str(r.get("activityName", "")).strip()
        workouts.append({
            "start_ts": start.strftime("%Y-%m-%dT%H:%M:%S"), "source": "kinetix",
            "type": OUTDOOR_TYPES.get(name.lower(), "other"),
            "duration_min": round(p.get("Duration", 0) / 60, 1) or None,
            "end_ts": (start + timedelta(seconds=p.get("Duration", 0))).strftime("%Y-%m-%dT%H:%M:%S"),
            "kcal": round(p["Calories"]) if p.get("Calories") else None,
            "distance_km": round(p["HDistance"] / 1000, 2) if p.get("HDistance") else None,
            "avg_hr": round(p["AvgHr"]) if p.get("AvgHr") else None,
            "details": {"name": name, "logged_in": "Mywellness"},
        })
    return {"kind": "outdoor", "measurements": 0, "workouts": db.upsert_workouts(workouts) if workouts else 0,
            "skipped_duplicates": dupes}


def import_technogym(data: Any) -> dict | None:
    k = kind(data)
    if k is None:
        return None
    if k == "masterdata":
        return {"kind": "masterdata", "measurements": 0, "workouts": 0, "note": "profile data skipped (not needed)"}
    result = {"biometrics": import_biometrics, "indoor": import_indoor, "outdoor": import_outdoor}[k](data)
    from app.ingest.dedupe import dedupe_all

    result["deduplicated"] = dedupe_all()
    return result
