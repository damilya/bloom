"""Apple Health `export.zip` / `export.xml` parser.

The export can be hundreds of MB, so we stream it with iterparse and clear elements as we go.
Extracted: menstrual flow (cycle tracking), workouts (Apple Watch), resting HR, HRV, sleep, steps,
and body mass / body fat when they were NOT written by Withings (Withings syncs into Apple Health,
and we already pull Withings directly — this avoids double counting).
"""
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import IO
from xml.etree.ElementTree import iterparse

from app.config import get_settings
from app.data import db

# iOS ≤ 17 wrote "MenstrualFlow*" values; newer iOS writes "VaginalBleeding*" for the same record type.
# "None" means the user logged "no flow" that day, so it is not a period day and is skipped.
FLOW = {
    f"HKCategoryValue{prefix}{level}": level.lower()
    for prefix in ("MenstrualFlow", "VaginalBleeding")
    for level in ("Light", "Medium", "Heavy", "Unspecified")
}
CYCLE_HISTORY_DAYS = 3 * 365  # cycles are sparse (~12/yr) and irregular with PCOS: keep more history for stats
QUANTITY = {
    "HKQuantityTypeIdentifierRestingHeartRate": ("resting_hr", "bpm", "mean"),
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": ("hrv_ms", "ms", "mean"),
    "HKQuantityTypeIdentifierStepCount": ("steps", "steps", "sum"),
    "HKQuantityTypeIdentifierBodyMass": ("weight_kg", "kg", "mean"),
    "HKQuantityTypeIdentifierBodyFatPercentage": ("body_fat_pct", "%", "mean"),
}
ASLEEP = {"HKCategoryValueSleepAnalysisAsleep", "HKCategoryValueSleepAnalysisAsleepCore",
          "HKCategoryValueSleepAnalysisAsleepDeep", "HKCategoryValueSleepAnalysisAsleepREM",
          "HKCategoryValueSleepAnalysisAsleepUnspecified"}
WORKOUT_TYPES = {
    "TraditionalStrengthTraining": "strength", "FunctionalStrengthTraining": "strength",
    "Running": "running", "Walking": "walking", "Cycling": "cycling", "Yoga": "yoga",
    "HighIntensityIntervalTraining": "hiit", "Pilates": "pilates", "Swimming": "swimming",
    "Elliptical": "cardio", "MixedCardio": "cardio", "CoreTraining": "core", "Dance": "dance",
    "Hiking": "hiking", "Rowing": "rowing", "Cooldown": "mobility", "Flexibility": "mobility",
}
SKIP_SOURCES = ("withings", "health mate")


LOCAL_TZ = get_settings().tz


def _dt(s: str) -> datetime:
    """Apple writes timestamps in the phone's timezone *at export time* (e.g. +0500 after travelling);
    normalise to the user's home timezone so days and times line up with Withings/Kinetix data."""
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z").astimezone(LOCAL_TZ)


def _open_export(path: Path) -> IO[bytes]:
    if path.suffix == ".zip":
        zf = zipfile.ZipFile(path)
        name = next(n for n in zf.namelist() if n.endswith("export.xml") and "cda" not in n.lower())
        return zf.open(name)
    return open(path, "rb")


