"""B4 — compute_vat: PURE. Categorised transactions → the 9 VAT boxes.

No LLM, no I/O, no clock — deterministic and exhaustively unit-tested. Every
figure HMRC ever sees originates here.

ASSUMPTION (v1): transaction amounts are VAT-INCLUSIVE (gross). Net and VAT are
derived by stripping the rate. Whether the client's CSV is gross or net is a real
domain question logged in BLOCKERS.md.

Rounding (v1): per-transaction VAT to the penny (ROUND_HALF_UP); box 6/7 net
totals to whole pounds. HMRC permits rounding down for boxes 6-9 — exact
convention is a BLOCKERS.md question for the accountant.

Scope (v1): UK domestic only. Box 2 (acquisitions) and boxes 8/9 (EC goods) are 0.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from mtd_agent.models import (
    CategorisedTransaction,
    Direction,
    VatBoxes,
    VatTreatment,
)

_PENNY = Decimal("0.01")
_POUND = Decimal("1")
_VATABLE = (VatTreatment.STANDARD, VatTreatment.REDUCED)
_RATES = {
    VatTreatment.STANDARD: Decimal("0.20"),
    VatTreatment.REDUCED: Decimal("0.05"),
    VatTreatment.ZERO: Decimal("0.00"),
}


def _net_and_vat(gross: Decimal, treatment: VatTreatment) -> tuple[Decimal, Decimal] | None:
    """Return (net, vat) at 2dp, or None if the transaction is out of scope."""
    if treatment == VatTreatment.OUTSIDE_SCOPE:
        return None
    if treatment == VatTreatment.EXEMPT:
        return gross.quantize(_PENNY, ROUND_HALF_UP), Decimal("0.00")
    rate = _RATES[treatment]
    net = (gross / (1 + rate)).quantize(_PENNY, ROUND_HALF_UP)
    vat = (gross - net).quantize(_PENNY, ROUND_HALF_UP)
    return net, vat


def compute_vat(categorised: list[CategorisedTransaction]) -> VatBoxes:
    box1 = Decimal("0.00")   # VAT due on sales
    box4 = Decimal("0.00")   # VAT reclaimed on purchases
    sales_net = Decimal("0.00")
    purchases_net = Decimal("0.00")

    for c in categorised:
        split = _net_and_vat(c.txn.amount, c.treatment)
        if split is None:
            continue  # outside scope — excluded entirely
        net, vat = split
        if c.txn.direction == Direction.SALE:
            sales_net += net
            if c.treatment in _VATABLE:
                box1 += vat
        else:
            purchases_net += net
            if c.treatment in _VATABLE:
                box4 += vat

    box1 = box1.quantize(_PENNY)
    box4 = box4.quantize(_PENNY)
    box2 = Decimal("0.00")
    box3 = box1 + box2
    box5 = abs(box3 - box4)

    return VatBoxes(
        box1_vat_due_sales=box1,
        box2_vat_due_acquisitions=box2,
        box3_total_vat_due=box3,
        box4_vat_reclaimed=box4,
        box5_net_vat_due=box5,
        box6_total_sales_ex_vat=int(sales_net.quantize(_POUND, ROUND_HALF_UP)),
        box7_total_purchases_ex_vat=int(purchases_net.quantize(_POUND, ROUND_HALF_UP)),
        box8_total_goods_supplied_ex_vat=0,
        box9_total_acquisitions_ex_vat=0,
    )


def compute_vat_flat_rate(
    categorised: list[CategorisedTransaction],
    flat_rate_percent: Decimal,
) -> VatBoxes:
    """Flat Rate Scheme (Phase B). PURE, like `compute_vat`.

    v1 assumptions (cf. skills/hmrc/.../flat-rate-scheme.md):
    - Flat-rate turnover = VAT-INCLUSIVE value of all in-scope sales (standard/reduced/zero;
      outside-scope excluded). FRS applies the percentage to gross turnover.
    - Box 1 = flat_rate_percent% of that turnover.
    - Box 4 = 0 — no input VAT reclaim under FRS (the capital-asset exception is deferred).
    - Box 6 = the VAT-inclusive turnover (an FRS quirk: Box 6 includes VAT here).
    - Box 7 = 0 — purchases are not reclaimed under FRS in v1.
    The percentage is a business attribute supplied by the caller, never computed here.
    """
    turnover = sum(
        (c.txn.amount for c in categorised
         if c.txn.direction == Direction.SALE and c.treatment != VatTreatment.OUTSIDE_SCOPE),
        Decimal("0"),
    )
    box1 = (flat_rate_percent / Decimal("100") * turnover).quantize(_PENNY, ROUND_HALF_UP)
    box4 = Decimal("0.00")
    box3 = box1
    box5 = abs(box3 - box4)
    return VatBoxes(
        box1_vat_due_sales=box1,
        box2_vat_due_acquisitions=Decimal("0.00"),
        box3_total_vat_due=box3,
        box4_vat_reclaimed=box4,
        box5_net_vat_due=box5,
        box6_total_sales_ex_vat=int(turnover.quantize(_POUND, ROUND_HALF_UP)),
        box7_total_purchases_ex_vat=0,
        box8_total_goods_supplied_ex_vat=0,
        box9_total_acquisitions_ex_vat=0,
    )


def compute_vat_cash(categorised: list[CategorisedTransaction]) -> VatBoxes:
    """Cash accounting (Phase B). PURE.

    Our input is bank/payment transactions, which are already cash-basis events (VAT
    accounted when money moves). The per-transaction box arithmetic is therefore identical
    to the standard computation — the accrual-vs-cash difference is *which* transactions
    fall in the period (payment vs invoice date), which is upstream of this maths and not
    represented in a single-period bank feed. Kept as a named, gated entry point so the
    scheme router has a real target; revisit if invoice-dated data is ever ingested.
    """
    return compute_vat(categorised)
