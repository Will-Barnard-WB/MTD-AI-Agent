"""Configuration + the sandbox guard.

Two jobs:
1. Load settings from .env (names only live in .env.example).
2. Enforce SANDBOX-ONLY (CONTRACT.md §1.6) — a single chokepoint that refuses
   any HMRC base URL that isn't the sandbox host.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

SANDBOX_HOST = "test-api.service.hmrc.gov.uk"


def assert_sandbox(base_url: str) -> str:
    """Refuse anything that isn't the HMRC sandbox host. Call before any HMRC I/O."""
    from urllib.parse import urlparse

    host = urlparse(base_url).hostname or ""
    if host != SANDBOX_HOST:
        raise RuntimeError(
            f"Refusing non-sandbox HMRC host {host!r}. v1 is sandbox-only "
            f"(expected {SANDBOX_HOST}). See CONTRACT.md §1.6."
        )
    return base_url


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    hmrc_client_id: str
    hmrc_client_secret: str
    hmrc_redirect_uri: str
    hmrc_base_url: str
    hmrc_test_vrn: str
    openai_api_key: str
    extraction_model: str
    # LangSmith observability (opt-in). The project auto-creates on the first trace.
    langsmith_api_key: str
    langsmith_tracing: bool
    langsmith_project: str
    langsmith_endpoint: str

    @classmethod
    def load(cls) -> "Settings":
        """Read settings from the environment. Does not require secrets at import
        time — call this only where real HMRC/LLM access is needed (so tests and
        Phase-0 imports stay credential-free)."""
        base_url = os.environ.get("HMRC_BASE_URL", f"https://{SANDBOX_HOST}")
        assert_sandbox(base_url)
        return cls(
            hmrc_client_id=os.environ.get("HMRC_CLIENT_ID", ""),
            hmrc_client_secret=os.environ.get("HMRC_CLIENT_SECRET", ""),
            hmrc_redirect_uri=os.environ.get("HMRC_REDIRECT_URI", ""),
            hmrc_base_url=base_url,
            hmrc_test_vrn=os.environ.get("HMRC_TEST_VRN", ""),
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            extraction_model=os.environ.get("EXTRACTION_MODEL", "gpt-4o-mini"),
            langsmith_api_key=os.environ.get("LANGSMITH_API_KEY", ""),
            langsmith_tracing=_truthy(os.environ.get("LANGSMITH_TRACING", "")),
            langsmith_project=os.environ.get("LANGSMITH_PROJECT", "mtd-agent"),
            langsmith_endpoint=os.environ.get("LANGSMITH_ENDPOINT", ""),
        )


def configure_tracing(settings: "Settings | None" = None) -> bool:
    """Activate LangSmith tracing if it's opted-in and a key is present. Idempotent and
    safe to call always — a no-op otherwise. LangGraph auto-traces the graph nodes and
    the (wrapped) OpenAI categoriser call nests underneath. Returns True if active.

    Setup: create an API key in your LangSmith account, then in .env set
    `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY=...` (and optionally `LANGSMITH_PROJECT`).
    """
    settings = settings or Settings.load()
    if not (settings.langsmith_tracing and settings.langsmith_api_key):
        return False
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
    os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
    if settings.langsmith_endpoint:
        os.environ.setdefault("LANGSMITH_ENDPOINT", settings.langsmith_endpoint)
    return True
