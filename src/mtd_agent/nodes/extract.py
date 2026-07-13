"""B2 — extract: the ONLY LLM call. Categorise transactions (no figures).

SAFETY BOUNDARY (CONTRACT.md §1.1–1.2):
- The LLM returns `TxnCategory` objects — id + treatment + category + confidence
  + reasoning. There is **no monetary field** on `TxnCategory`, so a model can
  never emit a figure that flows into a box.
- `categorise()` joins those labels back to the original Transactions BY ID;
  every downstream figure is computed from `txn.amount` in pure Python.
- The provider sits behind the `Categoriser` Protocol, so swapping OpenAI for
  another backend is a config change, not a pipeline change.
"""

from __future__ import annotations

import json
from typing import Protocol

from pydantic import BaseModel, Field

from mtd_agent.models import CategorisedTransaction, Transaction, VatTreatment


class TxnCategory(BaseModel):
    """The LLM's per-transaction classification. NO money field by design."""

    id: str
    treatment: VatTreatment
    category: str = Field(description="Bookkeeping category, e.g. 'fuel', 'rent'.")
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    needs_review: bool = False   # the model's explicit "I'm not sure" self-flag
    candidates: list[VatTreatment] = Field(default_factory=list)  # plausible alternatives


class Categoriser(Protocol):
    def categorise(self, txns: list[Transaction]) -> list[TxnCategory]: ...


def categorise(txns: list[Transaction], categoriser: Categoriser) -> list[CategorisedTransaction]:
    """Run the categoriser and merge labels back onto transactions by id."""
    by_id = {c.id: c for c in categoriser.categorise(txns)}
    out: list[CategorisedTransaction] = []
    for txn in txns:
        cat = by_id.get(txn.id)
        if cat is None:
            continue  # the completeness guard (B3) turns this into a hard stop
        out.append(
            CategorisedTransaction(
                txn=txn,
                treatment=cat.treatment,
                category=cat.category,
                confidence=cat.confidence,
                reasoning=cat.reasoning,
                needs_review=cat.needs_review,
                candidates=cat.candidates,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# OpenAI backend (Structured Outputs, strict json_schema)
# --------------------------------------------------------------------------- #

_SYSTEM = (
    "You are a UK VAT bookkeeping assistant. For each transaction, assign the correct "
    "VAT treatment and a short bookkeeping category. Do NOT compute any amounts — only "
    "classify. Treatments: 'standard' (20%), 'reduced' (5%), 'zero' (0% e.g. most food, "
    "books, public transport), 'exempt' (e.g. insurance, rent of residential property, "
    "financial services), 'outside_scope' (e.g. salaries/wages, dividends, transfers). "
    "Give one short sentence of reasoning. "
    "Set 'needs_review' to true whenever the transaction could plausibly take more than one "
    "treatment, the description is too vague to be sure, or it is an edge case you would want "
    "a human to confirm — do NOT default to false just to seem confident. When 'needs_review' "
    "is true, list the plausible treatments in 'candidates' (otherwise leave it empty). "
    "Also give a confidence in [0,1] as a secondary signal."
)

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "treatment", "category", "confidence", "reasoning",
                             "needs_review", "candidates"],
                "properties": {
                    "id": {"type": "string"},
                    "treatment": {
                        "type": "string",
                        "enum": [t.value for t in VatTreatment],
                    },
                    "category": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reasoning": {"type": "string"},
                    "needs_review": {"type": "boolean"},
                    "candidates": {
                        "type": "array",
                        "items": {"type": "string", "enum": [t.value for t in VatTreatment]},
                    },
                },
            },
        }
    },
}


def _format_txns(txns: list[Transaction]) -> str:
    lines = ["Classify these transactions (amounts are context only — do not echo or sum them):"]
    for t in txns:
        lines.append(f"- id={t.id} | {t.date} | {t.direction.value} | {t.description} | £{t.amount}")
    return "\n".join(lines)


class OpenAICategoriser:
    """Categoriser backed by OpenAI Structured Outputs."""

    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        # LangSmith: when tracing is on, this records each categorisation as a nested LLM
        # span (prompt, response, tokens) under the graph run. No-op when tracing is off.
        try:
            from langsmith.wrappers import wrap_openai

            client = wrap_openai(client)
        except Exception:  # langsmith optional — never let tracing break categorisation
            pass
        self._client = client
        self._model = model

    def categorise(self, txns: list[Transaction]) -> list[TxnCategory]:
        resp = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "categorisations", "strict": True, "schema": _SCHEMA},
            },
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _format_txns(txns)},
            ],
        )
        data = json.loads(resp.choices[0].message.content)
        return [TxnCategory(**item) for item in data["items"]]


# --------------------------------------------------------------------------- #
# Offline backend — keyword rules. For tests + credit-free demo runs.
# --------------------------------------------------------------------------- #

_KEYWORD_RULES: list[tuple[tuple[str, ...], VatTreatment]] = [
    (("salary", "wages", "payroll", "dividend", "transfer"), VatTreatment.OUTSIDE_SCOPE),
    (("insurance", "rent", "interest"), VatTreatment.EXEMPT),
    (("train", "rail", "food", "book", "bus"), VatTreatment.ZERO),
]


def matched_treatments(description: str) -> set[VatTreatment]:
    """Which VAT treatments the offline keyword rules cue for a description.

    Provider-independent — used by intake's ambiguity heuristic (a description that
    cues *two* different treatments is objectively worth a human check, whatever the
    model's self-reported confidence)."""
    desc = description.lower()
    return {mapped for keywords, mapped in _KEYWORD_RULES if any(k in desc for k in keywords)}


class FakeCategoriser:
    """Deterministic, network-free categoriser. NOT for production accuracy —
    a stand-in so the pipeline (and the demo) runs without spending LLM credits.

    Reports *honest* confidence: high when a keyword rule fired, low when it fell
    through to the default (a genuine guess). This is what lets intake fire offline
    — a fixed 0.9 made the clarification gate dormant."""

    def __init__(self, default: VatTreatment = VatTreatment.STANDARD) -> None:
        self._default = default

    def categorise(self, txns: list[Transaction]) -> list[TxnCategory]:
        out: list[TxnCategory] = []
        for t in txns:
            desc = t.description.lower()
            treatment, matched = self._default, False
            for keywords, mapped in _KEYWORD_RULES:
                if any(k in desc for k in keywords):
                    treatment, matched = mapped, True
                    break
            if matched:
                confidence, reasoning = 0.9, "keyword-rule (offline fake)"
            else:
                confidence, reasoning = 0.35, "no keyword rule matched — default guess (offline fake)"
            out.append(TxnCategory(
                id=t.id, treatment=treatment,
                category=desc.split()[0] if desc else "uncategorised",
                confidence=confidence, reasoning=reasoning,
                needs_review=not matched,   # honest: flag the guesses for a human
            ))
        return out
