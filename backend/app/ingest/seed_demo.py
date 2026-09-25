"""Deterministic demo dataset (120 days) so the app, MCP tools and evals run before real exports exist.

Shape mimics the target user: irregular (PCOS-like) cycles, Withings weigh-ins most mornings,
Tanita scans at the gym every ~2 weeks, Kinetix strength sessions + Apple Watch runs/yoga,
Foodvisor-style meal logs. Usage:
    python -m app.ingest.seed_demo          # wipe + seed
    python -m app.ingest.seed_demo --clear  # wipe only (before importing real data)
"""
import random
import sys
from datetime import date, timedelta

from app.data import db

DAYS = 120
CYCLE_LENGTHS = [33, 39, 30, 42, 35]  # irregular, PCOS-like

MEALS = {
    "breakfast": [("Greek yogurt, berries & oats", 380, 42, 11, 24, 6), ("Eggs on rye toast", 420, 30, 20, 26, 5),
                  ("Protein porridge", 450, 55, 10, 30, 8)],
    "lunch": [("Chicken quinoa bowl", 610, 58, 20, 45, 9), ("Lentil soup & bread", 520, 70, 12, 26, 14),
              ("Salmon poke", 650, 62, 22, 38, 6), ("Tuna salad", 430, 20, 22, 36, 7)],
    "dinner": [("Tofu stir-fry with rice", 590, 72, 18, 28, 8), ("Steak, potatoes & greens", 700, 50, 30, 48, 7),
               ("Pasta bolognese", 720, 88, 22, 38, 6), ("Baked cod & vegetables", 480, 35, 15, 42, 9)],
    "snack": [("Apple & almonds", 220, 20, 14, 6, 5), ("Protein shake", 160, 6, 3, 28, 1),
              ("Dark chocolate", 170, 13, 12, 2, 3), ("Hummus & carrots", 190, 18, 10, 6, 6)],
}


def clear() -> None:
    with db.connect() as conn:
        for t in ("measurements", "workouts", "cycle_days", "meals", "goals", "weather"):
            conn.execute(f"DELETE FROM {t}")


