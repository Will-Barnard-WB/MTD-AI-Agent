"""Phase C1 — skills KB loads, parses anchors, and retrieves by description."""

from mtd_agent.models import VatTreatment
from mtd_agent.reviewer.skills import SkillSet


def test_loads_versioned_rules_with_citations():
    ss = SkillSet.load("2026-27")
    assert ss.tax_year == "2026-27"
    citations = {r.citation for r in ss.rules()}
    # A few known anchors must be present and citable.
    assert {"vat-rates#reduced", "vat-rates#zero", "vat-scope#exempt",
            "vat-scope#outside-scope"} <= citations


def test_rule_carries_treatments_and_keywords():
    ss = SkillSet.load("2026-27")
    reduced = ss.get("vat-rates#reduced")
    assert reduced is not None
    assert reduced.treatments == {VatTreatment.REDUCED}
    assert any("fuel" in k for k in reduced.keywords)


def test_match_retrieves_by_description():
    ss = SkillSet.load("2026-27")
    hits = {r.citation for r in ss.match("Reduced-rate domestic fuel bill")}
    assert "vat-rates#reduced" in hits


def test_unknown_tax_year_is_empty_not_error():
    ss = SkillSet.load("1999-00")
    assert ss.rules() == []
