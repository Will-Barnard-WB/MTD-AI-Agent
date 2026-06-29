"""Real HMRC VAT (MTD) client — implements the `HmrcVatClient` Protocol.

Re-architected from the AIAccountant CLI module into a typed client that the
pipeline drives through the frozen interface. Responsibilities and boundaries:

* It serialises a **ready** `VatReturnPayload` and POSTs it. It does NOT compute
  any box figure — that is Stream B's pure `compute_vat`. No number originates
  here, so the deterministic-core guarantee holds in the HMRC layer too.
* `submit_vat_return` is **idempotent** on `(VRN, periodKey)` via the persisted
  `IdempotencyLedger` — a repeat call returns the stored receipt, never re-files.
* Every HMRC error is mapped to a typed `HmrcUserError` / `HmrcSystemError`.
* All I/O goes through `config.assert_sandbox`, so there is no path to production.
"""

from __future__ import annotations

from datetime import date

import httpx

from mtd_agent.config import Settings, assert_sandbox
from mtd_agent.models import (
    Obligation,
    ObligationStatus,
    SubmitReceipt,
    VatReturnPayload,
)

from .auth import get_access_token
from .errors import HmrcAuthError, HmrcSystemError, HmrcUserError
from .fraud_headers import build_fraud_headers
from .idempotency import IdempotencyLedger

ACCEPT_HEADER = "application/vnd.hmrc.1.0+json"


class HmrcVatClient:
    """Concrete `HmrcVatClient`. Inject `http_client`/`ledger`/`settings` for tests."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        ledger: IdempotencyLedger | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or Settings.load()
        self.base_url = assert_sandbox(self.settings.hmrc_base_url)
        self.ledger = ledger or IdempotencyLedger()
        self._client = http_client  # if None, a short-lived client is used per request

    # ------------------------------------------------------------------ #
    # HTTP plumbing
    # ------------------------------------------------------------------ #

    def _headers(self, test_scenario: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": ACCEPT_HEADER,
            "Authorization": f"Bearer {get_access_token(self.settings)}",
            "Content-Type": "application/json",
            **build_fraud_headers(),
        }
        if test_scenario:
            headers["Gov-Test-Scenario"] = test_scenario
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
        test_scenario: str | None = None,
    ) -> dict:
        url = f"{self.base_url}{path}"
        headers = self._headers(test_scenario)

        def _do(client: httpx.Client) -> httpx.Response:
            return client.request(method, url, headers=headers, json=json_body, params=params)

        try:
            if self._client is not None:
                response = _do(self._client)
            else:
                with httpx.Client(timeout=30) as client:
                    response = _do(client)
        except httpx.HTTPError as exc:
            raise HmrcSystemError(f"HMRC request failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError:
            data = {"raw": response.text}

        if not response.is_success:
            raise self._map_error(response.status_code, data)
        return data

    @staticmethod
    def _map_error(status: int, data: dict) -> HmrcUserError | HmrcSystemError | HmrcAuthError:
        code = data.get("code") if isinstance(data, dict) else None
        message = (data.get("message") if isinstance(data, dict) else None) or str(data)
        if status in (401, 403):
            return HmrcAuthError(
                f"HMRC rejected the credentials/token: {message}", status=status, code=code
            )
        if status in (400, 404, 409, 422):
            # Validation, not-found, duplicate submission, business rule — user-fixable.
            return HmrcUserError(message, status=status, code=code, detail=data)
        return HmrcSystemError(message, status=status, code=code, detail=data)

    # ------------------------------------------------------------------ #
    # Protocol methods
    # ------------------------------------------------------------------ #

    def get_obligations(
        self,
        vrn: str,
        *,
        from_: date,
        to: date,
        status: ObligationStatus | None = None,
    ) -> list[Obligation]:
        params = {"from": from_.isoformat(), "to": to.isoformat()}
        if status is not None:
            params["status"] = status.value
        data = self._request(
            "GET",
            f"/organisations/vat/{vrn}/obligations",
            params=params,
            test_scenario="QUARTERLY_NONE_MET",
        )
        return [self._parse_obligation(o) for o in data.get("obligations", [])]

    def submit_vat_return(self, vrn: str, payload: VatReturnPayload) -> SubmitReceipt:
        existing = self.ledger.get(vrn, payload.periodKey)
        if existing is not None:
            return existing  # idempotent: already filed, return the stored receipt
        data = self._request(
            "POST",
            f"/organisations/vat/{vrn}/returns",
            json_body=self._payload_to_json(payload),
        )
        receipt = self._parse_receipt(data)
        self.ledger.put(vrn, payload.periodKey, receipt)
        return receipt

    def retrieve_vat_return(self, vrn: str, period_key: str) -> VatReturnPayload:
        data = self._request("GET", f"/organisations/vat/{vrn}/returns/{period_key}")
        return VatReturnPayload(
            periodKey=data.get("periodKey", period_key),
            vatDueSales=data["vatDueSales"],
            vatDueAcquisitions=data["vatDueAcquisitions"],
            totalVatDue=data["totalVatDue"],
            vatReclaimedCurrPeriod=data["vatReclaimedCurrPeriod"],
            netVatDue=data["netVatDue"],
            totalValueSalesExVAT=data["totalValueSalesExVAT"],
            totalValuePurchasesExVAT=data["totalValuePurchasesExVAT"],
            totalValueGoodsSuppliedExVAT=data["totalValueGoodsSuppliedExVAT"],
            totalAcquisitionsExVAT=data["totalAcquisitionsExVAT"],
            finalised=data.get("finalised", True),
        )

    # ------------------------------------------------------------------ #
    # Parsers / serialisers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _payload_to_json(payload: VatReturnPayload) -> dict:
        """Serialise to HMRC's JSON shape: boxes 1-5 as numbers, 6-9 as ints."""
        return {
            "periodKey": payload.periodKey,
            "vatDueSales": float(payload.vatDueSales),
            "vatDueAcquisitions": float(payload.vatDueAcquisitions),
            "totalVatDue": float(payload.totalVatDue),
            "vatReclaimedCurrPeriod": float(payload.vatReclaimedCurrPeriod),
            "netVatDue": float(payload.netVatDue),
            "totalValueSalesExVAT": payload.totalValueSalesExVAT,
            "totalValuePurchasesExVAT": payload.totalValuePurchasesExVAT,
            "totalValueGoodsSuppliedExVAT": payload.totalValueGoodsSuppliedExVAT,
            "totalAcquisitionsExVAT": payload.totalAcquisitionsExVAT,
            "finalised": payload.finalised,
        }

    @staticmethod
    def _parse_obligation(o: dict) -> Obligation:
        return Obligation(
            period_key=o["periodKey"],
            start=date.fromisoformat(o["start"]),
            end=date.fromisoformat(o["end"]),
            due=date.fromisoformat(o["due"]),
            status=ObligationStatus(o["status"]),
            received=date.fromisoformat(o["received"]) if o.get("received") else None,
        )

    @staticmethod
    def _parse_receipt(data: dict) -> SubmitReceipt:
        return SubmitReceipt(
            processing_date=data["processingDate"],
            form_bundle_number=data["formBundleNumber"],
            charge_ref_number=data.get("chargeRefNumber"),
            payment_indicator=data.get("paymentIndicator"),
        )
