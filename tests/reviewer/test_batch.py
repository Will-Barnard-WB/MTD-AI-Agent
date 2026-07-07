"""Phase C3 — batch reviewer sweeps historical audit logs and re-reviews from the trail."""

from pathlib import Path

from mtd_agent.graph.pipeline import run_pipeline
from mtd_agent.hmrc.fake_client import FakeHmrcVatClient
from mtd_agent.models import VatTreatment
from mtd_agent.nodes.approval import AutoApprover
from mtd_agent.nodes.extract import TxnCategory
from mtd_agent.nodes.intake import AutoQuestioner
from mtd_agent.reviewer.batch import review_audit_dir


class _FuelAsStandard:
    def categorise(self, txns):
        return [TxnCategory(id=t.id, treatment=VatTreatment.STANDARD, category="fuel",
                            confidence=0.95) for t in txns]


def _run(tmp_path: Path, csv_body: str):
    csv = tmp_path / f"in-{abs(hash(csv_body)) % 10000}.csv"
    csv.write_text("id,date,description,amount\n" + csv_body, encoding="utf-8")
    return run_pipeline(csv_path=csv, vrn="123456789", client=FakeHmrcVatClient(),
                        categoriser=_FuelAsStandard(), approver=AutoApprover(True),
                        questioner=AutoQuestioner(), audit_dir=tmp_path)


def test_batch_reviews_runs_from_audit_trail(tmp_path):
    _run(tmp_path, "P1,2026-01-01,Reduced-rate domestic fuel,105.00\n")
    _run(tmp_path, "S1,2026-01-01,Consulting fee Q1,1200.00\n")   # clean, no comment

    report = review_audit_dir(audit_dir=tmp_path)
    assert report.runs_reviewed == 2
    assert report.runs_with_warnings == 1
    assert report.by_citation.get("vat-rates#reduced") == 1


def test_batch_report_is_empty_for_clean_runs(tmp_path):
    _run(tmp_path, "S1,2026-01-01,Consulting fee Q1,1200.00\n")
    report = review_audit_dir(audit_dir=tmp_path)
    assert report.runs_reviewed == 1 and report.total_comments == 0


def test_batch_handles_empty_dir(tmp_path):
    report = review_audit_dir(audit_dir=tmp_path)
    assert report.runs_reviewed == 0 and report.per_run == []
