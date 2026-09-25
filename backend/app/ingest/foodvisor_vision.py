"""Foodvisor screenshot → structured nutrition log (multimodal).

Why vision: Foodvisor has no public API or reliable export, so the only data channel the user
actually has is the app screen. A vision model reads the screenshot into a strict schema; we then
run deterministic sanity checks (Atwater kcal ≈ 4·C + 4·P + 9·F, item sums vs. printed totals)
and show a preview for the user to confirm before anything is written to the DB.
"""
import base64
from datetime import date, timedelta

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.data import db
from app.llm import get_structured


class FoodItem(BaseModel):
    meal: str = Field(description="breakfast | lunch | dinner | snack")
    name: str = Field(description="food name as shown")
    kcal: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    protein_g: float | None = None
    fiber_g: float | None = None


class Totals(BaseModel):
    kcal: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    protein_g: float | None = None
    fiber_g: float | None = None


class FoodvisorExtraction(BaseModel):
    date: str | None = Field(None, description="YYYY-MM-DD only if the YEAR is visible on screen, else null")
    day: int | None = Field(None, description="day of month shown on screen (e.g. 'Monday, 7 September' → 7)")
    month: int | None = Field(None, description="month number shown on screen (e.g. September → 9)")
    calories_vs_goal: float | None = Field(
        None, description="signed value of a calorie ring that is RELATIVE to the goal: 'Cal over 122' → 122, 'Cal left 300' → -300")
    items: list[FoodItem] = Field(default_factory=list)
    daily_totals: Totals | None = Field(None, description="totals printed on screen, if any")
    unreadable: bool = Field(False, description="true if the image is not a food log / unreadable")
    notes: str = ""


SYSTEM = """You extract nutrition data from screenshots of the Foodvisor app (or similar food logs).
Rules:
- Only transcribe numbers that are visible. Never estimate or invent a value — use null if absent.
- Units: kcal for energy, grams for macros. Convert if shown otherwise.
- Map sections to meal: breakfast, lunch, dinner, snack.
- If the screen only shows daily totals (no items), fill daily_totals and leave items empty.
- Foodvisor "Daily Insights"/summary screens show rings. The FIRST ring labelled "Cal over" or "Cal left" is the
  difference from the calorie GOAL, not the calories eaten: put it in calories_vs_goal and leave kcal null.
  Macro rings read "eaten / target g" (e.g. "53 / 74 g" under Fat → fat_g = 53); use the eaten value only.
- Dates: if the screen shows no year (e.g. "Monday, 7 September"), set date=null and fill day and month.
- If the image is not a food log, set unreadable=true."""


def extract(image_bytes: bytes, mime: str = "image/png") -> dict:
    b64 = base64.b64encode(image_bytes).decode()
    llm = get_structured(FoodvisorExtraction, role="fast")
    result: FoodvisorExtraction = llm.invoke([
        SystemMessage(SYSTEM),
        HumanMessage(content=[
            {"type": "text", "text": "Extract the food log from this screenshot."},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}},
        ]),
    ])
    t = result.daily_totals
    notes: list[dict] = []
    if t and not t.kcal and None not in (t.carbs_g, t.protein_g, t.fat_g):
        # e.g. "122 Cal over" screens: intake itself isn't shown → derive it from the macros (Atwater factors)
        t.kcal = round(4 * t.carbs_g + 4 * t.protein_g + 9 * t.fat_g)
        notes.append({"level": "ok", "item": "totals", "msg": f"calories not shown on screen — computed from macros: {t.kcal:.0f} kcal"
                      + (f" (screen: {result.calories_vs_goal:+.0f} vs goal)" if result.calories_vs_goal is not None else "")})
    if not result.items and result.daily_totals and result.daily_totals.kcal:
        # screens that only show the day's totals: keep them as one entry rather than saving nothing
        t = result.daily_totals
        result.items = [FoodItem(meal="snack", name="Daily total (from summary)", kcal=t.kcal, carbs_g=t.carbs_g,
                                 fat_g=t.fat_g, protein_g=t.protein_g, fiber_g=t.fiber_g)]
    data = result.model_dump()
    data["checks"] = notes + [c for c in sanity_checks(result) if not (notes and c["level"] == "ok")]
    if not result.items and not result.unreadable:
        data["checks"] = [{"level": "warn", "item": "all", "msg": "no food items or totals could be read from this screenshot"}]
    data["date"] = resolve_date(result.date, result.day, result.month)
    return data


def resolve_date(iso: str | None, day: int | None, month: int | None, today: date | None = None) -> str:
    """Screens often omit the year: use the most recent past occurrence of day/month.

    (The model otherwise *guesses* a year: "Monday, 7 September" became 2020, the last year it was a Monday.)
    A full date that is in the future or more than a year old is treated the same way.
    """
    today = today or date.today()
    if iso:
        try:
            d = date.fromisoformat(iso[:10])
            if today - timedelta(days=366) <= d <= today:
                return d.isoformat()
            day, month = day or d.day, month or d.month
        except ValueError:
            pass
    if day and month:
        for year in (today.year, today.year - 1):
            try:
                d = date(year, month, day)
            except ValueError:
                continue
            if d <= today:
                return d.isoformat()
    return today.isoformat()


def sanity_checks(x: FoodvisorExtraction) -> list[dict]:
    checks = []
    for it in x.items:
        if it.kcal and None not in (it.carbs_g, it.protein_g, it.fat_g):
            atwater = 4 * it.carbs_g + 4 * it.protein_g + 9 * it.fat_g
            dev = abs(atwater - it.kcal) / max(it.kcal, 1)
            if dev > 0.25:
                checks.append({"level": "warn", "item": it.name,
                               "msg": f"kcal {it.kcal:.0f} vs macros → {atwater:.0f} kcal ({dev:.0%} off) — check the reading"})
    if x.daily_totals and x.daily_totals.kcal and x.items:
        s = sum(i.kcal or 0 for i in x.items)
        if s and abs(s - x.daily_totals.kcal) / x.daily_totals.kcal > 0.1:
            checks.append({"level": "warn", "item": "totals",
                           "msg": f"items sum to {s:.0f} kcal but screen total is {x.daily_totals.kcal:.0f}"})
    if not checks:
        checks.append({"level": "ok", "item": "all", "msg": "numbers are internally consistent"})
    return checks


def save(day: str, items: list[dict]) -> int:
    records = [{"date": day, "meal": i.get("meal") or "snack", "name": i["name"],
                "kcal": i.get("kcal"), "carbs_g": i.get("carbs_g"), "fat_g": i.get("fat_g"),
                "protein_g": i.get("protein_g"), "fiber_g": i.get("fiber_g"), "source": "foodvisor_vision"}
               for i in items]
    return db.upsert_meals(records)
