"""The read-only audit reviewer (Phase C2).

A second opinion for the expert. Given the categorised transactions (and, in batch mode,
a reconstructed run), it emits **grounded, cited** comments — every comment references a
skill file. It is read-only *by construction*: it takes data and returns comments; it holds
no client, no state, and no submit capability, so it cannot bypass the gate or move a figure
(CONTRACT §8 A1, A3). It never blocks — the human decides.
"""

from __future__ import annotations

from pydantic import BaseModel

from mtd_agent.models import CategorisedTransaction
from mtd_agent.reviewer.skills import SkillSet


class ReviewComment(BaseModel):
    """One advisory, cited comment. `citation` is mandatory — no ungrounded assertions."""

    txn_id: str | None
    severity: str          # "warning" (likely misclassification) | "info"
    message: str
    citation: str          # skill-file citation, e.g. "vat-rates#reduced"


class Reviewer:
    """Read-only reviewer over a versioned skills KB."""

    def __init__(self, skills: SkillSet) -> None:
        self._skills = skills

    def review(self, categorised: list[CategorisedTransaction]) -> list[ReviewComment]:
        """Flag transactions whose assigned treatment conflicts with the skills KB.

        For each transaction, the KB rules whose keywords the description matches are
        retrieved; if none of the matched rules endorse the assigned treatment, that is a
        grounded reason to double-check — surfaced as a cited warning. This catches
        'confidently wrong' via independent rules, not the model's own confidence."""
        comments: list[ReviewComment] = []
        for c in categorised:
            matched = self._skills.match(c.txn.description)
            if not matched:
                continue
            endorsed = any(c.treatment in r.treatments for r in matched)
            if endorsed:
                continue
            # No matched rule endorses the assigned treatment → cite the closest rule.
            rule = matched[0]
            suggested = "/".join(sorted(t.value for t in rule.treatments))
            comments.append(ReviewComment(
                txn_id=c.txn.id,
                severity="warning",
                message=(f"{c.txn.id} '{c.txn.description}' classified {c.treatment.value}, but "
                         f"{rule.title} suggests {suggested}."),
                citation=rule.citation,
            ))
        return comments
