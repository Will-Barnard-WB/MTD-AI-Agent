"""Phase B — pure per-scheme compute + supervisor routing + end-to-end flat-rate run."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from mtd_agent.audit import AuditLogger
from mtd_agent.graph.pipeline import run_pipeline
from mtd_agent.graph.state import Status
from mtd_agent.hmrc.fake_client import FakeHmrcVatClient
from mtd_agent.models import (
    CategorisedTransaction,
    Direction,
    Transaction,
    VatScheme,
    VatTreatment,
)
from mtd_agent.nodes.approval import AutoApprover
from mtd_agent.nodes.compute_vat import compute_vat, compute_vat_cash, compute_vat_flat_rate
from mtd_agent.nodes.intake import AutoQuestioner
from mtd_agent.nodes.routing import classify_scheme
from mtd_agent.routing_eval import load_cases

EXAMPLE_CSV = Path(__file__).resolve().parents[1] / "examples" / "sample_transactions.csv"


def _sale(txn_id: str, amount: str, treatment: VatTreatment) -> CategorisedTransaction:
    txn = Transaction(id=txn_id, date=date(2026, 1, 1), description="x",
                      amount=Decimal(amount), direction=Direction.SALE)
    return CategorisedTransaction(txn=txn, treatment=treatment, category="", confidence=0.9)


# --- Flat rate (pure) ----------------------------------------------------- #

def test_flat_rate_boxes():
    cats = [_sale("S1", "1200.00", VatTreatment.STANDARD),
            _sale("S2", "600.00", VatTreatment.ZERO)]
    boxes = compute_vat_flat_rate(cats, Decimal("14.5"))
    # 14.5% of £1800 gross turnover = £261.00; Box 6 = gross turnover (FRS quirk); no reclaim.
    assert boxes.box1_vat_due_sales == Decimal("261.00")
    assert boxes.box6_total_sales_ex_vat == 1800
    assert boxes.box4_vat_reclaimed == Decimal("0.00")
    assert boxes.box7_total_purchases_ex_vat == 0
    assert boxes.box5_net_vat_due == Decimal("261.00")


def test_flat_rate_excludes_outside_scope():
    cats = [_sale("S1", "1000.00", VatTreatment.STANDARD),
            _sale("S2", "5000.00", VatTreatment.OUTSIDE_SCOPE)]
    boxes = compute_vat_flat_rate(cats, Decimal("10"))
    assert boxes.box6_total_sales_ex_vat == 1000        # outside-scope not in turnover
    assert boxes.box1_vat_due_sales == Decimal("100.00")


def test_cash_equals_standard_for_bank_txn_input():
    cats = [_sale("S1", "1200.00", VatTreatment.STANDARD)]
    assert compute_vat_cash(cats) == compute_vat(cats)


# --- Supervisor routing (B1) ---------------------------------------------- #

def test_classify_scheme_clear_signals():
    assert classify_scheme("On the Flat Rate Scheme") is VatScheme.FLAT_RATE
    assert classify_scheme("we use cash accounting") is VatScheme.CASH
    assert classify_scheme("standard scheme, accrual basis") is VatScheme.STANDARD


def test_classify_scheme_asks_when_unsure():
    assert classify_scheme("flat rate and cash accounting") is None   # conflicting
    assert classify_scheme("a small shop in Leeds") is None           # no signal
    assert classify_scheme("") is None


def test_routing_eval_cases_all_pass():
    for c in load_cases():
        assert classify_scheme(c.profile) == c.expected, c.name


# --- End to end (routing changes the computed return) --------------------- #

class _AllStandardSales:
    def categorise(self, txns):
        from mtd_agent.nodes.extract import TxnCategory
        return [TxnCategory(id=t.id, treatment=VatTreatment.STANDARD, category="x",
                            confidence=0.95) for t in txns]


def test_pipeline_routes_flat_rate(tmp_path):
    result = run_pipeline(
        csv_path=EXAMPLE_CSV, vrn="123456789", client=FakeHmrcVatClient(),
        categoriser=_AllStandardSales(), approver=AutoApprover(True),
        questioner=AutoQuestioner(), scheme=VatScheme.FLAT_RATE,
        flat_rate_percent=Decimal("14.5"), audit_dir=tmp_path,
    )
    assert result.status == Status.SUBMITTED
    # Flat-rate Box 1 is a % of gross turnover, not summed per-transaction VAT.
    assert result.boxes.box4_vat_reclaimed == Decimal("0.00")


# --- Live supervisor node (B1 wired into the graph) ----------------------- #

def _run_super(tmp_path, **kw):
    return run_pipeline(
        csv_path=EXAMPLE_CSV, vrn="123456789", client=FakeHmrcVatClient(),
        categoriser=_AllStandardSales(), approver=AutoApprover(True),
        questioner=AutoQuestioner(), audit_dir=tmp_path, **kw,
    )


def _scheme_resolved(tmp_path, run_id) -> dict:
    events = AuditLogger(run_id, tmp_path).read_all()
    return next(e for e in events if e.step == "scheme_resolved").payload


def test_supervisor_classifies_scheme_from_profile(tmp_path):
    r = _run_super(tmp_path, business_profile="We use cash accounting for VAT")
    assert _scheme_resolved(tmp_path, r.run_id) == {"scheme": "cash", "source": "classified"}


def test_supervisor_asks_when_unsure_and_uses_the_answer(tmp_path):
    from mtd_agent.nodes.routing import AutoSchemeChooser
    r = _run_super(tmp_path, business_profile="flat rate scheme and cash accounting both apply",
                   scheme_chooser=AutoSchemeChooser("cash"))
    assert r.status == Status.SUBMITTED
    assert _scheme_resolved(tmp_path, r.run_id) == {"scheme": "cash", "source": "asked"}


def test_supervisor_explicit_scheme_skips_classification(tmp_path):
    r = _run_super(tmp_path, scheme=VatScheme.STANDARD,
                   business_profile="mentions flat rate but is ignored")
    assert _scheme_resolved(tmp_path, r.run_id)["source"] == "provided"


def test_supervisor_defaults_to_standard_with_no_hint(tmp_path):
    r = _run_super(tmp_path)
    assert _scheme_resolved(tmp_path, r.run_id) == {"scheme": "standard", "source": "default"}
