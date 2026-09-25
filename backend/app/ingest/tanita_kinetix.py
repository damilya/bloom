"""Stadium Kinetix (Brussels) + Tanita JSON export importer.

The exact export schema isn't documented publicly, so this mapper is deliberately tolerant:
it walks any JSON structure, finds record-like dicts, and maps keys through alias tables
(case/space/underscore-insensitive). Records with body-composition keys → measurements;
records with exercise/workout keys → workouts. Unknown keys are kept in `details`.
"""
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from app.data import db

BODY_ALIASES = {
    "weight_kg": ["weight", "weightkg", "bodyweight", "poids", "gewicht", "mass"],
    "body_fat_pct": ["bodyfat", "fat", "fatpercent", "fatpercentage", "bodyfatpercentage", "bodyfatpct", "fatpct", "bf"],
    "fat_mass_kg": ["fatmass", "fatmasskg"],
    "muscle_mass_kg": ["musclemass", "muscle", "musclemasskg", "skeletalmusclemass", "leanmass"],
    "bone_mass_kg": ["bonemass", "bone"],
    "water_pct": ["water", "bodywater", "totalbodywater", "waterpercentage", "tbw", "hydration"],
    "visceral_fat": ["visceralfat", "visceralfatrating", "visceralfatlevel", "visceral"],
    "bmr_kcal": ["bmr", "basalmetabolicrate", "metabolism", "dailycaloricintake"],
    "metabolic_age": ["metabolicage", "metage"],
}
DATE_KEYS = ["date", "datetime", "timestamp", "measuredat", "createdat", "time", "day", "start", "starttime", "startdate"]
WORKOUT_HINTS = {"exercises", "exercise", "sets", "reps", "workout", "workoutname", "activity", "duration", "program", "session"}


def _norm(k: str) -> str:
    return re.sub(r"[^a-z0-9]", "", k.lower())


def _parse_dt(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        ts = v / 1000 if v > 1e11 else v
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")
    s = str(v).strip().replace("Z", "+00:00")
    for fmt in (None, "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d"):
        try:
            dt = datetime.fromisoformat(s) if fmt is None else datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    return None


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):  # {"value": 62.1, "unit": "kg"}
        return _num(v.get("value"))
    if isinstance(v, str):
        m = re.search(r"-?\d+(?:[.,]\d+)?", v)
        return float(m.group().replace(",", ".")) if m else None
    return None


def _records(node: Any) -> list[dict]:
    """Collect every dict that has a date-like key, recursively."""
    out: list[dict] = []
    if isinstance(node, list):
        for x in node:
            out += _records(x)
    elif isinstance(node, dict):
        keys = {_norm(k) for k in node}
        if keys & set(DATE_KEYS):
            out.append(node)
        for v in node.values():
            if isinstance(v, (list, dict)):
                out += _records(v)
    return out


def _date_of(rec: dict) -> str | None:
    for k, v in rec.items():
        if _norm(k) in DATE_KEYS:
            d = _parse_dt(v)
            if d:
                return d
    return None


def _body_values(rec: dict) -> dict[str, float]:
    found = {}
    for k, v in rec.items():
        nk = _norm(k)
        for metric, aliases in BODY_ALIASES.items():
            if nk in aliases or nk == _norm(metric):
                n = _num(v)
                if n is not None and metric not in found:
                    found[metric] = n
    # "fat" alone can be kg or %, disambiguate by magnitude vs weight
    if "body_fat_pct" in found and "weight_kg" in found and found["body_fat_pct"] > 60:
        found["fat_mass_kg"] = found.pop("body_fat_pct")
    return found


def _workout(rec: dict, source: str) -> dict | None:
    start = _date_of(rec)
    if not start:
        return None
    name = next((str(v) for k, v in rec.items() if _norm(k) in {"name", "workoutname", "title", "activity", "type", "program"}), "strength")
    duration = next((_num(v) for k, v in rec.items() if _norm(k) in {"duration", "durationmin", "minutes", "durationminutes"}), None)
    if duration and duration > 400:  # seconds
        duration /= 60
    kcal = next((_num(v) for k, v in rec.items() if _norm(k) in {"calories", "kcal", "energy", "caloriesburned"}), None)
    lname = name.lower()
    wtype = ("cardio" if any(w in lname for w in ("cardio", "bike", "run", "row", "treadmill"))
             else "hiit" if "hiit" in lname or "circuit" in lname
             else "yoga" if "yoga" in lname else "pilates" if "pilates" in lname else "strength")
    details = {k: v for k, v in rec.items() if _norm(k) not in DATE_KEYS}
    return {"start_ts": start, "source": source, "type": wtype, "duration_min": duration or 60,
            "kcal": kcal, "details": {"name": name, **details}}


def import_data(data: Any, name: str, source: str | None = None) -> dict:
    """Map one parsed JSON document into measurements/workouts and upsert them."""
    from app.ingest.technogym import import_technogym

    tg = import_technogym(data)  # Mywellness (Technogym) export: exact mapping, detected by shape
    if tg is not None:
        return {"file": name, "source": "kinetix", **tg}
    src = source or ("tanita" if "tanita" in name.lower() else "kinetix")
    measurements, workouts = [], []
    for rec in _records(data):
        keys = {_norm(k) for k in rec}
        body = _body_values(rec)
        ts = _date_of(rec)
        if body and ts and len(body) >= 1 and not (keys & WORKOUT_HINTS and len(body) < 2):
            # Tanita readings come through Kinetix too; tag them as tanita (the device) either way
            for metric, value in body.items():
                measurements.append({"ts": ts, "source": "tanita", "metric": metric, "value": round(value, 2),
                                     "unit": {"body_fat_pct": "%", "water_pct": "%"}.get(metric, "kg")})
        elif keys & WORKOUT_HINTS:
            w = _workout(rec, "kinetix")
            if w:
                workouts.append(w)
    return {
        "file": name, "source": src,
        "measurements": db.upsert_measurements(measurements) if measurements else 0,
        "workouts": db.upsert_workouts(workouts) if workouts else 0,
    }


def import_json(path: str | Path, source: str | None = None) -> dict:
    path = Path(path)
    return import_data(json.loads(path.read_text(encoding="utf-8")), path.name, source)


MAX_MEMBER_BYTES = 50_000_000


def import_zip(path: str | Path) -> dict:
    """Import every .json file inside a ZIP (e.g. several Kinetix/Tanita exports at once).

    Members are read in memory (never extracted to disk, so no path-traversal risk); macOS
    metadata and hidden files are skipped; one malformed file doesn't abort the others.
    """
    files: list[dict] = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            name = info.filename
            base = name.rsplit("/", 1)[-1]
            if info.is_dir() or "__MACOSX" in name or base.startswith(".") or not base.lower().endswith(".json"):
                continue
            if info.file_size > MAX_MEMBER_BYTES:
                files.append({"file": base, "error": "file too large (> 50 MB)"})
                continue
            try:
                data = json.loads(zf.read(info).decode("utf-8-sig"))
                files.append(import_data(data, base))
            except (ValueError, UnicodeDecodeError) as exc:
                files.append({"file": base, "error": f"not valid JSON: {str(exc)[:120]}"})
    return {
        "files": files,
        "measurements": sum(f.get("measurements", 0) for f in files),
        "workouts": sum(f.get("workouts", 0) for f in files),
    }
