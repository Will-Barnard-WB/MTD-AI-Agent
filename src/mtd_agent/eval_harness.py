"""Eval harness (PLAN 3.3): labelled CSVs → expected boxes + categorisation accuracy.

Two things measured per case:
1. **Deterministic core** — compute_vat over the *ground-truth* labels must equal the
   hand-computed expected boxes. This is a regression gate on `compute_vat` itself
   (run in the offline test suite).
2. **Categoriser quality** — the categoriser-under-test's predicted treatments vs the
   labels (accuracy), plus whether its predictions still yield the correct boxes.

Offline by default (FakeCategoriser). Evaluate the real OpenAI categoriser online with:

    ./.venv/bin/python -m mtd_agent.eval_harness --real-llm
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from mtd_agent.models import CategorisedTransaction, VatBoxes, VatTreatment
from mtd_agent.nodes import ingest
from mtd_agent.nodes.compute_vat import compute_vat
from mtd_agent.nodes.extract import Categoriser, FakeCategoriser

CASES_DIR = Path(__file__).resolve().parents[2] / "evals" / "cases"


@dataclass
class Case:
    name: str
    csv: Path
    treatments: dict[str, str]
    expected_boxes: dict


@dataclass
class CaseResult:
    name: str
    n: int
    boxes_ok: bool          # compute_vat(ground-truth) == expected  (validates the core)
    correct: int            # categoriser predictions matching the labels
    boxes_match_pred: bool  # end-to-end boxes with predicted treatments == ground-truth boxes


def load_cases(cases_dir: Path = CASES_DIR) -> list[Case]:
    cases: list[Case] = []
    for csv_path in sorted(cases_dir.glob("*.csv")):
        labels = json.loads(csv_path.with_suffix(".labels.json").read_text(encoding="utf-8"))
        cases.append(Case(csv_path.stem, csv_path, labels["treatments"], labels["expected_boxes"]))
    return cases


def _expected_boxes(d: dict) -> VatBoxes:
    return VatBoxes(
        box1_vat_due_sales=Decimal(str(d["box1_vat_due_sales"])),
        box2_vat_due_acquisitions=Decimal(str(d["box2_vat_due_acquisitions"])),
        box3_total_vat_due=Decimal(str(d["box3_total_vat_due"])),
        box4_vat_reclaimed=Decimal(str(d["box4_vat_reclaimed"])),
        box5_net_vat_due=Decimal(str(d["box5_net_vat_due"])),
        box6_total_sales_ex_vat=int(d["box6_total_sales_ex_vat"]),
        box7_total_purchases_ex_vat=int(d["box7_total_purchases_ex_vat"]),
        box8_total_goods_supplied_ex_vat=int(d["box8_total_goods_supplied_ex_vat"]),
        box9_total_acquisitions_ex_vat=int(d["box9_total_acquisitions_ex_vat"]),
    )


def _cats(txns, treatments: dict[str, VatTreatment]) -> list[CategorisedTransaction]:
    return [
        CategorisedTransaction(txn=t, treatment=treatments[t.id], category="", confidence=1.0)
        for t in txns
        if t.id in treatments
    ]


def run_case(case: Case, categoriser: Categoriser) -> CaseResult:
    txns = ingest.load_transactions(case.csv)

    gt = {tid: VatTreatment(v) for tid, v in case.treatments.items()}
    gt_boxes = compute_vat(_cats(txns, gt))
    boxes_ok = gt_boxes == _expected_boxes(case.expected_boxes)

    preds = {p.id: p.treatment for p in categoriser.categorise(txns)}
    correct = sum(1 for t in txns if preds.get(t.id) == gt.get(t.id))
    pred_boxes = compute_vat(_cats(txns, preds))

    return CaseResult(case.name, len(txns), boxes_ok, correct, pred_boxes == gt_boxes)


def main() -> int:
    parser = argparse.ArgumentParser(prog="mtd_agent.eval_harness")
    parser.add_argument("--real-llm", action="store_true",
                        help="Evaluate the OpenAI categoriser online (spends credits).")
    args = parser.parse_args()

    if args.real_llm:
        from mtd_agent.config import Settings
        from mtd_agent.nodes.extract import OpenAICategoriser
        settings = Settings.load()
        if not settings.openai_api_key:
            print("OPENAI_API_KEY not set — omit --real-llm for the offline Fake eval.")
            return 2
        categoriser: Categoriser = OpenAICategoriser(settings.openai_api_key,
                                                     settings.extraction_model)
        label = f"OpenAI ({settings.extraction_model})"
    else:
        categoriser = FakeCategoriser()
        label = "FakeCategoriser (offline keyword rules)"

    cases = load_cases()
    print(f"Eval — categoriser: {label}\n")
    print(f"{'case':<20} {'txns':>5} {'boxes✓(core)':>13} {'cat-acc':>9} {'boxes✓(pred)':>13}")
    print("-" * 64)

    total = correct = 0
    all_core_ok = True
    for case in cases:
        r = run_case(case, categoriser)
        total += r.n
        correct += r.correct
        all_core_ok &= r.boxes_ok
        acc = r.correct / r.n if r.n else 0.0
        print(f"{r.name:<20} {r.n:>5} {('yes' if r.boxes_ok else 'NO'):>13} "
              f"{acc:>8.0%} {('yes' if r.boxes_match_pred else 'NO'):>13}")

    print("-" * 64)
    print(f"overall categorisation accuracy: {correct}/{total} = {correct / total:.0%}")
    print(f"deterministic core: {'all cases match expected boxes' if all_core_ok else 'REGRESSION'}")
    return 0 if all_core_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
