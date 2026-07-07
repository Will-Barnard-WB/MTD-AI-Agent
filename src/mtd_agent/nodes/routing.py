"""Supervisor scheme routing (Phase B1).

Classifies which VAT scheme a business is on from a short profile/description, so the
pipeline can route to the matching pure compute (standard / flat-rate / cash). Like
intake, it **asks when unsure** rather than guessing: an ambiguous or signal-free profile
returns None, which the caller turns into a clarification question — never a silent default.
The router only *picks a path*; the path's compute is still pure and gated (CONTRACT §8 A2).
"""

from __future__ import annotations

from typing import Protocol

from mtd_agent.models import VatScheme

_FLAT_RATE_CUES = ("flat rate", "flat-rate", " frs", "frs ")
_CASH_CUES = ("cash accounting", "cash basis", "cash scheme")
_STANDARD_CUES = ("standard scheme", "accrual", "invoice basis", "standard vat")


def classify_scheme(profile: str) -> VatScheme | None:
    """Return the scheme, or None when unsure (conflicting or no signal → ask the human)."""
    text = f" {profile.lower()} "
    flat = any(k in text for k in _FLAT_RATE_CUES)
    cash = any(k in text for k in _CASH_CUES)
    standard = any(k in text for k in _STANDARD_CUES)

    picked = [s for s, hit in (
        (VatScheme.FLAT_RATE, flat), (VatScheme.CASH, cash), (VatScheme.STANDARD, standard),
    ) if hit]
    if len(picked) == 1:
        return picked[0]
    return None   # zero signals (unsure) or multiple (conflicting) → ask


class SchemeChooser(Protocol):
    """Answers the supervisor's scheme question when classification is unsure.
    `prompt` carries the profile + valid options; returns a VatScheme *value* string."""

    def choose(self, prompt: dict) -> str: ...


class AutoSchemeChooser:
    """Non-interactive chooser for tests + unattended runs. Default: standard."""

    def __init__(self, scheme: str = VatScheme.STANDARD.value) -> None:
        self._scheme = scheme

    def choose(self, prompt: dict) -> str:
        return self._scheme


class CLISchemeChooser:
    """Asks the human at the terminal which VAT scheme applies."""

    def choose(self, prompt: dict) -> str:
        opts = "/".join(prompt.get("options", [s.value for s in VatScheme]))
        profile = prompt.get("profile", "")
        resp = input(f"\nVAT scheme unclear for '{profile}'. Which scheme? "
                     f"[{opts}] (Enter = standard): ").strip().lower()
        return resp or VatScheme.STANDARD.value
