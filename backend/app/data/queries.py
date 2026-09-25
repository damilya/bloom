"""Read-side domain logic over the health DB.

Used by BOTH the MCP server (agent tools) and the dashboard API, so the numbers the
coach talks about are exactly the numbers the charts show.
"""
import json
import statistics
from datetime import date, datetime, timedelta

from app.data import db

METRIC_UNITS = {
    "weight_kg": "kg", "body_fat_pct": "%", "fat_mass_kg": "kg", "muscle_mass_kg": "kg",
    "bone_mass_kg": "kg", "water_pct": "%", "hydration_kg": "kg", "visceral_fat": "level",
    "bmr_kcal": "kcal", "metabolic_age": "years", "resting_hr": "bpm", "hrv_ms": "ms",
    "sleep_hours": "h", "steps": "steps", "bmi": "kg/m²", "fitness_age": "years", "vo2max": "ml/kg/min",
}
DEFAULT_CYCLE_LEN = 28
DEFAULT_PERIOD_LEN = 5


def _today() -> date:
    return date.today()


def _parse_date(d: str | date | None) -> date:
    if d is None or d == "" or d == "today":
        return _today()
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d)[:10])


# ───────────────────────────── body composition ─────────────────────────────

def body_composition_trend(metric: str = "weight_kg", days: int = 90, source: str | None = None) -> dict:
    since = (_today() - timedelta(days=days)).isoformat()
    sql = "SELECT substr(ts,1,10) AS date, source, AVG(value) AS value FROM measurements WHERE metric=? AND ts>=?"
    params: list = [metric, since]
    if source:
        sql += " AND source=?"
        params.append(source)
    sql += " GROUP BY date, source ORDER BY date"
    points = db.rows(sql, tuple(params))
    by_source: dict[str, list[dict]] = {}
    for p in points:
        p["value"] = round(p["value"], 2)
        by_source.setdefault(p["source"], []).append(p)
    summary = {}
    today = _today()
    for src, pts in by_source.items():
        first, last = pts[0], pts[-1]
        summary[src] = {
            "first": first, "last": last, "n": len(pts),
            "change": round(last["value"] - first["value"], 2),
        }
        # noise-robust trend: mean of the last 7 days vs the mean of the 7 days four weeks earlier
        recent = [p["value"] for p in pts if (today - date.fromisoformat(p["date"])).days < 7]
        earlier = [p["value"] for p in pts if 28 <= (today - date.fromisoformat(p["date"])).days < 35]
        if recent and earlier:
            summary[src]["weekly_avg_change_28d"] = round(sum(recent) / len(recent) - sum(earlier) / len(earlier), 2)
    return {"metric": metric, "unit": METRIC_UNITS.get(metric, ""), "days": days,
            "points": points, "summary": summary}


def latest_metrics() -> dict:
    """Most recent value per metric, its 7-day change *within the same source*, and the latest value from
    every source (home scale vs gym Tanita differ systematically, so "my latest Tanita scan" must not be
    answered with a Withings reading, found by the `da05` eval)."""
    out = {}
    for m in METRIC_UNITS:
        per_source = db.rows(
            "SELECT source, ts, value FROM measurements m1 WHERE metric=? AND ts = "
            "(SELECT MAX(ts) FROM measurements m2 WHERE m2.metric=m1.metric AND m2.source=m1.source) ORDER BY ts DESC",
            (m,),
        )
        if not per_source:
            continue
        last = per_source[0]
        ts = last["ts"][:10]
        prev = db.rows(
            "SELECT value FROM measurements WHERE metric=? AND source=? AND substr(ts,1,10)<=? ORDER BY ts DESC LIMIT 1",
            (m, last["source"], (date.fromisoformat(ts) - timedelta(days=7)).isoformat()),
        )
        out[m] = {
            "value": round(last["value"], 2), "date": ts, "source": last["source"], "unit": METRIC_UNITS[m],
            "delta_7d": round(last["value"] - prev[0]["value"], 2) if prev else None,
        }
        if len(per_source) > 1:
            out[m]["by_source"] = {r["source"]: {"value": round(r["value"], 2), "date": r["ts"][:10]} for r in per_source}
    return out


def strength_progress(days: int = 365) -> dict:
    """1RM strength tests from Kinetix (Technogym Biostrength): first vs latest per exercise."""
    since = (_today() - timedelta(days=days)).isoformat()
    rows = db.rows("SELECT metric, substr(ts,1,10) AS date, value FROM measurements WHERE metric LIKE 'rm1_%' AND ts>=? "
                   "ORDER BY metric, ts", (since,))
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["metric"], []).append(r)
    tests = []
    for metric, pts in by.items():
        first, last = pts[0], pts[-1]
        tests.append({"exercise": metric[4:].replace("_", " "), "tests": len(pts), "first": {"date": first["date"], "kg": first["value"]},
                      "latest": {"date": last["date"], "kg": last["value"]},
                      "change_pct": round(100 * (last["value"] - first["value"]) / first["value"], 1) if first["value"] else None})
    tests.sort(key=lambda t: -t["tests"])
    return {"days": days, "unit": "kg (estimated one-rep max)", "exercises": tests}


