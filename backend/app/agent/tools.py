"""Tool access for the agent: MCP first, in-process fallback.

Primary path: langchain-mcp-adapters → health-data MCP server (streamable HTTP). If the MCP server
is unreachable, the agent falls back to calling the same query functions in-process, so a crashed
sidecar degrades observability, not the user experience. `source` is reported in the trace.
"""
import logging

from langchain_core.tools import BaseTool, StructuredTool

from app.config import get_settings
from app.data import queries

log = logging.getLogger(__name__)
_tools: list[BaseTool] | None = None
_source = "none"


async def load_tools(force: bool = False) -> tuple[list[BaseTool], str]:
    global _tools, _source
    if _tools is not None and not force:
        return _tools, _source
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        client = MultiServerMCPClient({"health": {"url": get_settings().mcp_url, "transport": "streamable_http"}})
        _tools, _source = await client.get_tools(), "mcp"
    except Exception as exc:  # noqa: BLE001
        log.warning("MCP server unavailable (%s) — using in-process tools", exc)
        _tools, _source = _local_tools(), "in-process-fallback"
    return _tools, _source


def _local_tools() -> list[BaseTool]:
    def wrap(fn, name, desc):
        return StructuredTool.from_function(fn, name=name, description=desc)

    return [
        wrap(queries.body_composition_trend, "get_body_composition_trend", "Body metric trend. args: metric, days, source"),
        wrap(queries.latest_metrics, "get_latest_metrics", "Latest value of every tracked metric with 7-day change"),
        wrap(queries.strength_progress, "get_strength_progress", "Kinetix 1RM strength tests: first vs latest per exercise"),
        wrap(queries.cycle_status, "get_cycle_status", "Menstrual cycle day/phase on a date (default today)"),
        wrap(queries.nutrition_summary, "get_nutrition_summary", "Nutrition per day + averages + targets over `days`"),
        wrap(queries.workouts, "get_workouts", "Workouts over `days`, optional source kinetix|apple_health"),
        wrap(queries.weather, "get_weather", "Brussels daily weather between start and end date"),
        wrap(queries.list_goals, "get_goals", "Active goals with progress"),
        wrap(lambda title, metric=None, target_value=None, unit=None, deadline=None, weekly_plan=None, rationale=None:
             queries.save_goal(dict(title=title, metric=metric, target_value=target_value, unit=unit, deadline=deadline,
                                    weekly_plan=weekly_plan, rationale=rationale)),
             "save_goal", "Persist an approved goal"),
    ]


def reset_tools() -> None:
    global _tools
    _tools = None
