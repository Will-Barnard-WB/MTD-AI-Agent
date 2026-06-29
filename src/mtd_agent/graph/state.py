"""Pipeline state + result types.

NOTE (Stream B, v1): the spine is implemented as an explicit orchestrator
(`pipeline.run_pipeline`) rather than a LangGraph StateGraph. The nodes are kept
pure and individually testable so a LangGraph wrapper can be layered on later
(HITL via interrupt + checkpointer) without changing node logic. This deviation
from PLAN.md is intentional for a runnable, fully-tested v1 — flagged in LOG.md
for the reviewer. It is internal to Stream B and touches no shared surface.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from mtd_agent.models import SubmitReceipt, VatBoxes


class Status(str, Enum):
    SUBMITTED = "submitted"
    DECLINED = "declined"          # human did not approve
    INCOMPLETE = "incomplete"      # completeness guard failed
    NO_OPEN_PERIOD = "no_open_period"


class PipelineResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    status: Status
    run_id: str
    audit_path: str
    boxes: VatBoxes | None = None
    period_key: str | None = None
    receipt: SubmitReceipt | None = None
    issues: list[str] = []
