"""The pipeline as a LangGraph `StateGraph` (v2 A1).

Wraps the v1 pure nodes unchanged — LangGraph orchestrates control flow only
(CONTRACT.md §8). Runtime dependencies (HMRC client, categoriser, approver, audit
logger) are passed in the run `config` under `configurable`, so `GraphState` stays
serializable for the checkpointer that A2's HITL interrupts will use.

Flow (early-exits go straight to END, nothing reaches HMRC on those paths):

    ingest → extract → completeness ─┬─(incomplete)─────────────► END
                                     └─► compute → resolve_period ─┬─(no period)─► END
                                                                   └─► approval ─┬─(declined)─► END
                                                                                 └─► submit ─► END
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from mtd_agent.audit import AuditLogger
from mtd_agent.interfaces import HmrcVatClient
from mtd_agent.models import ObligationStatus, VatReturnPayload
from mtd_agent.nodes import compute_vat, completeness, extract, ingest, submit
from mtd_agent.nodes.approval import Approver, build_derivation
from mtd_agent.nodes.extract import Categoriser
from mtd_agent.graph.state import GraphState, Status

# HMRC caps the obligations query window at 366 days — keep it legal.
_OBLIGATION_WINDOW_DAYS = 180


@dataclass
class Deps:
    """Runtime dependencies for a single run — passed via config, not graph state."""

    client: HmrcVatClient
    categoriser: Categoriser
    approver: Approver


def _deps(config: RunnableConfig) -> Deps:
    return config["configurable"]["deps"]


def _audit(config: RunnableConfig) -> AuditLogger:
    return config["configurable"]["audit"]


# --------------------------------------------------------------------------- #
# Nodes (thin wrappers over the pure v1 functions)
# --------------------------------------------------------------------------- #


def _ingest(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    txns = ingest.load_transactions(state["csv_path"])
    _audit(config).emit("ingest", {"count": len(txns), "csv": str(state["csv_path"])})
    return {"txns": txns}


def _extract(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    categorised = extract.categorise(state["txns"], _deps(config).categoriser)
    _audit(config).emit("extract", {"categorised": [
        {"id": c.txn.id, "treatment": c.treatment.value, "confidence": c.confidence}
        for c in categorised
    ]})
    return {"categorised": categorised}


def _completeness(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    issues = completeness.check_completeness(state["txns"], state["categorised"])
    audit = _audit(config)
    if issues:
        audit.emit("completeness_failed", {"issues": issues})
        return {"issues": issues, "status": Status.INCOMPLETE}
    audit.emit("completeness_ok", {})
    return {"issues": []}


def _compute(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    boxes = compute_vat.compute_vat(state["categorised"])
    _audit(config).emit("compute_vat", boxes.model_dump(mode="json"))
    return {"boxes": boxes}


def _resolve_period(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    audit = _audit(config)
    period_key = state.get("period_key")
    if period_key is None:
        today = date.today()
        obligations = _deps(config).client.get_obligations(
            state["vrn"],
            from_=today - timedelta(days=_OBLIGATION_WINDOW_DAYS),
            to=today + timedelta(days=_OBLIGATION_WINDOW_DAYS),
            status=ObligationStatus.OPEN,
        )
        if not obligations:
            audit.emit("no_open_period", {})
            return {"status": Status.NO_OPEN_PERIOD}
        period_key = obligations[0].period_key
    audit.emit("period_resolved", {"period_key": period_key})
    return {"period_key": period_key}


def _approval(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    audit = _audit(config)
    derivation = build_derivation(state["boxes"], state["categorised"])
    if not _deps(config).approver.approve(derivation):
        audit.emit("declined", {"period_key": state["period_key"]})
        return {"status": Status.DECLINED}
    audit.emit("approved", {"period_key": state["period_key"], "anomalies": derivation.anomalies})
    return {}


def _submit(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    payload = VatReturnPayload.from_boxes(
        period_key=state["period_key"], boxes=state["boxes"], finalised=state["finalised"],
    )
    receipt = submit.submit_return(_deps(config).client, state["vrn"], payload)
    _audit(config).emit(
        "submitted", {"period_key": state["period_key"], "form_bundle_number": receipt.form_bundle_number},
    )
    return {"receipt": receipt, "status": Status.SUBMITTED}


# --------------------------------------------------------------------------- #
# Graph wiring
# --------------------------------------------------------------------------- #


def _after_completeness(state: GraphState) -> str:
    return "end" if state.get("status") == Status.INCOMPLETE else "compute"


def _after_resolve(state: GraphState) -> str:
    return "end" if state.get("status") == Status.NO_OPEN_PERIOD else "approval"


def _after_approval(state: GraphState) -> str:
    return "end" if state.get("status") == Status.DECLINED else "submit"


def build_pipeline_graph():
    """Compile the pipeline StateGraph. Compiled once and reused (deps come per-run
    via config); a checkpointer is added in A2 when HITL interrupts land."""
    g = StateGraph(GraphState)
    g.add_node("ingest", _ingest)
    g.add_node("extract", _extract)
    g.add_node("completeness", _completeness)
    g.add_node("compute", _compute)
    g.add_node("resolve_period", _resolve_period)
    g.add_node("approval", _approval)
    g.add_node("submit", _submit)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "extract")
    g.add_edge("extract", "completeness")
    g.add_conditional_edges("completeness", _after_completeness, {"compute": "compute", "end": END})
    g.add_edge("compute", "resolve_period")
    g.add_conditional_edges("resolve_period", _after_resolve, {"approval": "approval", "end": END})
    g.add_conditional_edges("approval", _after_approval, {"submit": "submit", "end": END})
    g.add_edge("submit", END)
    return g.compile()


PIPELINE_GRAPH = build_pipeline_graph()
