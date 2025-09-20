import os
from typing import List


def get_env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v is not None else default


VERSION = "0.1.0"

# Paths
FILE_FLIGHTS = get_env("FILE_FLIGHTS", "flights_normalized.csv")
FILE_DAILY = get_env("FILE_DAILY", "daily_aggregates.csv")
FILE_FORECAST = get_env("FILE_FORECAST", "forecast_14d.csv")
FILE_QA = get_env("FILE_QA", "qa_issues.csv")

# API
API_PORT = int(get_env("API_PORT", "8000"))
API_HOST = get_env("API_HOST", "0.0.0.0")
API_TOKEN = get_env("API_TOKEN")  # Minimal auth via static Bearer token

# CORS
_cors = get_env("CORS_ORIGINS", "*")
if _cors == "*" or not _cors:
    CORS_ORIGINS: List[str] | str = "*"
else:
    CORS_ORIGINS = [x.strip() for x in _cors.split(",") if x.strip()]

# AI (optional)
AI_API_BASE = get_env("AI_API_BASE") or get_env("DEEPSEEK_API_BASE") or get_env("OPENAI_BASE_URL")
AI_API_KEY = get_env("AI_API_KEY") or get_env("DEEPSEEK_API_KEY") or get_env("OPENAI_API_KEY")
AI_MODEL = get_env("AI_MODEL") or get_env("DEEPSEEK_MODEL") or "deepseek-chat"
AI_PROVIDER = get_env("AI_PROVIDER", "openai-compatible")
AI_TIMEOUT = int(get_env("AI_TIMEOUT", "20"))
