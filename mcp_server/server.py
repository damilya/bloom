"""health-data-mcp — MCP server exposing the user's aggregated health data as tools.

Why MCP and not a plain internal API: the same tools are consumed by (1) the LangGraph agent in
this app via langchain-mcp-adapters and (2) any MCP client, e.g. Claude Desktop / Claude Code,
with zero glue code. Tool schemas + docstrings are the contract the LLM plans against.

Run:  PYTHONPATH=backend python mcp_server/server.py            (streamable HTTP on :8001/mcp)
      PYTHONPATH=backend python mcp_server/server.py --stdio    (for Claude Desktop)
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

from app.data import db, queries  # noqa: E402

mcp = FastMCP(
    "health-data",
    instructions=(
        "Personal health data of one user (a woman with PCOS training in Brussels): body composition "
        "(Withings scale + Tanita at the gym), menstrual cycle (Apple Health), workouts (Apple Watch + "
        "Stadium Kinetix), nutrition (Foodvisor), weather, and goals. All dates are YYYY-MM-DD."
    ),
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8001")),
    stateless_http=True,
    json_response=True,
    # inside docker-compose the Host header is "mcp:8001", so DNS-rebinding protection is disabled;
    # the port is not published outside the compose network.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

@mcp.tool()
def get_body_composition_trend(metric: str = "weight_kg", days: int = 90, source: str | None = None) -> dict:
    """Time series + change summary for a body metric.

    metric: weight_kg, body_fat_pct, fat_mass_kg, muscle_mass_kg, bone_mass_kg, water_pct, hydration_kg,
    visceral_fat, bmr_kcal, metabolic_age, resting_hr, hrv_ms, sleep_hours, steps, bmi, fitness_age, vo2max.
    days: look-back window (7–365).
    source: optional filter — 'withings' (home scale, frequent), 'tanita' (gym scan, bi-weekly, more
    detailed), 'apple_health'. Different scales disagree by ~0.5–1 kg / 1–2 % fat, so compare trends
    within one source rather than mixing sources.
    """
    return queries.body_composition_trend(metric, max(1, min(days, 365)), source)



@mcp.tool()
def get_latest_metrics() -> dict:
    """Most recent value of every tracked metric with its 7-day change (weight, body fat %, muscle mass,
    resting HR, HRV, sleep hours, steps, visceral fat, BMR, metabolic age)."""
    return queries.latest_metrics()


@mcp.tool()
def get_strength_progress(days: int = 365) -> dict:
    """Strength progress from Kinetix 1RM tests (Technogym Biostrength machines): per exercise the number of
    tests, first and latest estimated one-rep max in kg, and % change. Use for 'am I getting stronger?'."""
    return queries.strength_progress(max(30, min(days, 1500)))


@mcp.tool()
def get_cycle_status(date: str | None = None) -> dict:
    """Menstrual-cycle status on a date (default today): cycle day, estimated phase
    (menstrual / follicular / ovulatory / luteal), average cycle length, regularity and a confidence
    level. Phases are calendar estimates from Apple Health flow records — low confidence when cycles
    are irregular (e.g. PCOS)."""
    return queries.cycle_status(date)


@mcp.tool()
def get_nutrition_summary(days: int = 7) -> dict:
    """Daily nutrition from Foodvisor logs over the last `days`: kcal, carbs, fat, protein, fiber per day,
    averages, % of energy per macro, and evidence-based targets (protein g/kg, fiber)."""
    return queries.nutrition_summary(max(1, min(days, 90)))


@mcp.tool()
def get_workouts(days: int = 30, source: str | None = None) -> dict:
    """Workouts over the last `days` with per-type counts/minutes and sessions per week.
    source: optional 'kinetix' (gym strength sessions with exercises/sets/kg) or 'apple_health'
    (Apple Watch: runs, yoga, cardio with HR and distance)."""
    return queries.workouts(max(1, min(days, 365)), source)


@mcp.tool()
def get_weather(start_date: str | None = None, end_date: str | None = None) -> dict:
    """Daily weather in Brussels (Open-Meteo): min/max °C, precipitation, wind, summary.
    Defaults to the last 7 days + 3-day forecast. Useful for planning outdoor runs."""
    return queries.weather(start_date, end_date)


@mcp.tool()
def get_goals() -> list[dict]:
    """Active goals with weekly plan and progress toward the target (current vs baseline vs target)."""
    return queries.list_goals()


@mcp.tool()
def save_goal(title: str, metric: str | None = None, target_value: float | None = None, unit: str | None = None,
              deadline: str | None = None, weekly_plan: list[str] | None = None, rationale: str | None = None) -> dict:
    """Persist a goal the USER HAS APPROVED. Never call this without explicit user approval.
    metric (optional) must be a tracked metric so progress can be measured automatically."""
    return queries.save_goal({"title": title, "metric": metric, "target_value": target_value, "unit": unit,
                              "deadline": deadline, "weekly_plan": weekly_plan, "rationale": rationale})


if __name__ == "__main__":
    db.init_db()
    mcp.run(transport="stdio" if "--stdio" in sys.argv else "streamable-http")
