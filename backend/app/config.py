"""Central configuration, loaded from environment / .env (see .env.example)."""
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

# LangSmith / OpenAI SDKs read os.environ directly, so export .env there too.
load_dotenv(ROOT / ".env")
if "TODO" in os.environ.get("LANGSMITH_API_KEY", "TODO"):
    # No real key yet: disable tracing instead of spamming 401s.
    os.environ["LANGSMITH_TRACING"] = "false"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    openai_api_key: str = ""
    primary_model: str = "gpt-4.1"
    fast_model: str = "gpt-4.1-mini"
    fallback_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    daily_budget_usd: float = 2.0

    gen_temperature: float = 0.3
    gen_top_p: float = 1.0
    gen_max_tokens: int = 900

    withings_client_id: str = ""
    withings_client_secret: str = ""
    withings_redirect_uri: str = "http://localhost:8000/withings/callback"

    db_path: str = "data/health.db"
    qdrant_url: str = ""
    qdrant_path: str = "data/qdrant"
    qdrant_api_key: str = ""

    mcp_url: str = "http://localhost:8001/mcp"
    frontend_origin: str = "http://localhost:3000"
    user_name: str = "Damilya"
    home_lat: float = 50.85
    home_lon: float = 4.35
    home_tz: str = "Europe/Brussels"  # all timestamps from all sources are normalised to this timezone

    def abs_path(self, p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else ROOT / path

    @property
    def tz(self):
        from zoneinfo import ZoneInfo

        return ZoneInfo(self.home_tz)

    @property
    def has_openai(self) -> bool:
        return self.openai_api_key.startswith("sk-") and "TODO" not in self.openai_api_key

    @property
    def has_withings(self) -> bool:
        return bool(self.withings_client_id) and "TODO" not in self.withings_client_id


@lru_cache
def get_settings() -> Settings:
    return Settings()
