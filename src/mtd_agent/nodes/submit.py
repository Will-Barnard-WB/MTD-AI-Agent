"""B6 — submit: hand the approved payload to HMRC via the Protocol.

Idempotency is the client's responsibility (keyed on vrn + periodKey) — this node
just delegates, so a re-run can never double-file. It speaks only to the
`HmrcVatClient` interface, never the real client directly.
"""

from __future__ import annotations

from mtd_agent.interfaces import HmrcVatClient
from mtd_agent.models import SubmitReceipt, VatReturnPayload


def submit_return(
    client: HmrcVatClient,
    vrn: str,
    payload: VatReturnPayload,
) -> SubmitReceipt:
    return client.submit_vat_return(vrn, payload)