# ───────────────────────────── menstrual cycle ─────────────────────────────

def _period_starts() -> list[tuple[date, int]]:
    """Return (start_date, period_length_days) for each period, from flow days."""
    days = sorted(date.fromisoformat(r["date"]) for r in db.rows("SELECT date FROM cycle_days"))
    periods: list[list[date]] = []
    for d in days:
        if periods and (d - periods[-1][-1]).days <= 2:
            periods[-1].append(d)
        else:
            periods.append([d])
    return [(p[0], (p[-1] - p[0]).days + 1) for p in periods]


def cycle_stats() -> dict:
    starts = _period_starts()
    lengths = [(b[0] - a[0]).days for a, b in zip(starts, starts[1:], strict=False) if 15 <= (b[0] - a[0]).days <= 120]
    recent = lengths[-6:]
    avg_len = round(statistics.median(recent)) if recent else DEFAULT_CYCLE_LEN
    sd = round(statistics.pstdev(recent), 1) if len(recent) >= 2 else None
    period_len = round(statistics.median([p for _, p in starts[-6:]])) if starts else DEFAULT_PERIOD_LEN
    irregular = bool(avg_len > 35 or (sd is not None and sd > 7))
    return {
        "n_cycles_recorded": len(lengths), "cycle_lengths": recent, "avg_cycle_len": avg_len,
        "cycle_len_sd": sd, "avg_period_len": period_len, "irregular": irregular,
        "last_period_start": starts[-1][0].isoformat() if starts else None,
    }


def _phase_for_day(day: int, cycle_len: int, period_len: int) -> str:
    ovulation = max(cycle_len - 14, period_len + 2)  # luteal phase is the more constant one (~14 d)
    if day <= period_len:
        return "menstrual"
    if day < ovulation - 1:
        return "follicular"
    if day <= ovulation + 1:
        return "ovulatory"
    return "luteal"


def cycle_status(on: str | date | None = None) -> dict:
    d = _parse_date(on)
    stats = cycle_stats()
    starts = [s for s, _ in _period_starts() if s <= d]
    if not starts:
        return {"date": d.isoformat(), "known": False,
                "message": "No menstrual-flow data recorded. Import Apple Health cycle tracking."}
    start = starts[-1]
    day = (d - start).days + 1
    cycle_len, period_len = stats["avg_cycle_len"], stats["avg_period_len"]
    late = day > cycle_len + 7
    phase = "late / unknown (cycle longer than usual)" if late else _phase_for_day(day, cycle_len, period_len)
    confidence = "low" if (stats["irregular"] or late or stats["n_cycles_recorded"] < 2) else "moderate"
    next_expected = start + timedelta(days=cycle_len)
    return {
        "date": d.isoformat(), "known": True, "cycle_day": day, "phase": phase,
        "cycle_start": start.isoformat(), "expected_next_period": next_expected.isoformat(),
        "confidence": confidence, **stats,
        "note": (
            "Cycle is irregular (common with PCOS): ovulation timing is uncertain, so phase is an estimate "
            "based on flow dates only, not on temperature/LH confirmation."
            if confidence == "low" else "Phase estimated from recorded period dates (calendar method)."
        ),
    }


def cycle_phase_bands(start: str | date, end: str | date) -> list[dict]:
    """Contiguous phase segments between start and end — used to shade charts."""
    s, e = _parse_date(start), _parse_date(end)
    if not _period_starts():
        return []
    bands: list[dict] = []
    d = s
    while d <= e:
        st = cycle_status(d)
        phase = st.get("phase", "unknown") if st.get("known") else "unknown"
        phase = "unknown" if phase.startswith("late") else phase
        if bands and bands[-1]["phase"] == phase:
            bands[-1]["end"] = d.isoformat()
        else:
            bands.append({"phase": phase, "start": d.isoformat(), "end": d.isoformat()})
        d += timedelta(days=1)
    return bands


# ───────────────────────────── nutrition ─────────────────────────────

def nutrition_targets() -> dict:
    """Evidence-informed defaults; protein scales with body weight (ISSN: 1.4–2.0 g/kg/day for exercisers)."""
    w = latest_metrics().get("weight_kg", {}).get("value") or 65.0
    return {
        "protein_g": round(1.6 * w), "fiber_g": 28, "carbs_g": None, "fat_g": None,
        "basis": "protein 1.6 g/kg body weight (ISSN 2017 position stand range 1.4–2.0); fiber ≥25–30 g/day",
    }