def parse_apple_health(path: str | Path, days: int = 365) -> dict:
    path = Path(path)
    cutoff = datetime.now().astimezone() - timedelta(days=days)
    cycle_cutoff = datetime.now().astimezone() - timedelta(days=max(days, CYCLE_HISTORY_DAYS))
    flow_days: dict[str, str] = {}
    daily: dict[tuple[str, str], list[float]] = defaultdict(list)
    sleep: dict[str, float] = defaultdict(float)
    workouts: list[dict] = []

    with _open_export(path) as fh:
        for _, el in iterparse(fh, events=("end",)):
            tag = el.tag
            if tag == "Record":
                t = el.get("type", "")
                start = el.get("startDate")
                is_flow = t == "HKCategoryTypeIdentifierMenstrualFlow"
                if not start or _dt(start) < (cycle_cutoff if is_flow else cutoff):
                    el.clear()
                    continue
                day = _dt(start).date().isoformat()
                if is_flow:
                    f = FLOW.get(el.get("value", ""))
                    if f:
                        flow_days[day] = f
                elif t == "HKCategoryTypeIdentifierSleepAnalysis" and el.get("value") in ASLEEP:
                    end = _dt(el.get("endDate"))
                    sleep[end.date().isoformat()] += (end - _dt(start)).total_seconds() / 3600
                elif t in QUANTITY:
                    src = (el.get("sourceName") or "").lower()
                    metric = QUANTITY[t][0]
                    if metric in ("weight_kg", "body_fat_pct") and any(s in src for s in SKIP_SOURCES):
                        el.clear()
                        continue
                    try:
                        v = float(el.get("value"))
                    except (TypeError, ValueError):
                        el.clear()
                        continue
                    if metric == "body_fat_pct" and v <= 1:
                        v *= 100
                    if metric == "weight_kg" and el.get("unit") == "lb":
                        v *= 0.453592
                    daily[(day, metric)].append(v)
                el.clear()
            elif tag == "Workout":
                start = el.get("startDate")
                if start and _dt(start) >= cutoff:
                    workouts.append(_workout(el))
                el.clear()

    measurements = []
    for (day, metric), vals in daily.items():
        agg = next(a for m, _, a in QUANTITY.values() if m == metric)
        value = sum(vals) if agg == "sum" else sum(vals) / len(vals)
        unit = next(u for m, u, _ in QUANTITY.values() if m == metric)
        measurements.append({"ts": f"{day}T08:00:00", "source": "apple_health", "metric": metric,
                             "value": round(value, 2), "unit": unit})
    for day, hours in sleep.items():
        measurements.append({"ts": f"{day}T08:00:00", "source": "apple_health", "metric": "sleep_hours",
                             "value": round(min(hours, 14), 2), "unit": "h"})
    cycle = [{"date": d, "flow": f, "source": "apple_health"} for d, f in flow_days.items()]

    result = {
        "measurements": db.upsert_measurements(measurements),
        "workouts": db.upsert_workouts(workouts),
        "cycle_days": db.upsert_cycle_days(cycle),
    }
    from app.ingest.dedupe import dedupe_all

    result["deduplicated"] = dedupe_all()
    return result


def _workout(el) -> dict:
    raw = el.get("workoutActivityType", "").replace("HKWorkoutActivityType", "")
    start, end = _dt(el.get("startDate")), _dt(el.get("endDate"))
    duration = float(el.get("duration") or (end - start).total_seconds() / 60)
    if el.get("durationUnit") == "s":
        duration /= 60
    kcal = float(el.get("totalEnergyBurned")) if el.get("totalEnergyBurned") else None
    dist = float(el.get("totalDistance")) if el.get("totalDistance") else None
    avg_hr = None
    for st in el.findall("WorkoutStatistics"):
        t = st.get("type", "")
        if t.endswith("ActiveEnergyBurned") and st.get("sum"):
            kcal = float(st.get("sum"))
        elif "Distance" in t and st.get("sum"):
            dist = float(st.get("sum")) * (1.609 if st.get("unit") == "mi" else 1)
        elif t.endswith("HeartRate") and st.get("average"):
            avg_hr = float(st.get("average"))
    return {
        "start_ts": start.strftime("%Y-%m-%dT%H:%M:%S"), "end_ts": end.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "apple_health", "type": WORKOUT_TYPES.get(raw, raw.lower() or "other"),
        "duration_min": round(duration, 1), "kcal": round(kcal) if kcal else None,
        "distance_km": round(dist, 2) if dist else None, "avg_hr": round(avg_hr) if avg_hr else None,
        "details": {"apple_type": raw},
    }
