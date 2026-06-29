"""Typed errors for the HMRC layer (CONTRACT.md §4 A3).

Every failure is classified as **user_fixable** or **system** so the pipeline and
the approval UI can tell an accountant whether *they* can resolve it (re-auth,
wrong VRN, a period already filed, a validation rejection) or whether it is a
transport/system problem to retry or escalate. The `kind` is what Stream B
branches on; the `message` is what gets surfaced to the human.
"""

from __future__ import annotations


class HmrcError(Exception):
    """Base for all HMRC client errors. Carries the HMRC status + code when known."""

    kind: str = "system"

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        detail: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.detail = detail or {}

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        bits = [self.message]
        if self.code:
            bits.append(f"[{self.code}]")
        if self.status is not None:
            bits.append(f"(HTTP {self.status})")
        return " ".join(bits)


class HmrcUserError(HmrcError):
    """The accountant can fix this: bad VRN, validation rejection, a period that is
    already filed, or auth that needs re-running. Always safe to show verbatim."""

    kind = "user_fixable"


class HmrcSystemError(HmrcError):
    """Transport failure, 5xx, or an unexpected response shape — not the user's
    fault. Retry or escalate; never silently swallow."""

    kind = "system"


class HmrcAuthError(HmrcUserError):
    """OAuth token is missing/invalid and refresh failed — the user must re-run the
    token flow (`python -m mtd_agent.hmrc.get_token`)."""
