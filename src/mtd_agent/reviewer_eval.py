"""Reviewer eval harness (Phase C4): true issues vs false positives.

The reviewer is only useful if it catches genuine misclassifications (recall) *without*
crying wolf on correct ones (precision). A false positive is the expensive failure here —
it erodes the expert's trust in the second opinion. Golden set lives in
`evals/reviewer/cases.json`; each case is (description, assigned treatment, should_flag,
optional expected citation).

    ./.venv/bin/python -m mtd_agent.reviewer_eval
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from mtd_agent.models import CategorisedTransaction, Direction, Transaction, VatTreatment
from mtd_agent.reviewer import Reviewer, SkillSet

CASES_PATH = Path(__file__).resolve().parents[2] / "evals" / "reviewer" / "cases.json"


@dataclass
class ReviewerCase:
    name: str
    description: str
    treatment: VatTreatment
    should_flag: bool
    expect_citation: str | None


@dataclass
class ReviewerResult:
    name: str
    should_flag: bool
    flagged: bool
    citation: str | None
    expect_citation: str | None

    @property
    def correct(self) -> bool:
        if self.flagged != self.should_flag:
            return False
        if self.flagged and self.expect_citation:
            return self.citation == self.expect_citation
        return True


def load_cases(path: Path = CASES_PATH) -> list[ReviewerCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        ReviewerCase(c["name"], c["description"], VatTreatment(c["treatment"]),
                     bool(c["should_flag"]), c.get("expect_citation"))
        for c in raw
    ]


def run_case(case: ReviewerCase, reviewer: Reviewer) -> ReviewerResult:
    txn = Transaction(id="X", date=date(2026, 1, 1), description=case.description,
                      amount=Decimal("100"), direction=Direction.PURCHASE)
    cat = CategorisedTransaction(txn=txn, treatment=case.treatment, category="", confidence=0.95)
    comments = reviewer.review([cat])
    citation = comments[0].citation if comments else None
    return ReviewerResult(case.name, case.should_flag, bool(comments), citation, case.expect_citation)


def main() -> int:
    reviewer = Reviewer(SkillSet.load("2026-27"))
    cases = load_cases()
    print("Reviewer eval — skills KB 2026-27\n")
    print(f"{'case':<26} {'should':>7} {'flagged':>8} {'citation':>22} {'ok':>4}")
    print("-" * 72)

    tp = fp = fn = 0
    for case in cases:
        r = run_case(case, reviewer)
        if r.should_flag and r.flagged:
            tp += 1
        elif r.flagged and not r.should_flag:
            fp += 1
        elif r.should_flag and not r.flagged:
            fn += 1
        print(f"{r.name:<26} {str(r.should_flag):>7} {str(r.flagged):>8} "
              f"{(r.citation or '-'):>22} {('yes' if r.correct else 'NO'):>4}")

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    print("-" * 72)
    print(f"precision: {precision:.0%}   recall: {recall:.0%}   (fp={fp}, fn={fn})")
    return 0 if fp == 0 and fn == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
