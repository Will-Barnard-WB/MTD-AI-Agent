"""The console's step-by-step HITL driver — proves the full interrupt choreography
(scheme → intake → approval → submit) the browser relies on, using fakes."""

from decimal import Decimal
from pathlib import Path

from dashboard.session import RunSession
from mtd_agent.graph.state import Status
from mtd_agent.hmrc.fake_client import FakeHmrcVatClient
from mtd_agent.models import VatTreatment
from mtd_agent.nodes.extract import TxnCategory

EXAMPLE_CSV = Path(__file__).resolve().parents[2] / "examples" / "sample_transactions.csv"


class _FlagsS1:
    """Confident everywhere except S1, which it flags for review (fires intake)."""

    def categorise(self, txns):
        return [TxnCategory(id=t.id, treatment=VatTreatment.STANDARD, category="x",
                            confidence=0.9, needs_review=(t.id == "S1")) for t in txns]


def _create(tmp_path, **kw):
    return RunSession.create(csv_path=EXAMPLE_CSV, vrn="123456789",
                             client=FakeHmrcVatClient(), categoriser=_FlagsS1(),
                             audit_dir=tmp_path, **kw)


def test_full_hitl_flow_scheme_then_intake_then_approval(tmp_path):
    sess = _create(tmp_path, business_profile="flat rate scheme and cash accounting both apply")
    sess.start()

    # 1) supervisor asks for the scheme (conflicting profile)
    assert sess.pending["ask"] == "vat_scheme"
    sess.resume({"scheme": "standard"})

    # 2) intake asks about the flagged transaction
    gaps = sess.pending["gaps"]
    assert any(g["txn_id"] == "S1" for g in gaps)
    sess.resume({"answers": {}})            # keep the suggestion

    # 3) approval gate presents the derivation
    assert sess.pending["ask"] == "approval"
    assert "derivation" in sess.pending
    sess.resume({"approved": True})

    # 4) done → submitted
    assert sess.done
    assert sess.status == Status.SUBMITTED


def test_decline_at_the_gate_halts(tmp_path):
    sess = _create(tmp_path, scheme=None, business_profile="")   # no scheme question
    sess.start()
    # confident-but-flagged S1 still triggers intake first
    assert sess.pending["gaps"]
    sess.resume({"answers": {}})
    assert sess.pending["ask"] == "approval"
    sess.resume({"approved": False})
    assert sess.done and sess.status == Status.DECLINED


def test_override_at_intake_changes_the_return(tmp_path):
    a = _create(tmp_path).start()
    a.resume({"answers": {}})                                  # keep S1 standard
    a.resume({"approved": True})

    b = _create(tmp_path).start()
    b.resume({"answers": {"S1": "zero"}})                      # reclassify S1
    b.resume({"approved": True})

    # S1 is a £1200 standard sale → £200 VAT; zero-rating drops Box 1 by £200.
    assert (a.result["boxes"].box1_vat_due_sales
            - b.result["boxes"].box1_vat_due_sales) == Decimal("200.00")


def test_flat_rate_via_session(tmp_path):
    sess = _create(tmp_path, scheme=None, business_profile="we are on the flat rate scheme",
                   flat_rate_percent=Decimal("14.5")).start()
    # scheme classified confidently (no scheme question) → straight to intake
    assert sess.pending.get("ask") != "vat_scheme"
    sess.resume({"answers": {}})
    sess.resume({"approved": True})
    assert sess.status == Status.SUBMITTED
    assert sess.result["boxes"].box4_vat_reclaimed == Decimal("0.00")
