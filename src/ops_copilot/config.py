"""Centralized, env-driven settings. Single source of truth for configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _truthy(val: str | None) -> bool:
    return str(val or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # ── LLM ──────────────────────────────────────────────────────────────
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    google_model: str = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
    llm_timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "20"))
    llm_retries: int = int(os.getenv("LLM_RETRIES", "2"))
    llm_stream: bool = field(default_factory=lambda: _truthy(os.getenv("LLM_STREAM", "true")))

    # ── Guardrails ───────────────────────────────────────────────────────
    guard_llm_judge: bool = field(default_factory=lambda: _truthy(os.getenv("GUARD_LLM_JUDGE", "true")))
    goal_max_chars: int = int(os.getenv("GOAL_MAX_CHARS", "600"))

    # ── LangSmith (observability + evals) ────────────────────────────────
    langsmith_api_key: str = os.getenv("LANGSMITH_API_KEY", "")
    langsmith_project: str = os.getenv("LANGSMITH_PROJECT", "ops-copilot")
    langsmith_tracing: bool = field(
        default_factory=lambda: _truthy(os.getenv("LANGSMITH_TRACING", "true"))
        and bool(os.getenv("LANGSMITH_API_KEY"))
    )

    # ── Storage ──────────────────────────────────────────────────────────
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", _PROJECT_ROOT / "data")))

    # ── Server ───────────────────────────────────────────────────────────
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    auth_api_key: str = os.getenv("AUTH_API_KEY", "")

    # ── Workflow limits ──────────────────────────────────────────────────
    planning_timeout_s: float = float(os.getenv("PLANNING_TIMEOUT_S", "120"))
    execution_timeout_s: float = float(os.getenv("EXECUTION_TIMEOUT_S", "60"))
    launch_rate_limit_per_min: int = int(os.getenv("LAUNCH_RATE_LIMIT_PER_MIN", "10"))
    sse_heartbeat_s: float = float(os.getenv("SSE_HEARTBEAT_S", "30"))

    # ── Calendar booking ─────────────────────────────────────────────────
    booking_max_date_shifts: int = int(os.getenv("BOOKING_MAX_DATE_SHIFTS", "2"))

    @property
    def app_db_path(self) -> Path:
        return self.data_dir / "ops_copilot.db"

    @property
    def checkpoint_db_path(self) -> Path:
        return self.data_dir / "checkpoints.db"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.google_api_key) and self.google_api_key != "your_gemini_api_key_here"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()

# LangSmith is enabled purely through env vars read by langchain/langgraph.
if settings.langsmith_tracing:
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)
