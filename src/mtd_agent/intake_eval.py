"""Intake eval harness (v2 A3): does the intake agent catch what it should?

The intake agent's job is to *surface the uncertain transactions to the human before
compute* — no more, no less. This harness measures that against a golden set:

- **Recall** — of the transactions that *should* be confirmed, how many did the agent
  flag? A miss (FN) is the dangerous failure: an uncertain figure slides through to the
  return unquestioned. We hold recall to 100%.
- **Precision** — of the transactions the agent flagged, how many genuinely needed it?
  Low precision (FP) means over-asking — it erodes the expert's trust and attention.

The detector under test is pluggable (`detect_gaps` today; an LLM question-author or a
calibrated-confidence detector later) so this stays a regression gate as intake gets
smarter. It measures *labels only* — never a figure (CONTRACT §8 A1).

    ./.venv/bin/python -m mtd_agent.intake_eval
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from mtd_agent.models import CategorisedTransaction, Direction, Transaction, VatTreatment
from mtd_agent.nodes.intake import Gap, detect_gaps

CASES_PATH = Path(__file__).resolve().parents[2] / "evals" / "intake" / "cases.json"

# A gap detector: categorised transactions in, the ones needing confirmation out.
Detector = Callable[[list[CategorisedTransaction]], list[Gap]]


@dataclass
class IntakeCase:
    name: str
    cats: list[CategorisedTransaction]
    should_flag: set[str]


@dataclass
class IntakeResult:
    name: str
    flagged: set[str]
    should_flag: set[str]

    @property
    def tp(self) -> int:
        return len(self.flagged & self.should_flag)

    @property
    def fp(self) -> set[str]:
        return self.flagged - self.should_flag

    @property
    def fn(self) -> set[str]:
        return self.should_flag - self.flagged

    @property
    def precision(self) -> float:
        return self.tp / len(self.flagged) if self.flagged else 1.0

    @property
    def recall(self) -> float:
        return self.tp / len(self.should_flag) if self.should_flag else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 1.0


def _cat(row: dict) -> CategorisedTransaction:
    """Build a categorised transaction from a JSON case row (description + label only)."""
    txn = Transaction(
        id=row["id"],
        date=date(2026, 1, 1),
        description=row["description"],
        amount=Decimal("120.00"),
        direction=Direction.SALE,
    )
    return CategorisedTransaction(
        txn=txn,
        treatment=VatTreatment(row["treatment"]),
        category="",
        confidence=float(row["confidence"]),
    )


def load_cases(path: Path = CASES_PATH) -> list[IntakeCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        IntakeCase(
            name=c["name"],
            cats=[_cat(r) for r in c["txns"]],
            should_flag=set(c["should_flag"]),
        )
        for c in raw
    ]


def run_case(case: IntakeCase, detector: Detector = detect_gaps) -> IntakeResult:
    flagged = {g.txn_id for g in detector(case.cats)}
    return IntakeResult(case.name, flagged, case.should_flag)


def main() -> int:
    cases = load_cases()
    print("Intake eval — detector: detect_gaps (calibrated confidence + ambiguity heuristic)\n")
    print(f"{'case':<28} {'flagged':>7} {'gold':>4} {'prec':>6} {'recall':>7} {'F1':>6}")
    print("-" * 62)

    micro_tp = micro_flagged = micro_gold = 0
    worst_recall = 1.0
    for case in cases:
        r = run_case(case)
        micro_tp += r.tp
        micro_flagged += len(r.flagged)
        micro_gold += len(r.should_flag)
        worst_recall = min(worst_recall, r.recall)
        flags = f"{len(r.flagged)}"
        if r.fn:
            flags += f" MISS:{','.join(sorted(r.fn))}"
        print(f"{r.name:<28} {flags:>7} {len(r.should_flag):>4} "
              f"{r.precision:>6.0%} {r.recall:>7.0%} {r.f1:>6.2f}")

    micro_p = micro_tp / micro_flagged if micro_flagged else 1.0
    micro_r = micro_tp / micro_gold if micro_gold else 1.0
    print("-" * 62)
    print(f"micro precision: {micro_p:.0%}   micro recall: {micro_r:.0%}   "
          f"worst per-case recall: {worst_recall:.0%}")
    # Recall is the safety-critical metric — a miss lets an uncertain item through unasked.
    return 0 if worst_recall == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
