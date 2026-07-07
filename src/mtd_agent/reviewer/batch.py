"""Batch reviewer (Phase C3) — sweep historical audit logs for anomalies/patterns.

Same read-only reviewer engine as the real-time approval-view path, run over the
`extract` event of every run in an audit directory. Because `extract` records the
(sanitised) description + assigned treatment, a run can be re-reviewed from its audit
trail alone — no re-ingest, no re-running the model. Produces a cross-run report of
cited comments and the most-flagged rules. Read-only: it reads JSONL, writes nothing.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel

from mtd_agent.audit import AUDIT_DIR, AuditLogger
from mtd_agent.models import CategorisedTransaction, Direction, Transaction, VatTreatment
from mtd_agent.reviewer.reviewer import ReviewComment, Reviewer
from mtd_agent.reviewer.skills import SkillSet

# Terminal status steps, newest-wins, to label a run in the report.
_STATUS_STEPS = {"submitted", "declined", "completeness_failed", "no_open_period"}


class RunReview(BaseModel):
    run_id: str
    status: str | None
    comments: list[ReviewComment]


class BatchReport(BaseModel):
    runs_reviewed: int
    runs_with_warnings: int
    total_comments: int
    by_citation: dict[str, int]        # citation -> how many times flagged
    per_run: list[RunReview]


def _reconstruct(extract_payload: dict) -> list[CategorisedTransaction]:
    """Rebuild the minimum a reviewer needs (description + treatment) from an extract event.
    Amount/date/direction are placeholders — the reviewer only reads description + treatment."""
    out: list[CategorisedTransaction] = []
    for item in extract_payload.get("categorised", []):
        txn = Transaction(id=item["id"], date=date(2000, 1, 1),
                          description=item.get("description", ""),
                          amount=Decimal("0"), direction=Direction.SALE)
        out.append(CategorisedTransaction(txn=txn, treatment=VatTreatment(item["treatment"]),
                                          category="", confidence=item.get("confidence", 1.0)))
    return out


def review_audit_dir(
    audit_dir: Path = AUDIT_DIR,
    tax_year: str = "2026-27",
    reviewer: Reviewer | None = None,
) -> BatchReport:
    reviewer = reviewer or Reviewer(SkillSet.load(tax_year))
    per_run: list[RunReview] = []
    by_citation: dict[str, int] = {}
    total = 0

    for path in sorted(audit_dir.glob("*.jsonl")):
        events = AuditLogger(path.stem, audit_dir).read_all()
        extract = next((e for e in events if e.step == "extract"), None)
        if extract is None:
            continue
        status = next((e.step for e in reversed(events) if e.step in _STATUS_STEPS), None)
        comments = reviewer.review(_reconstruct(extract.payload))
        per_run.append(RunReview(run_id=path.stem, status=status, comments=comments))
        for c in comments:
            by_citation[c.citation] = by_citation.get(c.citation, 0) + 1
            total += 1

    return BatchReport(
        runs_reviewed=len(per_run),
        runs_with_warnings=sum(1 for r in per_run if r.comments),
        total_comments=total,
        by_citation=dict(sorted(by_citation.items(), key=lambda kv: kv[1], reverse=True)),
        per_run=per_run,
    )


def render_report(report: BatchReport) -> str:
    lines = [
        "BATCH REVIEW — historical audit logs",
        "====================================",
        f"runs reviewed:      {report.runs_reviewed}",
        f"runs with warnings: {report.runs_with_warnings}",
        f"total comments:     {report.total_comments}",
    ]
    if report.by_citation:
        lines += ["", "Most-flagged rules:"]
        lines += [f"  {cite:<26} {n}" for cite, n in report.by_citation.items()]
    flagged = [r for r in report.per_run if r.comments]
    if flagged:
        lines += ["", "Per run:"]
        for r in flagged:
            lines.append(f"  {r.run_id} ({r.status or 'unknown'}):")
            lines += [f"    - {c.message}  [skill: {c.citation}]" for c in r.comments]
    return "\n".join(lines)
