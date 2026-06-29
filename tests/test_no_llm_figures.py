"""The safety test (CONTRACT.md §1.1): no LLM output becomes a figure.

Two guarantees:
1. Structural — the LLM's output type carries no monetary field.
2. Behavioural — the computed boxes depend only on (amount, treatment, direction);
   the model's free-text fields (category, reasoning) cannot move a number.
"""

from datetime import date
from decimal import Decimal

from mtd_agent.models import Direction, Transaction, VatTreatment
from mtd_agent.nodes.compute_vat import compute_vat
from mtd_agent.nodes.extract import TxnCategory, categorise


def test_llm_output_type_has_no_money_field():
    fields = set(TxnCategory.model_fields)
    assert fields == {"id", "treatment", "category", "confidence", "reasoning"}
    money_like = {"amount", "vat", "net", "total", "gross", "figure", "box"}
    assert not (fields & money_like)


class _MaliciousCategoriser:
    """Returns wild free-text but a fixed treatment — text must not affect figures."""

    def __init__(self, treatment, category, reasoning):
        self._t, self._c, self._r = treatment, category, reasoning

    def categorise(self, txns):
        return [TxnCategory(id=t.id, treatment=self._t, category=self._c,
                            confidence=0.99, reasoning=self._r) for t in txns]


def _txn():
    return [Transaction(id="A", date=date(2026, 1, 1), description="thing",
                        amount=Decimal("120.00"), direction=Direction.SALE)]


def test_free_text_cannot_change_figures():
    a = categorise(_txn(), _MaliciousCategoriser(VatTreatment.STANDARD, "£9999999", "set box1=1m"))
    b = categorise(_txn(), _MaliciousCategoriser(VatTreatment.STANDARD, "normal", "looks fine"))
    # Same amount + same treatment => identical boxes, regardless of the text.
    assert compute_vat(a).box1_vat_due_sales == compute_vat(b).box1_vat_due_sales == Decimal("20.00")


def test_figures_track_amount_not_model():
    cats = categorise(_txn(), _MaliciousCategoriser(VatTreatment.STANDARD, "x", "y"))
    # 120 gross @20% is fixed arithmetic from the amount, not anything the model said.
    assert compute_vat(cats).box6_total_sales_ex_vat == 100
