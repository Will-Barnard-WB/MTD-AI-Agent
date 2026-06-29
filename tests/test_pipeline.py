"""End-to-end spine against the fake client + offline categoriser."""

from decimal import Decimal
from pathlib import Path

from mtd_agent.audit import AuditLogger
from mtd_agent.graph.pipeline import run_pipeline
from mtd_agent.graph.state import Status
from mtd_agent.hmrc.fake_client import FakeHmrcVatClient
from mtd_agent.nodes.approval import AutoApprover
from mtd_agent.nodes.extract import FakeCategoriser

EXAMPLE_CSV = Path(__file__).resolve().parents[1] / "examples" / "sample_transactions.csv"


def _run(tmp_path, client, approver=AutoApprover(True)):
    return run_pipeline(
        csv_path=EXAMPLE_CSV, vrn="123456789", client=client,
        categoriser=FakeCategoriser(), approver=approver, audit_dir=tmp_path,
    )


def test_full_slice_submits(tmp_path):
    client = FakeHmrcVatClient()
    result = _run(tmp_path, client)
    assert result.status == Status.SUBMITTED
    assert result.receipt is not None
    # Sample CSV computes to the same boxes verified in test_compute_vat.
    assert result.boxes.box5_net_vat_due == Decimal("100.00")
    assert result.boxes.box6_total_sales_ex_vat == 1100


def test_audit_trail_is_complete(tmp_path):
    result = _run(tmp_path, FakeHmrcVatClient())
    steps = [e.step for e in AuditLogger(result.run_id, tmp_path).read_all()]
    for expected in ["ingest", "extract", "completeness_ok", "compute_vat",
                     "period_resolved", "approved", "submitted"]:
        assert expected in steps


def test_declined_does_not_submit(tmp_path):
    client = FakeHmrcVatClient()
    result = _run(tmp_path, client, approver=AutoApprover(False))
    assert result.status == Status.DECLINED
    assert result.receipt is None


def test_rerun_is_idempotent(tmp_path):
    client = FakeHmrcVatClient()
    r1 = _run(tmp_path, client)
    r2 = _run(tmp_path, client)
    # Same period, same client -> same form bundle, no double-file.
    assert r1.receipt.form_bundle_number == r2.receipt.form_bundle_number


def test_no_open_period_halts(tmp_path):
    client = FakeHmrcVatClient(obligations=[])  # nothing open
    result = _run(tmp_path, client)
    assert result.status == Status.NO_OPEN_PERIOD
    assert result.receipt is None
