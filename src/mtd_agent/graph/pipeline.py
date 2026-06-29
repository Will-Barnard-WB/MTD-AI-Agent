"""The vertical slice, wired end to end.

ingest → extract → completeness → compute_vat → approval → submit, with an
AuditEvent emitted at every step. Halts on incomplete inputs, a missing open
period, or a declined approval — nothing reaches HMRC in those cases.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from pathlib import Path

from mtd_agent.audit import AuditLogger
from mtd_agent.interfaces import HmrcVatClient
from mtd_agent.models import ObligationStatus, VatReturnPayload
from mtd_agent.nodes import compute_vat, completeness, extract, ingest, submit
from mtd_agent.nodes.approval import Approver, build_derivation
from mtd_agent.nodes.extract import Categoriser
from mtd_agent.graph.state import PipelineResult, Status


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

    # B1 — ingest
    txns = ingest.load_transactions(csv_path)
    audit.emit("ingest", {"count": len(txns), "csv": str(csv_path)})

    # B2 — extract (the only LLM call)
    categorised = extract.categorise(txns, categoriser)
    audit.emit("extract", {"categorised": [
        {"id": c.txn.id, "treatment": c.treatment.value, "confidence": c.confidence}
        for c in categorised
    ]})

    # B3 — completeness guard
    issues = completeness.check_completeness(txns, categorised)
    if issues:
        audit.emit("completeness_failed", {"issues": issues})
        return PipelineResult(status=Status.INCOMPLETE, run_id=run_id,
                              audit_path=str(audit.path), issues=issues)
    audit.emit("completeness_ok", {})

    # B4 — compute (pure)
    boxes = compute_vat.compute_vat(categorised)
    audit.emit("compute_vat", boxes.model_dump(mode="json"))

    # Resolve the open obligation period if not supplied.
    if period_key is None:
        today = date.today()
        obligations = client.get_obligations(
            vrn, from_=today - timedelta(days=365), to=today + timedelta(days=365),
            status=ObligationStatus.OPEN,
        )
        if not obligations:
            audit.emit("no_open_period", {})
            return PipelineResult(status=Status.NO_OPEN_PERIOD, run_id=run_id,
                                  audit_path=str(audit.path), boxes=boxes)
        period_key = obligations[0].period_key
    audit.emit("period_resolved", {"period_key": period_key})

    # B5 — approval gate (HITL)
    derivation = build_derivation(boxes, categorised)
    if not approver.approve(derivation):
        audit.emit("declined", {"period_key": period_key})
        return PipelineResult(status=Status.DECLINED, run_id=run_id,
                              audit_path=str(audit.path), boxes=boxes, period_key=period_key)
    audit.emit("approved", {"period_key": period_key, "anomalies": derivation.anomalies})

    # B6 — submit (idempotent in the client)
    payload = VatReturnPayload.from_boxes(period_key=period_key, boxes=boxes, finalised=finalised)
    receipt = submit.submit_return(client, vrn, payload)
    audit.emit("submitted", {"period_key": period_key,
                             "form_bundle_number": receipt.form_bundle_number})

    return PipelineResult(status=Status.SUBMITTED, run_id=run_id, audit_path=str(audit.path),
                          boxes=boxes, period_key=period_key, receipt=receipt)
