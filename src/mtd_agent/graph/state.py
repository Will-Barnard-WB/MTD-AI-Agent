"""Pipeline state + result types.

v2: the spine is a LangGraph `StateGraph` (see `graph/build.py`). `GraphState` is the
mutable channel dict threaded through the graph; the pure nodes are unchanged and still
individually testable — LangGraph orchestrates control flow only (CONTRACT.md §8). Runtime
dependencies (client/categoriser/approver/audit) travel in the run `config`, never in state,
so state stays serializable for the checkpointer that HITL interrupts (A2) will use.
`PipelineResult` remains the public return shape of `run_pipeline`.
"""

from __future__ import annotations

from enum import Enum
from typing import TypedDict

from pydantic import BaseModel, ConfigDict

from mtd_agent.models import CategorisedTransaction, SubmitReceipt, Transaction, VatBoxes


class Status(str, Enum):
    SUBMITTED = "submitted"
    DECLINED = "declined"          # human did not approve
    INCOMPLETE = "incomplete"      # completeness guard failed
    NO_OPEN_PERIOD = "no_open_period"


class GraphState(TypedDict, total=False):
    """Mutable channels threaded through the pipeline graph. Serializable data only —
    dependencies live in the run config (see `graph/build.py`)."""

    # inputs
    csv_path: str
    vrn: str
    finalised: bool
    period_key: str | None
    # working data produced by nodes
    txns: list[Transaction]
    categorised: list[CategorisedTransaction]
    issues: list[str]
    boxes: VatBoxes
    receipt: SubmitReceipt
    status: Status


class PipelineResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    status: Status
    run_id: str
    audit_path: str
    boxes: VatBoxes | None = None
    period_key: str | None = None
    receipt: SubmitReceipt | None = None
    issues: list[str] = []
