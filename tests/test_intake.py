"""v2 A2 — intake clarification: gap detection, answer application, and the
end-to-end interrupt/resume loop actually changing the computed return."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from mtd_agent.audit import AuditLogger
from mtd_agent.graph.pipeline import run_pipeline
from mtd_agent.graph.state import Status
from mtd_agent.hmrc.fake_client import FakeHmrcVatClient
from mtd_agent.models import CategorisedTransaction, Direction, Transaction, VatTreatment
from mtd_agent.nodes.approval import AutoApprover
from mtd_agent.nodes.extract import TxnCategory
from mtd_agent.nodes.intake import (
    AutoQuestioner,
    apply_answers,
    clarification_log,
    detect_gaps,
)

EXAMPLE_CSV = Path(__file__).resolve().parents[1] / "examples" / "sample_transactions.csv"


def _cat(txn_id: str, treatment: VatTreatment, conf: float) -> CategorisedTransaction:
    txn = Transaction(id=txn_id, date=date(2026, 1, 1), description=f"desc {txn_id}",
                      amount=Decimal("120.00"), direction=Direction.SALE)
    return CategorisedTransaction(txn=txn, treatment=treatment, category="x", confidence=conf)


def test_detect_gaps_flags_low_confidence():
    cats = [_cat("A", VatTreatment.STANDARD, 0.9), _cat("B", VatTreatment.STANDARD, 0.4)]
    gaps = detect_gaps(cats)
    assert [g.txn_id for g in gaps] == ["B"]
    assert any("low confidence" in r for r in gaps[0].reasons)


def _cat_desc(txn_id: str, description: str, conf: float) -> CategorisedTransaction:
    txn = Transaction(id=txn_id, date=date(2026, 1, 1), description=description,
                      amount=Decimal("120.00"), direction=Direction.SALE)
    return CategorisedTransaction(txn=txn, treatment=VatTreatment.STANDARD, category="x",
                                  confidence=conf)


def test_detect_gaps_flags_confident_but_opaque():
    """Calibration: a HIGH-confidence but opaque description is still flagged —
    the fix for 'confidently wrong'."""
    gaps = detect_gaps([_cat_desc("A", "Payment", 0.95)])
    assert [g.txn_id for g in gaps] == ["A"]
    assert any("opaque" in r for r in gaps[0].reasons)


def test_detect_gaps_flags_conflicting_cues():
    gaps = detect_gaps([_cat_desc("A", "Train tickets and insurance excess", 0.9)])
    assert [g.txn_id for g in gaps] == ["A"]
    assert any("conflicting" in r for r in gaps[0].reasons)


def test_clear_confident_transaction_is_not_flagged():
    assert detect_gaps([_cat_desc("A", "Consulting fee for Q1 project", 0.95)]) == []


def test_fake_categoriser_reports_honest_confidence():
    from mtd_agent.nodes.extract import FakeCategoriser
    txns = [
        Transaction(id="hit", date=date(2026, 1, 1), description="Train ticket to Leeds",
                    amount=Decimal("10"), direction=Direction.PURCHASE),
        Transaction(id="miss", date=date(2026, 1, 1), description="Consulting fee",
                    amount=Decimal("10"), direction=Direction.SALE),
    ]
    by_id = {c.id: c for c in FakeCategoriser().categorise(txns)}
    assert by_id["hit"].confidence == 0.9 and by_id["hit"].needs_review is False
    assert by_id["miss"].confidence < 0.6 and by_id["miss"].needs_review is True


def test_detect_gaps_honours_model_self_flag():
    """The explicit needs_review flag fires intake even on a clear, high-confidence item."""
    txn = Transaction(id="A", date=date(2026, 1, 1), description="Consulting fee for Q1 project",
                      amount=Decimal("120"), direction=Direction.SALE)
    flagged = CategorisedTransaction(txn=txn, treatment=VatTreatment.STANDARD, category="x",
                                     confidence=0.95, needs_review=True,
                                     candidates=[VatTreatment.STANDARD, VatTreatment.ZERO])
    gaps = detect_gaps([flagged])
    assert [g.txn_id for g in gaps] == ["A"]
    assert any("model flagged" in r for r in gaps[0].reasons)
    assert "candidates" in gaps[0].prompt   # alternatives surfaced to the human


def test_apply_answers_overrides_and_confirms():
    cats = [_cat("A", VatTreatment.STANDARD, 0.4)]
    updated, changed = apply_answers(cats, {"A": "zero"})
    assert changed == ["A"]
    assert updated[0].treatment is VatTreatment.ZERO
    assert updated[0].confidence == 1.0  # human-confirmed


def test_apply_answers_keeps_on_empty_or_same():
    cats = [_cat("A", VatTreatment.STANDARD, 0.4)]
    assert apply_answers(cats, {})[1] == []
    assert apply_answers(cats, {"A": "standard"})[1] == []  # same treatment = no change


def test_clarification_log_records_question_and_answer():
    gaps = detect_gaps([_cat("A", VatTreatment.STANDARD, 0.4),
                        _cat("B", VatTreatment.STANDARD, 0.4)])
    _, changed = apply_answers([_cat("A", VatTreatment.STANDARD, 0.4)], {"A": "zero"})
    log = clarification_log(gaps, {"A": "zero"}, changed)

    by_id = {e["txn_id"]: e for e in log}
    assert "desc A" in by_id["A"]["question"]          # the actual question is recorded
    assert by_id["A"]["outcome"] == "changed"
    assert (by_id["A"]["from"], by_id["A"]["to"]) == ("standard", "zero")
    assert by_id["B"]["outcome"] == "kept"             # unanswered gap kept as suggested
    assert by_id["B"]["from"] == by_id["B"]["to"] == "standard"


class _LowConfS1:
    """Marks S1 uncertain (triggers intake); everything else standard/confident."""

    def categorise(self, txns):
        return [TxnCategory(id=t.id, treatment=VatTreatment.STANDARD,
                            category="x", confidence=0.5 if t.id == "S1" else 0.9)
                for t in txns]


def _run(tmp_path, questioner):
    return run_pipeline(
        csv_path=EXAMPLE_CSV, vrn="123456789", client=FakeHmrcVatClient(),
        categoriser=_LowConfS1(), approver=AutoApprover(True),
        questioner=questioner, audit_dir=tmp_path,
    )


def test_intake_override_changes_the_return(tmp_path):
    keep = _run(tmp_path, AutoQuestioner())                    # keep S1 = standard
    override = _run(tmp_path, AutoQuestioner({"S1": "zero"}))  # reclassify S1 -> zero

    assert keep.status == Status.SUBMITTED and override.status == Status.SUBMITTED
    # S1 is a £1200 standard sale → £200 VAT; zero-rating it drops Box 1 by exactly £200.
    assert keep.boxes.box1_vat_due_sales - override.boxes.box1_vat_due_sales == Decimal("200.00")

    events = AuditLogger(override.run_id, tmp_path).read_all()
    steps = [e.step for e in events]
    assert "intake_clarified" in steps
    # A3: the full question/answer is in the audit trail, not just which ids were asked.
    clarified = next(e for e in events if e.step == "intake_clarified")
    qa = {e["txn_id"]: e for e in clarified.payload["qa"]}
    assert qa["S1"]["outcome"] == "changed"
    assert (qa["S1"]["from"], qa["S1"]["to"]) == ("standard", "zero")
    assert qa["S1"]["question"]  # a real question string was recorded


def test_no_gaps_means_no_interrupt(tmp_path):
    # Confident categoriser → intake asks nothing → pipeline runs straight through.
    result = run_pipeline(
        csv_path=EXAMPLE_CSV, vrn="123456789", client=FakeHmrcVatClient(),
        categoriser=type("Conf", (), {"categorise": lambda self, txns: [
            TxnCategory(id=t.id, treatment=VatTreatment.STANDARD, category="x", confidence=0.95)
            for t in txns]})(),
        approver=AutoApprover(True), questioner=AutoQuestioner(), audit_dir=tmp_path,
    )
    assert result.status == Status.SUBMITTED
    steps = [e.step for e in AuditLogger(result.run_id, tmp_path).read_all()]
    assert "intake_clarified" not in steps
    # The agent still ran and audited that it had nothing to ask (CONTRACT §8 A6).
    assert "intake_no_questions" in steps
