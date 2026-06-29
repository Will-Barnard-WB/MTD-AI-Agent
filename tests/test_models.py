"""VatBoxes invariants — a compute bug that breaks box3/box5 must fail fast."""

from decimal import Decimal

import pytest

from mtd_agent.models import VatBoxes, VatReturnPayload


def _boxes(**overrides) -> dict:
    base = dict(
        box1_vat_due_sales=Decimal("100.00"),
        box2_vat_due_acquisitions=Decimal("0.00"),
        box3_total_vat_due=Decimal("100.00"),
        box4_vat_reclaimed=Decimal("30.00"),
        box5_net_vat_due=Decimal("70.00"),
        box6_total_sales_ex_vat=500,
        box7_total_purchases_ex_vat=150,
        box8_total_goods_supplied_ex_vat=0,
        box9_total_acquisitions_ex_vat=0,
    )
    base.update(overrides)
    return base


def test_valid_boxes_construct():
    boxes = VatBoxes(**_boxes())
    assert boxes.box5_net_vat_due == Decimal("70.00")


def test_box3_must_equal_box1_plus_box2():
    with pytest.raises(ValueError):
        VatBoxes(**_boxes(box3_total_vat_due=Decimal("999.00")))


def test_box5_must_equal_abs_box3_minus_box4():
    with pytest.raises(ValueError):
        VatBoxes(**_boxes(box5_net_vat_due=Decimal("10.00")))


def test_payload_round_trips_from_boxes():
    boxes = VatBoxes(**_boxes())
    payload = VatReturnPayload.from_boxes(period_key="24A1", boxes=boxes, finalised=True)
    assert payload.periodKey == "24A1"
    assert payload.netVatDue == Decimal("70.00")
    assert payload.totalValueSalesExVAT == 500
    assert payload.finalised is True
