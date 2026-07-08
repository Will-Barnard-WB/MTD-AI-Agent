"""Step-by-step run driver for the console's live HITL (importable + testable).

`run_pipeline` drives every interrupt to completion using injected callbacks — great for
the CLI, wrong for a browser, which must render each question and wait for a click across
reruns. `RunSession` exposes the graph one interrupt at a time: `start()` → inspect
`pending` (the scheme question, intake gaps, or the approval derivation) → `resume(...)`
with the human's answer → repeat until `done`. State persists in the module-level
checkpointer keyed by `thread_id`, so it survives Streamlit reruns within a session.

This works with real deps (OpenAI categoriser + real HMRC client) or fakes — the class
doesn't care, which is what makes the HITL choreography testable without a browser.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from langgraph.types import Command

from mtd_agent.audit import AUDIT_DIR, AuditLogger
from mtd_agent.graph.build import PIPELINE_GRAPH, Deps
from mtd_agent.graph.state import Status
from mtd_agent.reviewer import Reviewer, SkillSet


class RunSession:
    """One live pipeline run, advanced interrupt-by-interrupt from a UI."""

    def __init__(self, *, config: dict, run_id: str, audit: AuditLogger, initial: dict) -> None:
        self._config = config
        self.run_id = run_id
        self.audit = audit
        self._initial = initial
        self._result: dict | None = None

    @classmethod
    def create(cls, *, csv_path, vrn, categoriser, client, reviewer: Reviewer | None = None,
               tax_year: str = "2026-27", scheme=None, business_profile: str = "",
               flat_rate_percent=None, finalised: bool = True, period_key=None,
               audit_dir: Path = AUDIT_DIR) -> RunSession:
        run_id = uuid.uuid4().hex[:12]
        audit = AuditLogger(run_id, audit_dir)
        reviewer = reviewer or Reviewer(SkillSet.load(tax_year))
        config = {"configurable": {
            "deps": Deps(client=client, categoriser=categoriser, reviewer=reviewer),
            "audit": audit,
            "flat_rate_percent": str(flat_rate_percent) if flat_rate_percent is not None else None,
            "run_id": run_id, "thread_id": run_id,
        }}
        initial = {"csv_path": str(csv_path), "vrn": vrn, "finalised": finalised,
                   "period_key": period_key, "business_profile": business_profile}
        if scheme is not None:
            initial["scheme"] = scheme
        return cls(config=config, run_id=run_id, audit=audit, initial=initial)

    def start(self) -> RunSession:
        self._result = PIPELINE_GRAPH.invoke(self._initial, config=self._config)
        return self

    def resume(self, value: dict) -> RunSession:
        # value is wrapped in a dict so it is always truthy (LangGraph ignores a falsy resume).
        self._result = PIPELINE_GRAPH.invoke(Command(resume=value), config=self._config)
        return self

    @property
    def pending(self) -> dict | None:
        """The current interrupt payload (what the UI must ask), or None when finished."""
        if self._result and "__interrupt__" in self._result:
            return self._result["__interrupt__"][0].value
        return None

    @property
    def done(self) -> bool:
        return self._result is not None and "__interrupt__" not in self._result

    @property
    def status(self) -> Status | None:
        return self._result.get("status") if self.done else None

    @property
    def result(self) -> dict | None:
        return self._result
