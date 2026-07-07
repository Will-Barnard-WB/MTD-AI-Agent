"""Phase C2 — the read-only reviewer produces grounded, cited comments, and is wired
into the approval view."""

from datetime import date
from decimal import Decimal

from mtd_agent.audit import AuditLogger
from mtd_agent.graph.pipeline import run_pipeline
from mtd_agent.graph.state import Status
from mtd_agent.hmrc.fake_client import FakeHmrcVatClient
from mtd_agent.models import CategorisedTransaction, Direction, Transaction, VatTreatment
from mtd_agent.nodes.approval import AutoApprover, build_derivation, render
from mtd_agent.nodes.extract import TxnCategory
from mtd_agent.nodes.intake import AutoQuestioner
from mtd_agent.reviewer import Reviewer, SkillSet


def _cat(desc: str, treatment: VatTreatment) -> CategorisedTransaction:
    txn = Transaction(id="T1", date=date(2026, 1, 1), description=desc,
                      amount=Decimal("105.00"), direction=Direction.PURCHASE)
    return CategorisedTransaction(txn=txn, treatment=treatment, category="x", confidence=0.95)


def _reviewer() -> Reviewer:
    return Reviewer(SkillSet.load("2026-27"))


def test_flags_confidently_wrong_with_citation():
    # High confidence, but domestic fuel classified standard — the reviewer must catch it.
    comments = _reviewer().review([_cat("Reduced-rate domestic fuel", VatTreatment.STANDARD)])
    assert len(comments) == 1
    assert comments[0].citation == "vat-rates#reduced"
    assert "reduced" in comments[0].message
    assert comments[0].severity == "warning"


def test_no_comment_when_treatment_agrees_with_kb():
    assert _reviewer().review([_cat("Reduced-rate domestic fuel", VatTreatment.REDUCED)]) == []


def test_no_comment_when_kb_has_nothing_to_say():
    assert _reviewer().review([_cat("Consulting fee for Q1", VatTreatment.STANDARD)]) == []


def test_every_comment_is_grounded():
    """CONTRACT §8 A3 — no ungrounded assertions: every comment carries a citation."""
    comments = _reviewer().review([
        _cat("Insurance premium", VatTreatment.STANDARD),           # should be exempt
        _cat("Train fare to Leeds", VatTreatment.STANDARD),         # should be zero
    ])
    assert len(comments) == 2
    assert all(c.citation for c in comments)


class _FuelAsStandard:
    """Categoriser that confidently mislabels a fuel purchase as standard."""

    def categorise(self, txns):
        return [TxnCategory(id=t.id, treatment=VatTreatment.STANDARD, category="fuel",
                            confidence=0.95) for t in txns]


def test_reviewer_comments_reach_the_approval_view_and_audit(tmp_path):
    csv = tmp_path / "fuel.csv"
    csv.write_text("id,date,description,amount\n"
                   "P1,2026-01-01,Reduced-rate domestic fuel,105.00\n", encoding="utf-8")
    result = run_pipeline(
        csv_path=csv, vrn="123456789", client=FakeHmrcVatClient(),
        categoriser=_FuelAsStandard(), approver=AutoApprover(True),
        questioner=AutoQuestioner(), audit_dir=tmp_path,
    )
    assert result.status == Status.SUBMITTED
    events = AuditLogger(result.run_id, tmp_path).read_all()
    reviewed = next(e for e in events if e.step == "reviewed")
    assert reviewed.payload["comments"][0]["citation"] == "vat-rates#reduced"


def test_render_shows_cited_comments():
    from mtd_agent.nodes.compute_vat import compute_vat
    from mtd_agent.reviewer import ReviewComment
    boxes = compute_vat([_cat("Reduced-rate domestic fuel", VatTreatment.STANDARD)])
    d = build_derivation(
        boxes=boxes, categorised=[],
        review_comments=[ReviewComment(txn_id="P1", severity="warning",
                                       message="P1 looks off", citation="vat-rates#reduced")],
    )
    text = render(d)
    assert "REVIEWER" in text
    assert "[skill: vat-rates#reduced]" in text
