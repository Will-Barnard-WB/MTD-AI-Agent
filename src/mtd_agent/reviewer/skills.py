"""Versioned HMRC skills knowledge base (Phase C1).

Curated markdown skill files under `skills/hmrc/<tax-year>/*.md`. Each rule has a stable
anchor so the reviewer can cite it (`vat-rates#reduced`). Retrieval is provenance-first:
matching a description returns the *rules* (with their citations), never a figure. Rules
are versioned by tax year (CONTRACT §8 A5).

Skill-file format (per rule):

    ## <Title> {#anchor}
    - treatments: reduced
    - keywords: domestic fuel, gas, electricity
    - rule: <the rule text the reviewer may cite>
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from mtd_agent.models import VatTreatment

_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = _ROOT / "skills" / "hmrc"

_HEADING = re.compile(r"^##\s+(?P<title>.+?)\s+\{#(?P<anchor>[a-z0-9-]+)\}\s*$")
_BULLET = re.compile(r"^-\s+(?P<key>treatments|keywords|rule):\s*(?P<val>.+?)\s*$")


class SkillRule(BaseModel):
    """One citable rule from a skill file."""

    file: str                       # skill-file stem, e.g. "vat-rates"
    anchor: str                     # e.g. "reduced"
    title: str
    tax_year: str
    treatments: set[VatTreatment]   # the treatment(s) this rule endorses
    keywords: list[str]             # description cues (lower-case)
    text: str

    @property
    def citation(self) -> str:
        return f"{self.file}#{self.anchor}"


def _parse_file(path: Path, tax_year: str) -> list[SkillRule]:
    stem = path.stem
    rules: list[SkillRule] = []
    cur: dict | None = None

    def _flush() -> None:
        if cur and cur.get("rule"):
            rules.append(SkillRule(
                file=stem, anchor=cur["anchor"], title=cur["title"], tax_year=tax_year,
                treatments={VatTreatment(t.strip()) for t in cur.get("treatments", "").split(",")
                            if t.strip()},
                keywords=[k.strip().lower() for k in cur.get("keywords", "").split(",") if k.strip()],
                text=cur["rule"],
            ))

    for line in path.read_text(encoding="utf-8").splitlines():
        m = _HEADING.match(line)
        if m:
            _flush()
            cur = {"title": m["title"], "anchor": m["anchor"]}
            continue
        if cur is not None:
            b = _BULLET.match(line)
            if b:
                cur[b["key"]] = b["val"]
    _flush()
    return rules


class SkillSet:
    """The loaded skill rules for one tax year. Read-only lookup by description or citation."""

    def __init__(self, rules: list[SkillRule], tax_year: str) -> None:
        self._rules = rules
        self.tax_year = tax_year
        self._by_citation = {r.citation: r for r in rules}

    @classmethod
    def load(cls, tax_year: str = "2026-27", skills_dir: Path = SKILLS_DIR) -> SkillSet:
        year_dir = skills_dir / tax_year
        rules: list[SkillRule] = []
        if year_dir.is_dir():
            for path in sorted(year_dir.glob("*.md")):
                rules.extend(_parse_file(path, tax_year))
        return cls(rules, tax_year)

    def rules(self) -> list[SkillRule]:
        return list(self._rules)

    def get(self, citation: str) -> SkillRule | None:
        return self._by_citation.get(citation)

    def match(self, description: str) -> list[SkillRule]:
        """Rules whose keywords appear in the description (provenance-first retrieval)."""
        desc = description.lower()
        return [r for r in self._rules if any(k in desc for k in r.keywords)]
