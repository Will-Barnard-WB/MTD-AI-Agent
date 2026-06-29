"""B3 — completeness guard: deterministic, not the model's judgement.

Returns a list of issues. Empty list = good to proceed. The pipeline halts on any
issue rather than computing a return from incomplete inputs (CONTRACT.md §1).
"""

from __future__ import annotations

from mtd_agent.models import CategorisedTransaction, Transaction


def check_completeness(
    txns: list[Transaction],
    categorised: list[CategorisedTransaction],
) -> list[str]:
    issues: list[str] = []

    cat_ids = {c.txn.id for c in categorised}
    missing = [t.id for t in txns if t.id not in cat_ids]
    if missing:
        issues.append(f"{len(missing)} transaction(s) not categorised: {missing[:5]}")

    if len(cat_ids) != len(categorised):
        issues.append("Duplicate categorisations for the same transaction id")

    return issues
