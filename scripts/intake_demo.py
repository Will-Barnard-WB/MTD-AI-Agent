"""See the intake (HITL clarification) agent actually ask you a question.

The offline FakeCategoriser is hardcoded to 0.9 confidence, so intake never fires in
the normal demo. This script wraps it in an *uncertain* categoriser that reports low
confidence for chosen transactions, so `detect_gaps` flags them and the CLIQuestioner
asks you — at the terminal — to confirm the VAT treatment before the return is computed.

    python scripts/intake_demo.py                 # marks P1 (office supplies) uncertain
    python scripts/intake_demo.py fuel supplies   # mark any txn whose desc matches a keyword

Fully offline and free (Fake categoriser + Fake HMRC client). A confirmed answer only
changes a *label* — the pure core still does all the arithmetic (CONTRACT §8 A1).
"""

from __future__ import annotations

import sys
from pathlib import Path

from mtd_agent.graph.pipeline import run_pipeline
from mtd_agent.graph.state import Status
from mtd_agent.hmrc.fake_client import FakeHmrcVatClient
from mtd_agent.nodes.approval import CLIApprover
from mtd_agent.nodes.extract import FakeCategoriser, TxnCategory
from mtd_agent.nodes.intake import CLIQuestioner

CSV = Path("examples/sample_transactions.csv")
_LOW = 0.45  # below the 0.6 intake threshold


class UncertainCategoriser:
    """FakeCategoriser, but low-confidence for txns matching the given keywords/ids.

    Default (no keywords) marks the office-supplies line uncertain so the demo always
    asks something."""

    def __init__(self, keywords: list[str]) -> None:
        self._fake = FakeCategoriser()
        self._keys = [k.lower() for k in keywords] or ["office supplies"]

    def _uncertain(self, cat: TxnCategory, desc: str) -> bool:
        hay = f"{cat.id} {desc}".lower()
        return any(k in hay for k in self._keys)

    def categorise(self, txns):
        by_id = {t.id: t for t in txns}
        out = []
        for c in self._fake.categorise(txns):
            desc = by_id[c.id].description
            if self._uncertain(c, desc):
                out.append(c.model_copy(update={"confidence": _LOW,
                                                "reasoning": "offline demo: forced low confidence"}))
            else:
                out.append(c)
        return out


def main() -> int:
    categoriser = UncertainCategoriser(sys.argv[1:])
    print("Running the pipeline. Intake will pause and ask you to confirm the uncertain "
          "transaction(s) before the return is computed.\n"
          "Tip: try entering 'zero' or 'exempt' at the prompt to see the return change.\n")
    result = run_pipeline(
        csv_path=CSV, vrn="123456789", client=FakeHmrcVatClient(),
        categoriser=categoriser, approver=CLIApprover(), questioner=CLIQuestioner(),
    )
    print(f"\nStatus: {result.status.value}")
    print(f"Audit log: {result.audit_path}  (look for the 'intake_clarified' event)")
    if result.status == Status.SUBMITTED and result.boxes:
        print(f"Box 1 (VAT due on sales): £{result.boxes.box1_vat_due_sales}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
