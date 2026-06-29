"""B1 — ingest: parse a transactions CSV into typed Transactions (no LLM).

Expected columns (header row, case-insensitive): date, description, amount.
Optional: id, direction. If `direction` is absent it is inferred from the sign
of `amount` (positive → sale/income, negative → purchase/expense). `amount` is
stored as the absolute GROSS value; `direction` carries the sign's meaning.
"""

from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from mtd_agent.models import Direction, Transaction

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")


def _parse_date(value: str) -> date:
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date {value!r} (expected one of {_DATE_FORMATS})")


def _parse_amount(value: str) -> Decimal:
    cleaned = value.strip().replace("£", "").replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Unparseable amount {value!r}") from exc


def load_transactions(path: str | Path) -> list[Transaction]:
    path = Path(path)
    out: list[Transaction] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        # Normalise headers to lower-case for tolerant lookup.
        for i, raw_row in enumerate(reader, start=1):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items()}
            amount = _parse_amount(row["amount"])
            if row.get("direction"):
                direction = Direction(row["direction"].lower())
            else:
                direction = Direction.SALE if amount >= 0 else Direction.PURCHASE
            out.append(
                Transaction(
                    id=row.get("id") or f"row-{i}",
                    date=_parse_date(row["date"]),
                    description=row["description"],
                    amount=abs(amount),
                    direction=direction,
                    raw=row,
                )
            )
    return out
