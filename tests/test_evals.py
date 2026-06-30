"""Eval harness as an offline regression gate (PLAN 3.3).

Keeps the deterministic core honest on realistic labelled cases, and asserts the
offline keyword categoriser clears a sanity accuracy bar. The online OpenAI eval
is run manually: `python -m mtd_agent.eval_harness --real-llm`.
"""

from mtd_agent.eval_harness import load_cases, run_case
from mtd_agent.nodes.extract import FakeCategoriser


def test_compute_vat_matches_expected_on_all_cases():
    fake = FakeCategoriser()
    cases = load_cases()
    assert cases, "no eval cases found"
    for case in cases:
        assert run_case(case, fake).boxes_ok, f"compute_vat != expected boxes for {case.name}"


def test_fake_categoriser_meets_accuracy_bar():
    fake = FakeCategoriser()
    total = correct = 0
    for case in load_cases():
        r = run_case(case, fake)
        total += r.n
        correct += r.correct
    assert total > 0
    assert correct / total >= 0.8, f"offline categoriser accuracy too low: {correct}/{total}"
