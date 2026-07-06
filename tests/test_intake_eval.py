"""v2 A3 — intake eval set (completeness detection) as an offline regression gate.

Asserts the intake detector catches everything the golden set says it should (100%
recall — a miss would let an uncertain figure through unasked) and doesn't wildly
over-ask (a precision floor).
"""

from mtd_agent.intake_eval import load_cases, run_case


def test_cases_load():
    cases = load_cases()
    assert cases, "no intake eval cases found"
    # A meaningful eval needs both kinds of case: some to flag, some to leave alone.
    assert any(c.should_flag for c in cases)
    assert any(not c.should_flag for c in cases)


def test_detector_catches_everything_it_should():
    """Recall == 100% on every case — the safety-critical metric for intake."""
    for case in load_cases():
        r = run_case(case)
        assert r.recall == 1.0, f"intake missed {sorted(r.fn)} in case {case.name}"


def test_detector_does_not_over_ask():
    """Precision floor — flagging confident transactions erodes expert trust."""
    micro_tp = micro_flagged = 0
    for case in load_cases():
        r = run_case(case)
        micro_tp += r.tp
        micro_flagged += len(r.flagged)
    precision = micro_tp / micro_flagged if micro_flagged else 1.0
    assert precision >= 0.8, f"intake over-asks: micro precision {precision:.0%}"
