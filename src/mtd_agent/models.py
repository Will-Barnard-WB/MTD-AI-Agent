"""Shared domain models — the common vocabulary for Stream A and Stream B.

PHASE 0 — FROZEN SURFACE. Changes here ripple into both streams, so treat edits
as a contract change: only in Phase 0, or by an explicit agreed update noted in
LOG.md (see CONTRACT.md §3).

Money is always Decimal. The VAT box rounding quirks are encoded here on purpose:
HMRC wants boxes 1-5 to 2 decimal places and boxes 6-9 as whole pounds (integers).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, model_validator

# --------------------------------------------------------------------------- #
# Transaction-level models
# --------------------------------------------------------------------------- #


class Direction(str, Enum):
    """Whether a transaction is money in (a sale/output) or out (a purchase/input)."""

    SALE = "sale"
    PURCHASE = "purchase"


class VatTreatment(str, Enum):
    """The VAT treatment the LLM assigns to a transaction.

    The LLM picks one of these *labels* — it never computes the VAT amount.
    The rate each maps to lives in compute (Stream B), not here, so rate changes
    are a deterministic-core concern, not a model edit.
    """

    STANDARD = "standard"          # 20%
    REDUCED = "reduced"            # 5%
    ZERO = "zero"                  # 0%
    EXEMPT = "exempt"              # no VAT, excluded from box 6/7 net? (kept; handled in compute)
    OUTSIDE_SCOPE = "outside_scope"  # not a VAT transaction at all


class Transaction(BaseModel):
    """A raw transaction parsed deterministically from the input CSV (no LLM)."""

    id: str
    date: date
    description: str
    amount: Decimal = Field(description="Gross amount as it appears on the statement (see "
                                        "amount_is_gross assumption in compute).")
    direction: Direction
    raw: dict[str, str] = Field(default_factory=dict, description="Original CSV row, for audit.")


class CategorisedTransaction(BaseModel):
    """A Transaction plus the LLM's classification.

    SAFETY: the model contributes only `treatment`, `category`, `confidence`,
    `reasoning`, `needs_review`, `candidates` — all labels/signals, NO monetary
    figure. compute_vat derives every number from `txn.amount` + `treatment`.
    """

    txn: Transaction
    treatment: VatTreatment
    category: str = Field(description="Human-readable bookkeeping category, e.g. 'fuel', 'rent'.")
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(default="", description="Short why, surfaced in the approval view.")
    needs_review: bool = Field(default=False, description="The model's explicit 'I'm not "
                               "sure' flag — a cleaner self-signal than the numeric confidence.")
    candidates: list[VatTreatment] = Field(default_factory=list, description="Plausible "
                                           "alternative treatments when unsure — shown to the human.")


# --------------------------------------------------------------------------- #
# VAT return models
# --------------------------------------------------------------------------- #


class VatBoxes(BaseModel):
    """The 9 VAT boxes, computed purely from categorised transactions.

    Consistency invariants (box3 = box1+box2, box5 = |box3-box4|) are enforced
    here — so a compute bug that breaks them fails fast at construction, before
    anything can be shown for approval or submitted.
    """

    box1_vat_due_sales: Decimal              # VAT due on sales and other outputs
    box2_vat_due_acquisitions: Decimal       # VAT due on acquisitions (EC) — usually 0 post-Brexit
    box3_total_vat_due: Decimal              # = box1 + box2
    box4_vat_reclaimed: Decimal              # VAT reclaimed on purchases and other inputs
    box5_net_vat_due: Decimal                # = |box3 - box4|  (always >= 0)
    box6_total_sales_ex_vat: int             # whole pounds
    box7_total_purchases_ex_vat: int         # whole pounds
    box8_total_goods_supplied_ex_vat: int    # whole pounds
    box9_total_acquisitions_ex_vat: int      # whole pounds

    @model_validator(mode="after")
    def _check_invariants(self) -> VatBoxes:
        if self.box3_total_vat_due != self.box1_vat_due_sales + self.box2_vat_due_acquisitions:
            raise ValueError("box3 must equal box1 + box2")
        if self.box5_net_vat_due != abs(self.box3_total_vat_due - self.box4_vat_reclaimed):
            raise ValueError("box5 must equal |box3 - box4|")
        if self.box5_net_vat_due < 0:
            raise ValueError("box5 must be non-negative")
        return self


class VatReturnPayload(BaseModel):
    """Exactly what the HMRC MTD VAT submit endpoint expects.

    Field names mirror the HMRC API so the client can serialise directly.
    """

    periodKey: str
    vatDueSales: Decimal
    vatDueAcquisitions: Decimal
    totalVatDue: Decimal
    vatReclaimedCurrPeriod: Decimal
    netVatDue: Decimal
    totalValueSalesExVAT: int
    totalValuePurchasesExVAT: int
    totalValueGoodsSuppliedExVAT: int
    totalAcquisitionsExVAT: int
    finalised: bool = False

    @classmethod
    def from_boxes(cls, *, period_key: str, boxes: VatBoxes, finalised: bool) -> VatReturnPayload:
        return cls(
            periodKey=period_key,
            vatDueSales=boxes.box1_vat_due_sales,
            vatDueAcquisitions=boxes.box2_vat_due_acquisitions,
            totalVatDue=boxes.box3_total_vat_due,
            vatReclaimedCurrPeriod=boxes.box4_vat_reclaimed,
            netVatDue=boxes.box5_net_vat_due,
            totalValueSalesExVAT=boxes.box6_total_sales_ex_vat,
            totalValuePurchasesExVAT=boxes.box7_total_purchases_ex_vat,
            totalValueGoodsSuppliedExVAT=boxes.box8_total_goods_supplied_ex_vat,
            totalAcquisitionsExVAT=boxes.box9_total_acquisitions_ex_vat,
            finalised=finalised,
        )


class ObligationStatus(str, Enum):
    OPEN = "O"
    FULFILLED = "F"


class Obligation(BaseModel):
    """An HMRC VAT obligation period — the window you submit a return against."""

    period_key: str
    start: date
    end: date
    due: date
    status: ObligationStatus
    received: date | None = None


class SubmitReceipt(BaseModel):
    """HMRC's response to a successful submission — the proof of filing."""

    processing_date: datetime
    form_bundle_number: str
    charge_ref_number: str | None = None
    payment_indicator: str | None = None


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #


class AuditEvent(BaseModel):
    """One immutable step in a run's audit trail (see audit.py)."""

    run_id: str
    step: str
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict = Field(default_factory=dict)
