"""Dashboard data layer — run summaries + traces derived from the audit trail."""

from decimal import Decimal
from pathlib import Path

from dashboard import data
from mtd_agent.graph.pipeline import run_pipeline
from mtd_agent.hmrc.fake_client import FakeHmrcVatClient
from mtd_agent.models import VatScheme, VatTreatment
from mtd_agent.nodes.approval import AutoApprover
from mtd_agent.nodes.extract import TxnCategory
from mtd_agent.nodes.intake import AutoQuestioner

EXAMPLE_CSV = Path(__file__).resolve().parents[2] / "examples" / "sample_transactions.csv"


class _AllStandard:
    def categorise(self, txns):
        return [TxnCategory(id=t.id, treatment=VatTreatment.STANDARD, category="x",
                            confidence=0.95) for t in txns]


def _run(tmp_path, **kw):
    return run_pipeline(csv_path=EXAMPLE_CSV, vrn="123456789", client=FakeHmrcVatClient(),
                        categoriser=_AllStandard(), approver=AutoApprover(True),
                        questioner=AutoQuestioner(), audit_dir=tmp_path, **kw)


def test_list_runs_empty_dir(tmp_path):
    assert data.list_runs(tmp_path) == []


def test_summary_captures_status_scheme_and_period(tmp_path):
    r = _run(tmp_path, scheme=VatScheme.STANDARD)
    runs = data.list_runs(tmp_path)
    assert len(runs) == 1
    s = runs[0]
    assert s.run_id == r.run_id
    assert s.status == "submitted"
    assert s.scheme == "standard"
    assert s.period_key is not None
    assert s.n_txns == 5
    assert s.n_events >= 7


def test_trace_covers_the_pipeline_in_order(tmp_path):
    r = _run(tmp_path)
    steps = [s.step for s in data.load_trace(r.run_id, tmp_path)]
    assert steps[0] == "scheme_resolved"          # supervisor runs first
    assert steps[-1] == "submitted"
    for expected in ("ingest", "extract", "compute_vat", "approved"):
        assert expected in steps


def test_trace_steps_have_family_and_durations(tmp_path):
    r = _run(tmp_path)
    steps = data.load_trace(r.run_id, tmp_path)
    assert data.family("compute_vat") == "compute"
    assert data.family("submitted") == "submit"
    # all but the last step have a non-negative duration
    assert all(s.duration_ms is None or s.duration_ms >= 0 for s in steps)


def test_declined_run_status(tmp_path):
    _run(tmp_path, )  # a submitted one
    run_pipeline(csv_path=EXAMPLE_CSV, vrn="123456789", client=FakeHmrcVatClient(),
                 categoriser=_AllStandard(), approver=AutoApprover(False),
                 questioner=AutoQuestioner(), audit_dir=tmp_path)
    statuses = {s.status for s in data.list_runs(tmp_path)}
    assert {"submitted", "declined"} <= statuses


def test_flat_rate_scheme_shows_in_summary(tmp_path):
    _run(tmp_path, scheme=VatScheme.FLAT_RATE, flat_rate_percent=Decimal("14.5"))
    assert any(s.scheme == "flat_rate" for s in data.list_runs(tmp_path))
