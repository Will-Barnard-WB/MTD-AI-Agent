"""LangSmith tracing activation logic (env only — no network)."""

from mtd_agent.config import Settings, configure_tracing

_BASE = dict(
    hmrc_client_id="", hmrc_client_secret="", hmrc_redirect_uri="",
    hmrc_base_url="https://test-api.service.hmrc.gov.uk", hmrc_test_vrn="",
    openai_api_key="", extraction_model="gpt-4o-mini",
)


def _settings(**kw) -> Settings:
    return Settings(**_BASE, langsmith_api_key=kw.get("key", ""),
                    langsmith_tracing=kw.get("tracing", False),
                    langsmith_project=kw.get("project", "mtd-agent"),
                    langsmith_endpoint=kw.get("endpoint", ""))


def test_off_when_not_opted_in(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    assert configure_tracing(_settings(tracing=False, key="ls-123")) is False


def test_off_when_no_key(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    assert configure_tracing(_settings(tracing=True, key="")) is False


def test_on_sets_env(monkeypatch):
    for var in ("LANGSMITH_TRACING", "LANGSMITH_API_KEY", "LANGSMITH_PROJECT", "LANGSMITH_ENDPOINT"):
        monkeypatch.delenv(var, raising=False)
    ok = configure_tracing(_settings(tracing=True, key="ls-abc", project="mtd-agent",
                                     endpoint="https://eu.api.smith.langchain.com"))
    assert ok is True
    import os
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "ls-abc"
    assert os.environ["LANGSMITH_PROJECT"] == "mtd-agent"
    assert os.environ["LANGSMITH_ENDPOINT"] == "https://eu.api.smith.langchain.com"


def test_load_parses_tracing_bool(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "TRUE")
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls-xyz")
    monkeypatch.setenv("LANGSMITH_PROJECT", "custom-proj")
    s = Settings.load()
    assert s.langsmith_tracing is True
    assert s.langsmith_api_key == "ls-xyz"
    assert s.langsmith_project == "custom-proj"
