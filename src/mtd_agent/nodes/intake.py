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

import re
from typing import Protocol

from pydantic import BaseModel

from mtd_agent.models import CategorisedTransaction, VatTreatment
from mtd_agent.nodes.extract import matched_treatments

_LOW_CONFIDENCE = 0.6

# Tokens that carry no categorisation signal — a description made only of these (or
# too short) is opaque and worth a human check, however confident the model claims to be.
_GENERIC_TOKENS = {
    "misc", "miscellaneous", "sundry", "sundries", "payment", "transfer", "ref",
    "reference", "adjustment", "correction", "other", "txn", "transaction", "item", "na",
}


def _informative_tokens(description: str) -> list[str]:
    words = re.findall(r"[a-z]+", description.lower())
    return [w for w in words if len(w) > 2 and w not in _GENERIC_TOKENS]


def ambiguity_reasons(description: str) -> list[str]:
    """Provider-independent reasons a categorisation is objectively worth confirming —
    independent of the model's (often overconfident) self-reported confidence. This is
    the calibration signal that catches 'confidently wrong'."""
    reasons: list[str] = []
    if not _informative_tokens(description):
        reasons.append("opaque/low-information description")
    cues = matched_treatments(description)
    if len(cues) >= 2:
        reasons.append(f"conflicting treatment cues ({', '.join(sorted(t.value for t in cues))})")
    return reasons


class Gap(BaseModel):
    """A categorisation the human should confirm before compute."""

    txn_id: str
    description: str
    suggested: VatTreatment
    confidence: float
    reasons: list[str] = []   # why this was flagged (calibration + confidence)

    @property
    def prompt(self) -> str:
        opts = "/".join(t.value for t in VatTreatment)
        why = f" [{'; '.join(self.reasons)}]" if self.reasons else ""
        return (f"{self.txn_id} '{self.description}' — suggested {self.suggested.value} "
                f"(conf {self.confidence:.2f}){why}. Treatment? [{opts}] (Enter = keep): ")


class IntakeResult(BaseModel):
    """Record of the clarification round, for state + audit."""

    asked: list[str] = []
    answers: dict[str, str] = {}   # txn_id -> chosen treatment value
    changed: list[str] = []        # txn_ids whose treatment the human actually changed


def detect_gaps(categorised: list[CategorisedTransaction]) -> list[Gap]:
    """Transactions worth a human confirm before compute.

    Flags on *either* low (calibrated) confidence *or* a provider-independent ambiguity
    signal (opaque or conflicting-cue descriptions). The second arm is the calibration
    fix: it catches transactions the model is confidently wrong about — where a raw
    confidence threshold alone would let them through."""
    gaps: list[Gap] = []
    for c in categorised:
        reasons = ambiguity_reasons(c.txn.description)
        if c.confidence < _LOW_CONFIDENCE:
            reasons.append(f"low confidence ({c.confidence:.2f})")
        if reasons:
            gaps.append(Gap(txn_id=c.txn.id, description=c.txn.description,
                            suggested=c.treatment, confidence=c.confidence, reasons=reasons))
    return gaps


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


def clarification_log(
    gaps: list[Gap],
    answers: dict[str, str],
    changed: list[str],
) -> list[dict]:
    """Structured question/answer record for the audit trail (A3, CONTRACT §8 A6).

    One entry per gap: the exact question put to the human, their raw answer, and the
    outcome (kept the suggestion vs changed it, with from→to treatment). This is the
    record that lets an accountant see *what was asked and how it was resolved* — no
    figure is ever recorded here, only labels (A1)."""
    changed_set = set(changed)
    log: list[dict] = []
    for g in gaps:
        raw = (answers.get(g.txn_id) or "").strip().lower()
        was_changed = g.txn_id in changed_set
        log.append({
            "txn_id": g.txn_id,
            "question": g.prompt,
            "reasons": g.reasons,
            "answer": raw,
            "outcome": "changed" if was_changed else "kept",
            "from": g.suggested.value,
            "to": raw if was_changed else g.suggested.value,
        })
    return log


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
