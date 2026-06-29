"""The interface boundary between Stream A (HMRC) and Stream B (pipeline).

# contract-version: 1
#
# THIS IS THE PARALLELISATION CONTRACT (see CONTRACT.md §3).
# - Stream B codes against THIS Protocol + the FakeHmrcVatClient. It must never
#   import the real HMRC client.
# - Stream A implements THIS Protocol with the real sandbox client.
# Change it only in Phase 0, or by an explicit agreed update — and bump the
# contract-version above + note it in LOG.md when you do.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from mtd_agent.models import Obligation, ObligationStatus, SubmitReceipt, VatReturnPayload


@runtime_checkable
class HmrcVatClient(Protocol):
    """Everything the pipeline needs from HMRC — and nothing more."""

    def get_obligations(
        self,
        vrn: str,
        *,
        from_: date,
        to: date,
        status: ObligationStatus | None = None,
    ) -> list[Obligation]:
        """Return VAT obligation periods for the VRN in the date window.

        Pass status=OPEN to find the period to submit against.
        """
        ...

    def submit_vat_return(self, vrn: str, payload: VatReturnPayload) -> SubmitReceipt:
        """Submit a VAT return. MUST be idempotent on (vrn, payload.periodKey):
        a repeat submit for the same period returns the existing receipt and
        does not file twice."""
        ...

    def retrieve_vat_return(self, vrn: str, period_key: str) -> VatReturnPayload:
        """Fetch a previously submitted return (used to confirm/verify a filing)."""
        ...
