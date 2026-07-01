"""Public entrypoint for the vertical slice.

`run_pipeline` keeps its v1 signature + `PipelineResult` return, but now drives the
LangGraph `StateGraph` in `graph/build.py`. The flow and audit events are unchanged:

    ingest → extract → completeness → compute → resolve_period → approval → submit

with an AuditEvent at every step, halting (nothing reaches HMRC) on incomplete inputs,
a missing open period, or a declined approval.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from mtd_agent.audit import AuditLogger
from mtd_agent.graph.build import PIPELINE_GRAPH, Deps
from mtd_agent.graph.state import PipelineResult
from mtd_agent.interfaces import HmrcVatClient
from mtd_agent.nodes.approval import Approver
from mtd_agent.nodes.extract import Categoriser


def run_pipeline(
    *,
    csv_path: str | Path,
    vrn: str,
    client: HmrcVatClient,
    categoriser: Categoriser,
    approver: Approver,
    finalised: bool = True,
    period_key: str | None = None,
    audit_dir: Path | None = None,
) -> PipelineResult:
    run_id = uuid.uuid4().hex[:12]
    audit = AuditLogger(run_id) if audit_dir is None else AuditLogger(run_id, audit_dir)

    config = {"configurable": {
        "deps": Deps(client=client, categoriser=categoriser, approver=approver),
        "audit": audit,
        "run_id": run_id,
    }}
    initial = {
        "csv_path": str(csv_path),
        "vrn": vrn,
        "finalised": finalised,
        "period_key": period_key,
    }
    final = PIPELINE_GRAPH.invoke(initial, config=config)

    return PipelineResult(
        status=final["status"],
        run_id=run_id,
        audit_path=str(audit.path),
        boxes=final.get("boxes"),
        period_key=final.get("period_key"),
        receipt=final.get("receipt"),
        issues=final.get("issues", []),
    )
