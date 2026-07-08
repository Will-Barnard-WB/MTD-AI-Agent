"""Data layer for the MTD console (importable + testable, no Streamlit).

A LangSmith-style *lens* over the append-only audit trail — it reads `audit/*.jsonl` and
derives run summaries and per-node traces (with timing from the events' own timestamps).
Read-only: it never writes to the trail. The Streamlit app (`app.py`) is a thin UI over
these functions, so all logic stays testable without a browser.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mtd_agent.audit import AUDIT_DIR, AuditLogger
from mtd_agent.models import AuditEvent

# Terminal status steps → a human-readable run status.
_STATUS = {
    "submitted": "submitted",
    "declined": "declined",
    "completeness_failed": "incomplete",
    "no_open_period": "no_open_period",
}


@dataclass
class TraceStep:
    step: str
    payload: dict
    ts: str
    duration_ms: int | None   # gap to the next event (LangSmith-style span timing)


@dataclass
class RunSummary:
    run_id: str
    status: str
    scheme: str | None
    period_key: str | None
    net_vat: str | None
    n_txns: int | None
    warnings: int          # reviewer comments flagged
    started: str | None
    duration_ms: int | None
    n_events: int


def _events(run_id: str, audit_dir: Path) -> list[AuditEvent]:
    return AuditLogger(run_id, audit_dir).read_all()


def _first(events: list[AuditEvent], step: str) -> AuditEvent | None:
    return next((e for e in events if e.step == step), None)


def summarise(run_id: str, audit_dir: Path = AUDIT_DIR) -> RunSummary:
    events = _events(run_id, audit_dir)
    status = next((_STATUS[e.step] for e in reversed(events) if e.step in _STATUS), "in_progress")
    compute = _first(events, "compute_vat")
    ingest = _first(events, "ingest")
    period = _first(events, "period_resolved")
    reviewed = _first(events, "reviewed")
    started = events[0].ts.isoformat() if events else None
    duration = _span_ms(events[0].ts, events[-1].ts) if len(events) >= 2 else None
    return RunSummary(
        run_id=run_id,
        status=status,
        scheme=(compute.payload.get("scheme") if compute else None),
        period_key=(period.payload.get("period_key") if period else None),
        net_vat=(str(compute.payload.get("box5_net_vat_due")) if compute else None),
        n_txns=(ingest.payload.get("count") if ingest else None),
        warnings=(len(reviewed.payload.get("comments", [])) if reviewed else 0),
        started=started,
        duration_ms=duration,
        n_events=len(events),
    )


def list_runs(audit_dir: Path = AUDIT_DIR) -> list[RunSummary]:
    """All runs, newest first (by first-event timestamp)."""
    if not Path(audit_dir).is_dir():
        return []
    summaries = [summarise(p.stem, audit_dir) for p in Path(audit_dir).glob("*.jsonl")]
    return sorted(summaries, key=lambda s: s.started or "", reverse=True)


def _span_ms(a, b) -> int:
    return int((b - a).total_seconds() * 1000)


def load_trace(run_id: str, audit_dir: Path = AUDIT_DIR) -> list[TraceStep]:
    """The per-node trace for a run, with each step's duration = gap to the next event."""
    events = _events(run_id, audit_dir)
    steps: list[TraceStep] = []
    for i, e in enumerate(events):
        nxt = events[i + 1].ts if i + 1 < len(events) else None
        steps.append(TraceStep(
            step=e.step, payload=e.payload, ts=e.ts.isoformat(),
            duration_ms=(_span_ms(e.ts, nxt) if nxt else None),
        ))
    return steps


# Colour hints for the trace UI, keyed by event family.
STEP_FAMILY: dict[str, str] = {
    "scheme_resolved": "supervisor", "ingest": "io",
    "guardrails_flagged": "guardrail", "guardrails_ok": "guardrail",
    "extract": "llm", "intake_clarified": "hitl", "intake_no_questions": "hitl",
    "completeness_ok": "check", "completeness_failed": "halt",
    "compute_vat": "compute", "period_resolved": "io", "no_open_period": "halt",
    "reviewed": "reviewer", "reviewer_guardrail": "guardrail",
    "approved": "hitl", "declined": "halt", "submitted": "submit",
}


def family(step: str) -> str:
    return STEP_FAMILY.get(step, "other")
