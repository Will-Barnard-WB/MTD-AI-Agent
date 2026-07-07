"""Public entrypoint for the vertical slice.

`run_pipeline` keeps its v1 signature + `PipelineResult` return, but now drives the
LangGraph `StateGraph` in `graph/build.py`. The flow and audit events are unchanged:

    ingest → extract → intake → completeness → compute → resolve_period → approval → submit

with an AuditEvent at every step, halting (nothing reaches HMRC) on incomplete inputs,
a missing open period, or a declined approval.

v2 A2: the `intake` node may `interrupt()` to clarify low-confidence categorisations.
This driver runs the graph, and while it is paused on an interrupt it asks the injected
`Questioner` for answers and resumes — so the HITL pause is checkpointer-backed, not a
blocking callback.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

from langgraph.types import Command

from mtd_agent.audit import AuditLogger
from mtd_agent.graph.build import PIPELINE_GRAPH, Deps
from mtd_agent.graph.state import PipelineResult
from mtd_agent.interfaces import HmrcVatClient
from mtd_agent.models import VatScheme
from mtd_agent.nodes.approval import Approver
from mtd_agent.nodes.extract import Categoriser
from mtd_agent.nodes.intake import AutoQuestioner, Gap, Questioner
from mtd_agent.nodes.routing import AutoSchemeChooser, SchemeChooser
from mtd_agent.reviewer import Reviewer, SkillSet


def run_pipeline(
    *,
    csv_path: str | Path,
    vrn: str,
    client: HmrcVatClient,
    categoriser: Categoriser,
    approver: Approver,
    questioner: Questioner | None = None,
    reviewer: Reviewer | None = None,
    scheme_chooser: SchemeChooser | None = None,
    tax_year: str = "2026-27",
    scheme: VatScheme | None = None,
    business_profile: str = "",
    flat_rate_percent: Decimal | None = None,
    finalised: bool = True,
    period_key: str | None = None,
    audit_dir: Path | None = None,
) -> PipelineResult:
    questioner = questioner or AutoQuestioner()
    scheme_chooser = scheme_chooser or AutoSchemeChooser()
    reviewer = reviewer or Reviewer(SkillSet.load(tax_year))
    run_id = uuid.uuid4().hex[:12]
    audit = AuditLogger(run_id) if audit_dir is None else AuditLogger(run_id, audit_dir)

    config = {"configurable": {
        "deps": Deps(client=client, categoriser=categoriser, approver=approver, reviewer=reviewer),
        "audit": audit,
        "flat_rate_percent": str(flat_rate_percent) if flat_rate_percent is not None else None,
        "run_id": run_id,
        "thread_id": run_id,   # required by the checkpointer
    }}
    initial = {
        "csv_path": str(csv_path),
        "vrn": vrn,
        "finalised": finalised,
        "period_key": period_key,
        "business_profile": business_profile,
    }
    if scheme is not None:               # explicit scheme skips classification
        initial["scheme"] = scheme

    final = PIPELINE_GRAPH.invoke(initial, config=config)
    # Drive any HITL interrupt(s) — the supervisor's scheme question and/or intake
    # clarifications — to completion. Each resume value is wrapped so it is never falsy
    # (LangGraph ignores a falsy resume).
    for _ in range(100):  # safety cap — well-formed HITL resolves in a few rounds
        if "__interrupt__" not in final:
            break
        payload = final["__interrupt__"][0].value
        if payload.get("ask") == "vat_scheme":
            resume = {"scheme": scheme_chooser.choose(payload)}
        else:  # intake clarification gaps
            gaps = [Gap(**g) for g in payload["gaps"]]
            resume = {"answers": questioner.answer(gaps)}
        final = PIPELINE_GRAPH.invoke(Command(resume=resume), config=config)
    else:
        raise RuntimeError("HITL did not resolve within 100 interrupt rounds")

    return PipelineResult(
        status=final["status"],
        run_id=run_id,
        audit_path=str(audit.path),
        boxes=final.get("boxes"),
        period_key=final.get("period_key"),
        receipt=final.get("receipt"),
        issues=final.get("issues", []),
    )