def seed() -> dict:
    db.init_db()
    clear()
    rnd = random.Random(42)
    today = date.today()
    start = today - timedelta(days=DAYS)

    # cycles: walk backwards from a recent period start
    cycle_days, starts = [], []
    d = today - timedelta(days=17)  # current cycle day ≈ 18 → luteal-ish
    i = 0
    while d > start - timedelta(days=45):
        starts.append(d)
        d -= timedelta(days=CYCLE_LENGTHS[i % len(CYCLE_LENGTHS)])
        i += 1
    for s in starts:
        for k, flow in enumerate(["medium", "heavy", "medium", "light", "light"]):
            cd = s + timedelta(days=k)
            if start <= cd <= today:
                cycle_days.append({"date": cd.isoformat(), "flow": flow, "source": "apple_health"})

    meas, workouts, meals = [], [], []
    for n in range(DAYS + 1):
        day = start + timedelta(days=n)
        t = n / DAYS
        ds = day.isoformat()
        # Withings: ~80% of mornings
        if rnd.random() < 0.8:
            w = 66.2 - 1.8 * t + rnd.gauss(0, 0.35)
            bf = 30.6 - 1.9 * t + rnd.gauss(0, 0.4)
            ts = f"{ds}T07:{rnd.randint(5, 40):02d}:00"
            meas += [
                {"ts": ts, "source": "withings", "metric": "weight_kg", "value": round(w, 2), "unit": "kg"},
                {"ts": ts, "source": "withings", "metric": "body_fat_pct", "value": round(bf, 1), "unit": "%"},
                {"ts": ts, "source": "withings", "metric": "muscle_mass_kg", "value": round(43.6 + 0.6 * t + rnd.gauss(0, 0.2), 2), "unit": "kg"},
                {"ts": ts, "source": "withings", "metric": "fat_mass_kg", "value": round(w * bf / 100, 2), "unit": "kg"},
            ]
        # Apple Watch vitals
        meas += [
            {"ts": f"{ds}T08:00:00", "source": "apple_health", "metric": "resting_hr", "value": round(61 - 3 * t + rnd.gauss(0, 1.5)), "unit": "bpm"},
            {"ts": f"{ds}T08:00:00", "source": "apple_health", "metric": "hrv_ms", "value": round(42 + 6 * t + rnd.gauss(0, 5)), "unit": "ms"},
            {"ts": f"{ds}T08:00:00", "source": "apple_health", "metric": "sleep_hours", "value": round(min(9, max(5, rnd.gauss(7.1, 0.7))), 2), "unit": "h"},
            {"ts": f"{ds}T08:00:00", "source": "apple_health", "metric": "steps", "value": round(max(2500, rnd.gauss(8500, 2500))), "unit": "steps"},
        ]
        # Tanita at Kinetix every 14 days
        if n % 14 == 3:
            ts = f"{ds}T18:30:00"
            w = 66.4 - 1.8 * t + rnd.gauss(0, 0.2)
            for metric, value, unit in [
                ("weight_kg", w, "kg"), ("body_fat_pct", 31.2 - 2.0 * t + rnd.gauss(0, 0.3), "%"),
                ("muscle_mass_kg", 43.1 + 0.7 * t, "kg"), ("water_pct", 50.1 + 1.0 * t, "%"),
                ("visceral_fat", 5 if t < 0.5 else 4, "level"), ("bmr_kcal", 1402 + 20 * t, "kcal"),
                ("metabolic_age", 31 - round(3 * t), "years"),
            ]:
                meas.append({"ts": ts, "source": "tanita", "metric": metric, "value": round(value, 2), "unit": unit})
        # workouts: Kinetix strength Mon/Wed/Fri (skip some), Apple runs Sat, yoga Tue
        wd = day.weekday()
        if wd in (0, 2, 4) and rnd.random() < 0.85:
            focus = {0: "Lower body", 2: "Upper body", 4: "Full body"}[wd]
            workouts.append({"start_ts": f"{ds}T18:00:00", "source": "kinetix", "type": "strength",
                             "duration_min": rnd.choice([50, 55, 60, 65]), "kcal": rnd.randint(280, 380),
                             "avg_hr": rnd.randint(118, 135),
                             "details": {"name": f"{focus} strength", "exercises": _exercises(focus, t, rnd)}})
        if wd == 5 and rnd.random() < 0.8:
            km = round(rnd.uniform(5, 9), 1)
            workouts.append({"start_ts": f"{ds}T09:30:00", "source": "apple_health", "type": "running",
                             "duration_min": round(km * rnd.uniform(5.8, 6.6), 1), "kcal": round(km * 62),
                             "distance_km": km, "avg_hr": rnd.randint(148, 162), "details": {}})
        if wd == 1 and rnd.random() < 0.6:
            workouts.append({"start_ts": f"{ds}T07:15:00", "source": "apple_health", "type": "yoga",
                             "duration_min": 40, "kcal": 140, "avg_hr": 96, "details": {}})
        # meals (Foodvisor) ~90% of days
        if rnd.random() < 0.9:
            for meal, options in MEALS.items():
                if meal == "snack" and rnd.random() < 0.4:
                    continue
                name, kcal, c, f, p, fi = rnd.choice(options)
                k = rnd.uniform(0.9, 1.1)
                meals.append({"date": ds, "meal": meal, "name": name, "kcal": round(kcal * k), "carbs_g": round(c * k, 1),
                              "fat_g": round(f * k, 1), "protein_g": round(p * k, 1), "fiber_g": round(fi * k, 1),
                              "source": "foodvisor_vision"})

    return {
        "measurements": db.upsert_measurements(meas), "workouts": db.upsert_workouts(workouts),
        "cycle_days": db.upsert_cycle_days(cycle_days), "meals": db.upsert_meals(meals),
    }


def _exercises(focus: str, t: float, rnd: random.Random) -> list[dict]:
    base = {"Lower body": [("Back squat", 45), ("Romanian deadlift", 50), ("Hip thrust", 70)],
            "Upper body": [("Bench press", 30), ("Lat pulldown", 40), ("Seated row", 35)],
            "Full body": [("Deadlift", 60), ("Overhead press", 22), ("Walking lunge", 16)]}[focus]
    return [{"name": n, "sets": 4, "reps": rnd.choice([6, 8, 10]), "kg": round(kg * (1 + 0.15 * t) / 2.5) * 2.5}
            for n, kg in base]


if __name__ == "__main__":
    db.init_db()
    if "--clear" in sys.argv:
        clear()
        print("cleared")
    else:
        print(seed())
