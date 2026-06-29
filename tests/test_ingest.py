"""ingest — CSV parsing, date formats, direction inference."""

from decimal import Decimal

from mtd_agent.models import Direction
from mtd_agent.nodes.ingest import load_transactions


def _write(tmp_path, text):
    p = tmp_path / "t.csv"
    p.write_text(text, encoding="utf-8")
    return p


def test_parses_explicit_direction(tmp_path):
    csv = _write(tmp_path, "id,date,description,amount,direction\n"
                           "A,2026-01-15,Sale,120.00,sale\n")
    txns = load_transactions(csv)
    assert len(txns) == 1
    assert txns[0].direction == Direction.SALE
    assert txns[0].amount == Decimal("120.00")


def test_infers_direction_from_sign(tmp_path):
    csv = _write(tmp_path, "date,description,amount\n"
                           "2026-01-15,Income,500\n"
                           "2026-01-16,Expense,-200\n")
    txns = load_transactions(csv)
    assert txns[0].direction == Direction.SALE
    assert txns[1].direction == Direction.PURCHASE
    assert txns[1].amount == Decimal("200")   # stored absolute


def test_handles_uk_dates_and_currency_symbols(tmp_path):
    csv = _write(tmp_path, "date,description,amount,direction\n"
                           "15/01/2026,Sale,\"£1,200.00\",sale\n")
    txns = load_transactions(csv)
    assert txns[0].amount == Decimal("1200.00")
    assert str(txns[0].date) == "2026-01-15"
