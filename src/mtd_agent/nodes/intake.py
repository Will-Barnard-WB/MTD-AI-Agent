"""v2 A2 — intake / gathering agent: clarify low-confidence categorisations via HITL.

Deterministically detects transactions the categoriser was unsure about and asks the
human to confirm the VAT treatment *before* the return is computed. The pause is a
LangGraph `interrupt()` (see `graph/build.py`) so it survives a checkpointer and, later,
a server. This agent **gathers and questions — it never computes a figure** (CONTRACT.md
§8 A1); a confirmed answer only changes a *label*, and the pure core does the arithmetic.

The question *detection* is deterministic for now (low confidence). An LLM question-author
(deciding what to ask, in natural language) is the next sub-step and slots in behind
`detect_gaps` without changing the interrupt machinery.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from mtd_agent.models import CategorisedTransaction, VatTreatment

_LOW_CONFIDENCE = 0.6


class Gap(BaseModel):
    """A categorisation the human should confirm before compute."""

    txn_id: str
    description: str
    suggested: VatTreatment
    confidence: float

    @property
    def prompt(self) -> str:
        opts = "/".join(t.value for t in VatTreatment)
        return (f"{self.txn_id} '{self.description}' — suggested {self.suggested.value} "
                f"(conf {self.confidence:.2f}). Treatment? [{opts}] (Enter = keep): ")


class IntakeResult(BaseModel):
    """Record of the clarification round, for state + audit."""

    asked: list[str] = []
    answers: dict[str, str] = {}   # txn_id -> chosen treatment value
    changed: list[str] = []        # txn_ids whose treatment the human actually changed


def detect_gaps(categorised: list[CategorisedTransaction]) -> list[Gap]:
    """Transactions the categoriser was not confident about — worth a human confirm."""
    return [
        Gap(txn_id=c.txn.id, description=c.txn.description,
            suggested=c.treatment, confidence=c.confidence)
        for c in categorised if c.confidence < _LOW_CONFIDENCE
    ]


def apply_answers(
    categorised: list[CategorisedTransaction],
    answers: dict[str, str],
) -> tuple[list[CategorisedTransaction], list[str]]:
    """Apply human treatment overrides by txn id. Returns (updated, changed_ids).

    Only a valid, *different* treatment changes anything; a confirmed answer sets
    confidence to 1.0 (human-verified). Unknown/empty answers keep the suggestion.
    """
    valid = {t.value for t in VatTreatment}
    changed: list[str] = []
    out: list[CategorisedTransaction] = []
    for c in categorised:
        choice = (answers.get(c.txn.id) or "").strip().lower()
        if choice in valid and choice != c.treatment.value:
            out.append(c.model_copy(update={
                "treatment": VatTreatment(choice),
                "confidence": 1.0,
                "reasoning": f"human-confirmed (was {c.treatment.value})",
            }))
            changed.append(c.txn.id)
        else:
            out.append(c)
    return out, changed


class Questioner(Protocol):
    """Answers a batch of clarification gaps → {txn_id: treatment value}."""

    def answer(self, gaps: list[Gap]) -> dict[str, str]: ...


class AutoQuestioner:
    """Non-interactive questioner for tests + unattended runs. Default: keep all."""

    def __init__(self, answers: dict[str, str] | None = None) -> None:
        self._answers = answers or {}

    def answer(self, gaps: list[Gap]) -> dict[str, str]:
        return {g.txn_id: self._answers[g.txn_id] for g in gaps if g.txn_id in self._answers}


class CLIQuestioner:
    """Asks the human at the terminal to confirm each uncertain categorisation."""

    def answer(self, gaps: list[Gap]) -> dict[str, str]:
        print("\nSome transactions need confirmation before computing the return:")
        out: dict[str, str] = {}
        for g in gaps:
            resp = input(g.prompt).strip().lower()
            if resp:
                out[g.txn_id] = resp
        return out