def nutrition_summary(days: int = 7) -> dict:
    since = (_today() - timedelta(days=days - 1)).isoformat()
    daily = db.rows(
        "SELECT date, ROUND(SUM(kcal)) kcal, ROUND(SUM(carbs_g),1) carbs_g, ROUND(SUM(fat_g),1) fat_g, "
        "ROUND(SUM(protein_g),1) protein_g, ROUND(SUM(fiber_g),1) fiber_g, COUNT(*) n_items "
        "FROM meals WHERE date>=? GROUP BY date ORDER BY date",
        (since,),
    )
    avg = {}
    if daily:
        for k in ("kcal", "carbs_g", "fat_g", "protein_g", "fiber_g"):
            avg[k] = round(sum((r[k] or 0) for r in daily) / len(daily), 1)
        total_kcal = avg["carbs_g"] * 4 + avg["protein_g"] * 4 + avg["fat_g"] * 9
        if total_kcal:
            avg["pct_kcal"] = {
                "carbs": round(100 * avg["carbs_g"] * 4 / total_kcal),
                "protein": round(100 * avg["protein_g"] * 4 / total_kcal),
                "fat": round(100 * avg["fat_g"] * 9 / total_kcal),
            }
    return {"days": days, "days_logged": len(daily), "daily": daily, "average": avg, "targets": nutrition_targets()}


def meals_on(day: str) -> list[dict]:
    return db.rows("SELECT * FROM meals WHERE date=? ORDER BY id", (day,))


# ───────────────────────────── workouts ─────────────────────────────

def workouts(days: int = 30, source: str | None = None) -> dict:
    since = (_today() - timedelta(days=days)).isoformat()
    sql = "SELECT * FROM workouts WHERE start_ts>=?"
    params: list = [since]
    if source:
        sql += " AND source=?"
        params.append(source)
    items = db.rows(sql + " ORDER BY start_ts DESC", tuple(params))
    for w in items:
        w["details"] = json.loads(w["details"] or "{}")
    by_type: dict[str, dict] = {}
    for w in items:
        t = by_type.setdefault(w["type"], {"count": 0, "minutes": 0.0})
        t["count"] += 1
        t["minutes"] += w["duration_min"] or 0
    weeks = max(days / 7, 1)
    return {
        "days": days, "total": len(items), "per_week": round(len(items) / weeks, 1),
        "by_type": {k: {"count": v["count"], "minutes": round(v["minutes"])} for k, v in by_type.items()},
        "items": items[:60],
    }


# ───────────────────────────── weather ─────────────────────────────

def weather(start: str | None = None, end: str | None = None) -> dict:
    from app.ingest.weather import describe, sync_weather

    s = _parse_date(start) if start else _today() - timedelta(days=7)
    e = _parse_date(end) if end else _today() + timedelta(days=3)
    have = db.rows("SELECT COUNT(*) n FROM weather WHERE date BETWEEN ? AND ?", (s.isoformat(), e.isoformat()))[0]["n"]
    if have < (e - s).days + 1:
        try:
            sync_weather(s, e)
        except Exception as exc:  # network down → still answer from cache
            return {"error": f"weather fetch failed: {exc}", "days": _weather_rows(s, e, describe)}
    return {"location": "Brussels", "days": _weather_rows(s, e, describe)}


def _weather_rows(s: date, e: date, describe) -> list[dict]:
    out = db.rows("SELECT * FROM weather WHERE date BETWEEN ? AND ? ORDER BY date", (s.isoformat(), e.isoformat()))
    for r in out:
        r["summary"] = describe(r["weather_code"])
    return out


# ───────────────────────────── goals ─────────────────────────────

def list_goals(status: str | None = "active") -> list[dict]:
    sql, params = "SELECT * FROM goals", ()
    if status:
        sql, params = sql + " WHERE status=?", (status,)
    goals = db.rows(sql + " ORDER BY created_at DESC", params)
    for g in goals:
        g["weekly_plan"] = json.loads(g["weekly_plan"] or "[]")
        g["progress"] = goal_progress(g)
    return goals


def goal_progress(g: dict) -> dict | None:
    if not g.get("metric") or g.get("target_value") is None:
        return None
    last = db.rows("SELECT value, ts FROM measurements WHERE metric=? ORDER BY ts DESC LIMIT 1", (g["metric"],))
    if not last:
        return None
    current = last[0]["value"]
    base = g.get("baseline_value") if g.get("baseline_value") is not None else current
    span = g["target_value"] - base
    pct = 100.0 if span == 0 else max(0.0, min(100.0, 100 * (current - base) / span))
    return {"current": round(current, 2), "baseline": round(base, 2), "pct": round(pct)}


def save_goal(goal: dict) -> dict:
    baseline = goal.get("baseline_value")
    if baseline is None and goal.get("metric"):
        last = db.rows("SELECT value FROM measurements WHERE metric=? ORDER BY ts DESC LIMIT 1", (goal["metric"],))
        baseline = last[0]["value"] if last else None
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO goals(title, metric, baseline_value, target_value, unit, deadline, weekly_plan, rationale) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (goal["title"], goal.get("metric"), baseline, goal.get("target_value"), goal.get("unit"),
             goal.get("deadline"), json.dumps(goal.get("weekly_plan") or []), goal.get("rationale")),
        )
        gid = cur.lastrowid
    return {"id": gid, "saved": True, "created_at": datetime.now().isoformat(timespec="seconds")}


def update_goal_status(goal_id: int, status: str) -> None:
    with db.connect() as conn:
        conn.execute("UPDATE goals SET status=? WHERE id=?", (status, goal_id))
