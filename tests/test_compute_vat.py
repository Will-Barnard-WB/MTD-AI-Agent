"""compute_vat — the pure core. Hand-computed fixtures → exact boxes."""

from datetime import date
from decimal import Decimal

from mtd_agent.models import (
    CategorisedTransaction,
    Direction,
    Transaction,
    VatTreatment,
)
from mtd_agent.nodes.compute_vat import compute_vat


def _cat(id, desc, amount, direction, treatment, conf=0.9) -> CategorisedTransaction:
    return CategorisedTransaction(
        txn=Transaction(id=id, date=date(2026, 1, 1), description=desc,
                        amount=Decimal(amount), direction=direction),
        treatment=treatment, category=desc, confidence=conf,
    )


def test_known_mixed_basket():
    cats = [
        _cat("S1", "consulting", "1200.00", Direction.SALE, VatTreatment.STANDARD),
        _cat("S2", "train", "100.00", Direction.SALE, VatTreatment.ZERO),
        _cat("P1", "office", "600.00", Direction.PURCHASE, VatTreatment.STANDARD),
        _cat("P2", "insurance", "50.00", Direction.PURCHASE, VatTreatment.EXEMPT),
        _cat("P3", "salary", "2000.00", Direction.PURCHASE, VatTreatment.OUTSIDE_SCOPE),
    ]
    b = compute_vat(cats)
    assert b.box1_vat_due_sales == Decimal("200.00")    # 1200 gross @20% -> 200 VAT
    assert b.box2_vat_due_acquisitions == Decimal("0.00")
    assert b.box3_total_vat_due == Decimal("200.00")
    assert b.box4_vat_reclaimed == Decimal("100.00")    # 600 gross @20% -> 100 VAT
    assert b.box5_net_vat_due == Decimal("100.00")      # |200 - 100|
    assert b.box6_total_sales_ex_vat == 1100            # 1000 net + 100 zero
    assert b.box7_total_purchases_ex_vat == 550         # 500 net + 50 exempt
    assert b.box8_total_goods_supplied_ex_vat == 0
    assert b.box9_total_acquisitions_ex_vat == 0


def test_outside_scope_is_fully_excluded():
    cats = [_cat("X", "salary", "5000.00", Direction.PURCHASE, VatTreatment.OUTSIDE_SCOPE)]
    b = compute_vat(cats)
    assert b.box4_vat_reclaimed == Decimal("0.00")
    assert b.box7_total_purchases_ex_vat == 0


def test_reduced_rate_vat():
    # 105 gross @5% -> net 100.00, vat 5.00
    cats = [_cat("R", "energy", "105.00", Direction.SALE, VatTreatment.REDUCED)]
    b = compute_vat(cats)
    assert b.box1_vat_due_sales == Decimal("5.00")
    assert b.box6_total_sales_ex_vat == 100


def test_net_vat_when_reclaim_exceeds_due():
    cats = [
        _cat("S", "sale", "120.00", Direction.SALE, VatTreatment.STANDARD),     # vat 20
        _cat("P", "big buy", "1200.00", Direction.PURCHASE, VatTreatment.STANDARD),  # vat 200
    ]
    b = compute_vat(cats)
    assert b.box3_total_vat_due == Decimal("20.00")
    assert b.box4_vat_reclaimed == Decimal("200.00")
    assert b.box5_net_vat_due == Decimal("180.00")   # absolute value, a refund
