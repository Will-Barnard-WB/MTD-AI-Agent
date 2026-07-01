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
from mtd_agent.nodes.intake import AutoQuestioner, apply_answers, detect_gaps

EXAMPLE_CSV = Path(__file__).resolve().parents[1] / "examples" / "sample_transactions.csv"


def _cat(txn_id: str, treatment: VatTreatment, conf: float) -> CategorisedTransaction:
    txn = Transaction(id=txn_id, date=date(2026, 1, 1), description=f"desc {txn_id}",
                      amount=Decimal("120.00"), direction=Direction.SALE)
    return CategorisedTransaction(txn=txn, treatment=treatment, category="x", confidence=conf)


def test_detect_gaps_flags_low_confidence():
    cats = [_cat("A", VatTreatment.STANDARD, 0.9), _cat("B", VatTreatment.STANDARD, 0.4)]
    gaps = detect_gaps(cats)
    assert [g.txn_id for g in gaps] == ["B"]


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

    steps = [e.step for e in AuditLogger(override.run_id, tmp_path).read_all()]
    assert "intake_clarified" in steps


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
