"""Unit tests for the real HMRC VAT client — fully offline via httpx.MockTransport.

Covers: Protocol conformance, obligation parsing, submit + receipt parsing,
idempotency (a repeat submit does NOT hit the network), retrieve round-trip,
typed error mapping, and the sandbox guard. The one *live* sandbox smoke test
is separate and creds-gated (see test_live_smoke.py / BLOCKERS.md).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import httpx
import pytest

from mtd_agent.config import Settings
from mtd_agent.hmrc.errors import HmrcAuthError, HmrcSystemError, HmrcUserError
from mtd_agent.hmrc.idempotency import IdempotencyLedger
from mtd_agent.hmrc.vat_client import HmrcVatClient
from mtd_agent.interfaces import HmrcVatClient as HmrcVatClientProtocol
from mtd_agent.models import ObligationStatus, VatBoxes, VatReturnPayload

SANDBOX = "https://test-api.service.hmrc.gov.uk"

RECEIPT_JSON = {
    "processingDate": "2026-05-01T10:00:00.000Z",
    "formBundleNumber": "123456789012",
    "chargeRefNumber": "XY123456789",
    "paymentIndicator": "BANK",
}

RETURN_JSON = {
    "periodKey": "24A1",
    "vatDueSales": 1000.00,
    "vatDueAcquisitions": 0.00,
    "totalVatDue": 1000.00,
    "vatReclaimedCurrPeriod": 250.00,
    "netVatDue": 750.00,
    "totalValueSalesExVAT": 5000,
    "totalValuePurchasesExVAT": 1250,
    "totalValueGoodsSuppliedExVAT": 0,
    "totalAcquisitionsExVAT": 0,
    "finalised": True,
}


@pytest.fixture(autouse=True)
def _fake_token(monkeypatch):
    """Avoid any token refresh network call: a valid, far-future access token."""
    monkeypatch.setenv("HMRC_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("HMRC_TOKEN_EXPIRES_AT", "9999999999")
    monkeypatch.setenv("HMRC_BASE_URL", SANDBOX)


def _settings() -> Settings:
    return Settings.load()


def _client(handler, tmp_path) -> HmrcVatClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    ledger = IdempotencyLedger(path=tmp_path / "idem.json")
    return HmrcVatClient(_settings(), ledger=ledger, http_client=http)


def _sample_payload() -> VatReturnPayload:
    boxes = VatBoxes(
        box1_vat_due_sales=1000,
        box2_vat_due_acquisitions=0,
        box3_total_vat_due=1000,
        box4_vat_reclaimed=250,
        box5_net_vat_due=750,
        box6_total_sales_ex_vat=5000,
        box7_total_purchases_ex_vat=1250,
        box8_total_goods_supplied_ex_vat=0,
        box9_total_acquisitions_ex_vat=0,
    )
    return VatReturnPayload.from_boxes(period_key="24A1", boxes=boxes, finalised=True)


def test_implements_protocol(tmp_path):
    client = _client(lambda r: httpx.Response(200, json={}), tmp_path)
    assert isinstance(client, HmrcVatClientProtocol)


def test_get_obligations_parsed(tmp_path):
    def handler(request):
        assert request.url.path.endswith("/obligations")
        return httpx.Response(200, json={"obligations": [{
            "periodKey": "24A1", "start": "2026-01-01", "end": "2026-03-31",
            "due": "2026-05-07", "status": "O",
        }]})

    client = _client(handler, tmp_path)
    obs = client.get_obligations("123456789", from_=date(2026, 1, 1), to=date(2026, 3, 31),
                                 status=ObligationStatus.OPEN)
    assert len(obs) == 1
    assert obs[0].period_key == "24A1"
    assert obs[0].status is ObligationStatus.OPEN
    assert obs[0].due == date(2026, 5, 7)


def test_submit_returns_receipt(tmp_path):
    client = _client(lambda r: httpx.Response(201, json=RECEIPT_JSON), tmp_path)
    receipt = client.submit_vat_return("123456789", _sample_payload())
    assert receipt.form_bundle_number == "123456789012"
    assert receipt.charge_ref_number == "XY123456789"


def test_submit_is_idempotent_no_second_post(tmp_path):
    calls = {"post": 0}

    def handler(request):
        if request.method == "POST":
            calls["post"] += 1
        return httpx.Response(201, json=RECEIPT_JSON)

    client = _client(handler, tmp_path)
    payload = _sample_payload()
    r1 = client.submit_vat_return("123456789", payload)
    r2 = client.submit_vat_return("123456789", payload)  # must not re-file
    assert calls["post"] == 1
    assert r1.form_bundle_number == r2.form_bundle_number


def test_idempotency_persists_across_instances(tmp_path):
    """A fresh client (new process) with the same ledger file does not re-file."""
    calls = {"post": 0}

    def handler(request):
        if request.method == "POST":
            calls["post"] += 1
        return httpx.Response(201, json=RECEIPT_JSON)

    ledger_path = tmp_path / "idem.json"
    payload = _sample_payload()

    c1 = HmrcVatClient(_settings(), ledger=IdempotencyLedger(ledger_path),
                       http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    c1.submit_vat_return("123456789", payload)

    c2 = HmrcVatClient(_settings(), ledger=IdempotencyLedger(ledger_path),
                       http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    c2.submit_vat_return("123456789", payload)

    assert calls["post"] == 1


def test_retrieve_round_trip(tmp_path):
    client = _client(lambda r: httpx.Response(200, json=RETURN_JSON), tmp_path)
    payload = client.retrieve_vat_return("123456789", "24A1")
    assert payload.periodKey == "24A1"
    assert float(payload.netVatDue) == 750.00
    assert payload.totalValueSalesExVAT == 5000


@pytest.mark.parametrize("status,exc", [
    (400, HmrcUserError),
    (404, HmrcUserError),
    (409, HmrcUserError),
    (401, HmrcAuthError),
    (403, HmrcAuthError),
    (500, HmrcSystemError),
    (503, HmrcSystemError),
])
def test_error_mapping(tmp_path, status, exc):
    def handler(request):
        return httpx.Response(status, json={"code": "X", "message": "boom"})

    client = _client(handler, tmp_path)
    with pytest.raises(exc):
        client.get_obligations("123456789", from_=date(2026, 1, 1), to=date(2026, 3, 31))


def test_sandbox_guard_blocks_production(tmp_path):
    prod = replace(_settings(), hmrc_base_url="https://api.service.hmrc.gov.uk")
    with pytest.raises(RuntimeError, match="sandbox"):
        HmrcVatClient(prod, ledger=IdempotencyLedger(tmp_path / "idem.json"))
