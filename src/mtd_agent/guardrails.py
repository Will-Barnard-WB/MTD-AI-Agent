"""Input guardrails (v2 A4) — treat transaction descriptions as data, not instructions.

v2 opens a new risk surface: a transaction description is **untrusted text** that flows
into the one LLM call (`extract`). Two concerns (CONTRACT §8 A4):

- **PII** — emails, phone numbers, card/account numbers, NI numbers etc. must not leak to
  the LLM provider. We **redact** them before the description is sent, and audit the kinds
  found (never the raw value — that would re-introduce the PII into the audit log).
- **Prompt injection** — instruction-like text ("ignore previous instructions", "system:")
  aimed at hijacking the categoriser. We **neutralise** the offending span and flag it. The
  attack payload itself is kept in the audit as forensic evidence (it is not PII).

This is deterministic, regex-based **defence in depth**, not a complete solution — the
deterministic core already guarantees the LLM can't emit a figure (§1.1), so at worst an
injection mislabels a *treatment*, which still faces the expert HITL gate. An LLM/RAG-based
detector is deferred. The scanner is pure and side-effect-free; the graph node wires it in
between `ingest` and `extract` and writes the audit event.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from mtd_agent.models import Transaction

# --------------------------------------------------------------------------- #
# Patterns (UK-focused, heuristic). Order matters: email before digit runs.
# --------------------------------------------------------------------------- #

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    # UK National Insurance number, e.g. QQ 12 34 56 C
    ("nino", re.compile(r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b", re.I)),
    # Card number: 13–16 digits, optionally grouped in 4s.
    ("card", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("sort_code", re.compile(r"\b\d{2}-\d{2}-\d{2}\b")),
    # UK phone: +44/0 prefix then 9–10 more digits (spaces/dashes allowed).
    ("phone", re.compile(r"(?:\+44\s?|\b0)\d(?:[\s-]?\d){8,9}\b")),
]

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(?:all\s+|the\s+)?(?:previous|prior|above)\s+"
               r"(?:instructions?|prompts?|text)", re.I),
    re.compile(r"disregard\s+(?:all\s+|the\s+)?(?:previous|prior|above)", re.I),
    re.compile(r"\b(?:system|assistant|user)\s*:", re.I),
    re.compile(r"you\s+are\s+now\b", re.I),
    re.compile(r"\bact\s+as\b", re.I),
    re.compile(r"\bnew\s+instructions?\b", re.I),
    re.compile(r"\boverride\b[^.\n]*\b(?:instructions?|rules?|prompt)\b", re.I),
    re.compile(r"reveal\s+(?:your|the)\s+(?:system\s+)?prompt", re.I),
    re.compile(r"<\|.*?\|>"),  # chat/role control tokens
]


class ScanResult(BaseModel):
    """Outcome of scanning one description. `sanitised` is what the LLM may see."""

    original: str
    sanitised: str
    pii_kinds: list[str] = []      # kinds only — never the raw PII value
    injection_hits: list[str] = []  # the offending phrases (evidence, not PII)

    @property
    def flagged(self) -> bool:
        return bool(self.pii_kinds or self.injection_hits)


class TxnScan(BaseModel):
    """A per-transaction finding, for the audit trail."""

    txn_id: str
    pii_kinds: list[str] = []
    injection_hits: list[str] = []


def scan_description(text: str) -> ScanResult:
    """Redact PII and neutralise injection spans in a single description (pure)."""
    pii_kinds: list[str] = []
    sanitised = text
    for kind, pattern in _PII_PATTERNS:
        if pattern.search(sanitised):
            pii_kinds.append(kind)
            sanitised = pattern.sub(f"[REDACTED:{kind}]", sanitised)

    injection_hits: list[str] = []
    for pattern in _INJECTION_PATTERNS:
        for m in pattern.finditer(sanitised):
            injection_hits.append(m.group(0))
        sanitised = pattern.sub("[FLAGGED]", sanitised)

    return ScanResult(
        original=text,
        sanitised=sanitised,
        pii_kinds=pii_kinds,
        injection_hits=injection_hits,
    )


# --------------------------------------------------------------------------- #
# Output guardrails (§4.3) — an agent may comment/route, never emit a figure or a
# box-mutation instruction (CONTRACT §8 A1, A2). Defence in depth: the core already
# guarantees no agent figure reaches HMRC; this protects the *decision* surface too,
# so even a future LLM-backed reviewer cannot slip a figure into the approval view.
# --------------------------------------------------------------------------- #

_MONEY = re.compile(r"£\s?\d")
_BOX_ASSIGN = re.compile(r"\bbox\s*\d\s*=", re.IGNORECASE)
_BOX_DIRECTIVE = re.compile(r"\b(?:set|change|make|force|override)\b[^.\n]{0,24}\bbox\s*\d",
                            re.IGNORECASE)


def comment_violations(text: str) -> list[str]:
    """Ways an advisory comment would overstep — carry a figure or direct a box change."""
    v: list[str] = []
    if _MONEY.search(text):
        v.append("contains a monetary figure")
    if _BOX_ASSIGN.search(text) or _BOX_DIRECTIVE.search(text):
        v.append("box-mutation directive")
    return v


def enforce_advisory(comments: list) -> tuple[list, list[str]]:
    """Keep only comments that are grounded (cited) and purely advisory (no figure, no
    box-change directive). Returns (kept, dropped_notes). Fail-safe: a violating comment
    is dropped, not shown to the approver — an agent never gets to assert a figure."""
    kept, dropped = [], []
    for c in comments:
        problems = comment_violations(c.message)
        if not c.citation:
            problems.append("ungrounded (no citation)")
        if problems:
            dropped.append(f"{c.citation or '?'}: {', '.join(problems)}")
        else:
            kept.append(c)
    return kept, dropped


def scan_transactions(
    txns: list[Transaction],
) -> tuple[list[Transaction], list[TxnScan]]:
    """Return (safe transactions, findings). Flagged txns get a sanitised description;
    the untouched original stays in `txn.raw` for the audit. Clean txns pass through
    unchanged (identity preserved)."""
    safe: list[Transaction] = []
    findings: list[TxnScan] = []
    for t in txns:
        res = scan_description(t.description)
        if res.flagged:
            safe.append(t.model_copy(update={"description": res.sanitised}))
            findings.append(TxnScan(
                txn_id=t.id, pii_kinds=res.pii_kinds, injection_hits=res.injection_hits,
            ))
        else:
            safe.append(t)
    return safe, findings
