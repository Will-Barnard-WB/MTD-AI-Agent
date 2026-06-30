"""In-memory fake HMRC VAT client — satisfies the HmrcVatClient Protocol.

Lets Stream B build and test the whole pipeline with zero credentials and zero
network. It encodes the behaviours the real client MUST also honour:
  * get_obligations returns a canned open period,
  * submit_vat_return is IDEMPOTENT on (vrn, periodKey),
  * retrieve_vat_return returns what was submitted.

Stream A's real vat_client must match this contract (see tests).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from mtd_agent.models import (
    Obligation,
    ObligationStatus,
    SubmitReceipt,
    VatReturnPayload,
)


def _default_open_obligation() -> Obligation:
    """An open period anchored to *today*, so the pipeline's today-relative
    obligations window always finds it (and tests/demo stay date-stable)."""
    today = date.today()
    return Obligation(
        period_key="24A1",
        start=today - timedelta(days=45),
        end=today + timedelta(days=45),
        due=today + timedelta(days=75),
        status=ObligationStatus.OPEN,
    )


class FakeHmrcVatClient:
    """Deterministic, offline stand-in for the real HMRC VAT client."""

    def __init__(self, obligations: list[Obligation] | None = None) -> None:
        self._obligations = (
            obligations if obligations is not None else [_default_open_obligation()]
        )
        # (vrn, period_key) -> (payload, receipt) — the idempotency ledger.
        self._submissions: dict[tuple[str, str], tuple[VatReturnPayload, SubmitReceipt]] = {}
        self._counter = 0

    def get_obligations(
        self,
        vrn: str,
        *,
        from_: date,
        to: date,
        status: ObligationStatus | None = None,
    ) -> list[Obligation]:
        out = [o for o in self._obligations if o.start >= from_ and o.end <= to]
        if status is not None:
            out = [o for o in out if o.status == status]
        return out

    def submit_vat_return(self, vrn: str, payload: VatReturnPayload) -> SubmitReceipt:
        key = (vrn, payload.periodKey)
        if key in self._submissions:
            # Idempotent: return the existing receipt, do not file again.
            return self._submissions[key][1]
        self._counter += 1
        receipt = SubmitReceipt(
            processing_date=datetime.now(timezone.utc),
            form_bundle_number=f"FAKE-{self._counter:08d}",
            charge_ref_number=None,
        )
        self._submissions[key] = (payload, receipt)
        return receipt

    def retrieve_vat_return(self, vrn: str, period_key: str) -> VatReturnPayload:
        key = (vrn, period_key)
        if key not in self._submissions:
            raise KeyError(f"No submission for vrn={vrn} period={period_key}")
        return self._submissions[key][0]
