"""Persisted idempotency ledger for VAT submissions (CONTRACT.md §1.4).

HMRC's *retrieve* endpoint returns the box values but **not** the submission
receipt (the formBundleNumber is only ever returned at submit time), so we
cannot reconstruct a receipt by re-fetching. Instead we record every successful
submission locally, keyed by `(VRN, periodKey)`. A repeat submit returns the
stored receipt and never re-files — mirroring FakeHmrcVatClient exactly, so
Stream B sees identical behaviour from the fake and the real client.
"""

from __future__ import annotations

import json
from pathlib import Path

from mtd_agent.models import SubmitReceipt

DEFAULT_LEDGER_PATH = Path("audit") / "idempotency.json"


class IdempotencyLedger:
    """A tiny JSON-backed map of (vrn, period_key) -> SubmitReceipt."""

    def __init__(self, path: Path = DEFAULT_LEDGER_PATH) -> None:
        self.path = path
        self._cache: dict[str, dict] = {}
        if path.exists():
            self._cache = json.loads(path.read_text(encoding="utf-8") or "{}")

    @staticmethod
    def _key(vrn: str, period_key: str) -> str:
        return f"{vrn}:{period_key}"

    def get(self, vrn: str, period_key: str) -> SubmitReceipt | None:
        raw = self._cache.get(self._key(vrn, period_key))
        return SubmitReceipt.model_validate(raw) if raw else None

    def put(self, vrn: str, period_key: str, receipt: SubmitReceipt) -> None:
        self._cache[self._key(vrn, period_key)] = json.loads(receipt.model_dump_json())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._cache, indent=2), encoding="utf-8")
