"""Fake client behaviour — the contract Stream A's real client must also meet."""

from datetime import date
from decimal import Decimal

from mtd_agent.hmrc.fake_client import FakeHmrcVatClient
from mtd_agent.interfaces import HmrcVatClient
from mtd_agent.models import ObligationStatus, VatBoxes, VatReturnPayload


def _payload(period_key="24A1") -> VatReturnPayload:
    boxes = VatBoxes(
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
    return VatReturnPayload.from_boxes(period_key=period_key, boxes=boxes, finalised=True)


def test_fake_satisfies_protocol():
    assert isinstance(FakeHmrcVatClient(), HmrcVatClient)


def test_open_obligation_is_returned():
    client = FakeHmrcVatClient()
    obs = client.get_obligations(
        "123456789", from_=date(2026, 1, 1), to=date(2026, 12, 31),
        status=ObligationStatus.OPEN,
    )
    assert len(obs) == 1
    assert obs[0].status == ObligationStatus.OPEN


def test_submit_is_idempotent():
    client = FakeHmrcVatClient()
    r1 = client.submit_vat_return("123456789", _payload())
    r2 = client.submit_vat_return("123456789", _payload())
    # Same period -> same receipt, no double-file.
    assert r1.form_bundle_number == r2.form_bundle_number


def test_retrieve_returns_submitted_payload():
    client = FakeHmrcVatClient()
    client.submit_vat_return("123456789", _payload())
    got = client.retrieve_vat_return("123456789", "24A1")
    assert got.netVatDue == Decimal("70.00")
