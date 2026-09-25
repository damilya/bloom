"""Cross-source de-duplication, run after every import (idempotent, order-independent).

The same real-world event reaches us through several apps:
  • Mywellness mirrors Apple Watch outdoor workouts (walks, swims) → keep the Apple copy (richer HR data)
  • a Kinetix gym visit is also recorded by the Apple Watch as a strength/cardio workout → keep the Kinetix
    session (it has exercises, sets and volume), copying the Watch's heart rate / calories into it if missing
  • Mywellness biometrics mirror Withings weigh-ins → keep the Withings reading; what remains under
    'tanita' are the real gym scans and manual entries
Found on real exports; demo data can't show this (see EVALS.md §6).
"""
from datetime import datetime, timedelta

from app.data import db

MIRROR_WINDOW = timedelta(minutes=15)
GYM_BEFORE, GYM_AFTER = timedelta(hours=1), timedelta(hours=3)
APPLE_GYM_TYPES = {"strength", "cardio", "hiit", "core", "other"}
MIRRORED_METRICS = ("weight_kg", "body_fat_pct", "fat_mass_kg", "muscle_mass_kg")
MIRROR_TOLERANCE = 0.15


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def dedupe_workouts() -> dict:
    ws = db.rows("SELECT id, start_ts, source, type, avg_hr, kcal, details FROM workouts")
    apple = [w for w in ws if w["source"] == "apple_health"]
    kinetix_outdoor = [w for w in ws if w["source"] == "kinetix" and "Mywellness" in (w["details"] or "")]
    gym = [w for w in ws if w["source"] == "kinetix" and "Kinetix gym session" in (w["details"] or "")]
    drop: set[int] = set()
    fill: dict[int, dict] = {}
    for k in kinetix_outdoor:
        if any(a["type"] == k["type"] and abs(_ts(a["start_ts"]) - _ts(k["start_ts"])) <= MIRROR_WINDOW for a in apple):
            drop.add(k["id"])
    for g in gym:
        start = _ts(g["start_ts"])
        for a in apple:
            if a["type"] in APPLE_GYM_TYPES and start - GYM_BEFORE <= _ts(a["start_ts"]) <= start + GYM_AFTER:
                drop.add(a["id"])
                f = fill.setdefault(g["id"], {})
                if not g["avg_hr"] and a["avg_hr"]:
                    f["avg_hr"] = a["avg_hr"]
    with db.connect() as conn:
        for gid, f in fill.items():
            if f:
                conn.execute("UPDATE workouts SET avg_hr=COALESCE(avg_hr, ?) WHERE id=?", (f["avg_hr"], gid))
        conn.executemany("DELETE FROM workouts WHERE id=?", [(i,) for i in drop])
    return {"workouts_removed": len(drop)}


def dedupe_measurements() -> dict:
    ph = ",".join("?" * len(MIRRORED_METRICS))
    rows = db.rows(
        f"SELECT t.id FROM measurements t JOIN measurements w ON w.source='withings' AND w.metric=t.metric "
        f"AND substr(w.ts,1,10)=substr(t.ts,1,10) AND ABS(w.value - t.value) <= ? "
        f"WHERE t.source='tanita' AND t.metric IN ({ph})",
        (MIRROR_TOLERANCE, *MIRRORED_METRICS),
    )
    ids = {r["id"] for r in rows}
    with db.connect() as conn:
        conn.executemany("DELETE FROM measurements WHERE id=?", [(i,) for i in ids])
    return {"measurements_removed": len(ids)}


def dedupe_all() -> dict:
    return {**dedupe_workouts(), **dedupe_measurements()}
