"""Safety hardening — output guardrails (no agent emits a figure or bypasses the gate)
and the adversarial guardrails eval."""

from mtd_agent.guardrails import comment_violations, enforce_advisory, scan_description
from mtd_agent.guardrails_eval import load_cases
from mtd_agent.reviewer import ReviewComment


# --- Output guardrail: reviewer comments must stay advisory ---------------- #

def test_comment_violations_flags_figures_and_directives():
    assert comment_violations("box 1 should be £200") == ["contains a monetary figure"]
    assert "box-mutation directive" in comment_violations("set box 1 = 200")
    assert "box-mutation directive" in comment_violations("force Box 4 to zero")
    assert comment_violations("classified standard, but reduced rate may apply") == []


def test_enforce_advisory_drops_figure_and_ungrounded_comments():
    comments = [
        ReviewComment(txn_id="A", severity="warning", message="looks like reduced rate",
                      citation="vat-rates#reduced"),                       # keep
        ReviewComment(txn_id="B", severity="warning", message="set box 1 = £500",
                      citation="vat-rates#standard"),                      # drop: figure+directive
        ReviewComment(txn_id="C", severity="info", message="just a note", citation=""),  # drop: ungrounded
    ]
    kept, dropped = enforce_advisory(comments)
    assert [c.txn_id for c in kept] == ["A"]
    assert len(dropped) == 2


def test_a_real_reviewer_comment_passes_the_guardrail():
    from datetime import date
    from decimal import Decimal

    from mtd_agent.models import CategorisedTransaction, Direction, Transaction, VatTreatment
    from mtd_agent.reviewer import Reviewer, SkillSet

    txn = Transaction(id="P1", date=date(2026, 1, 1), description="Reduced-rate domestic fuel",
                      amount=Decimal("105"), direction=Direction.PURCHASE)
    cat = CategorisedTransaction(txn=txn, treatment=VatTreatment.STANDARD, category="", confidence=0.95)
    comments = Reviewer(SkillSet.load("2026-27")).review([cat])
    kept, dropped = enforce_advisory(comments)
    assert kept == comments and dropped == []   # genuine comments are advisory + cited


# --- Structural: submit is only reachable through the approval gate --------- #

def test_submit_only_reachable_via_approval():
    from mtd_agent.graph.build import PIPELINE_GRAPH

    edges = PIPELINE_GRAPH.get_graph().edges
    sources_into_submit = {e.source for e in edges if e.target == "submit"}
    assert sources_into_submit == {"approval"}, sources_into_submit


# --- Adversarial guardrails eval ------------------------------------------- #

def test_guardrails_eval_all_cases_pass():
    for c in load_cases():
        r = scan_description(c.text)
        assert set(r.pii_kinds) == c.pii, f"{c.name}: PII {r.pii_kinds} != {c.pii}"
        assert bool(r.injection_hits) == c.injection, f"{c.name}: injection mismatch"
