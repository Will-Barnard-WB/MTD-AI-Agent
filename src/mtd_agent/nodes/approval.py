"""B5 — approval gate (HITL): an expert reviews the full derivation, then approves.

Built for a competent reviewer (CONTRACT.md §1.3): every box figure is shown with
the transactions behind it, plus anomaly flags. No submission happens without an
explicit approve. Prior-period deltas are a v2 enhancement (no prior data in v1).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel

from mtd_agent.models import CategorisedTransaction, VatBoxes, VatTreatment

_LOW_CONFIDENCE = 0.6
_LARGE_AMOUNT = Decimal("10000")


class Derivation(BaseModel):
    """Everything the reviewer needs to judge the return before submit."""

    boxes: VatBoxes
    box1_sources: list[str]      # txns contributing VAT on sales
    box4_sources: list[str]      # txns contributing VAT reclaimed
    excluded: list[str]          # outside-scope txns, surfaced not hidden
    anomalies: list[str]


def _line(c: CategorisedTransaction) -> str:
    return (f"{c.txn.id} | {c.txn.date} | {c.txn.description} | £{c.txn.amount} "
            f"| {c.treatment.value} | conf={c.confidence:.2f}")


def detect_anomalies(categorised: list[CategorisedTransaction]) -> list[str]:
    flags: list[str] = []
    for c in categorised:
        if c.confidence < _LOW_CONFIDENCE:
            flags.append(f"LOW CONFIDENCE ({c.confidence:.2f}): {c.txn.id} {c.txn.description}")
        if c.txn.amount >= _LARGE_AMOUNT:
            flags.append(f"LARGE AMOUNT (£{c.txn.amount}): {c.txn.id} {c.txn.description}")
        if c.treatment == VatTreatment.OUTSIDE_SCOPE:
            flags.append(f"EXCLUDED (outside scope): {c.txn.id} {c.txn.description}")
    return flags


def build_derivation(boxes: VatBoxes, categorised: list[CategorisedTransaction]) -> Derivation:
    vatable = (VatTreatment.STANDARD, VatTreatment.REDUCED)
    return Derivation(
        boxes=boxes,
        box1_sources=[_line(c) for c in categorised
                      if c.txn.direction.value == "sale" and c.treatment in vatable],
        box4_sources=[_line(c) for c in categorised
                      if c.txn.direction.value == "purchase" and c.treatment in vatable],
        excluded=[_line(c) for c in categorised if c.treatment == VatTreatment.OUTSIDE_SCOPE],
        anomalies=detect_anomalies(categorised),
    )


def _block(title: str, items: list[str]) -> list[str]:
    return [title, *([f"  {s}" for s in items] or ["  (none)"])]


def render(d: Derivation) -> str:
    b = d.boxes
    lines = [
        "VAT RETURN — REVIEW BEFORE SUBMIT",
        "=================================",
        f"Box 1  VAT due on sales .............. £{b.box1_vat_due_sales}",
        f"Box 2  VAT due on acquisitions ....... £{b.box2_vat_due_acquisitions}",
        f"Box 3  Total VAT due ................. £{b.box3_total_vat_due}",
        f"Box 4  VAT reclaimed ................. £{b.box4_vat_reclaimed}",
        f"Box 5  NET VAT due .................. £{b.box5_net_vat_due}",
        f"Box 6  Total sales ex VAT ........... £{b.box6_total_sales_ex_vat}",
        f"Box 7  Total purchases ex VAT ....... £{b.box7_total_purchases_ex_vat}",
        f"Box 8  Goods supplied to EC ......... £{b.box8_total_goods_supplied_ex_vat}",
        f"Box 9  Acquisitions from EC ......... £{b.box9_total_acquisitions_ex_vat}",
        "",
        *_block("Box 1 sources (VAT on sales):", d.box1_sources),
        *_block("Box 4 sources (VAT reclaimed):", d.box4_sources),
    ]
    if d.excluded:
        lines += ["Excluded (outside scope):", *[f"  {s}" for s in d.excluded]]
    if d.anomalies:
        lines += ["", "⚠ ANOMALIES:", *[f"  {a}" for a in d.anomalies]]
    return "\n".join(lines)


class Approver(Protocol):
    def approve(self, derivation: Derivation) -> bool: ...


class AutoApprover:
    """Non-interactive approver for tests and unattended demo runs."""

    def __init__(self, decision: bool = True) -> None:
        self._decision = decision

    def approve(self, derivation: Derivation) -> bool:
        return self._decision


class CLIApprover:
    """Prints the full derivation and asks a human to approve at the terminal."""

    def approve(self, derivation: Derivation) -> bool:
        print(render(derivation))
        answer = input("\nSubmit this return to HMRC? [y/N] ").strip().lower()
        return answer in ("y", "yes")
