"""Phase C4 — reviewer eval: catches true issues with the right citation, no false positives."""

from mtd_agent.reviewer import Reviewer, SkillSet
from mtd_agent.reviewer_eval import load_cases, run_case


def _reviewer():
    return Reviewer(SkillSet.load("2026-27"))


def test_cases_cover_both_polarities():
    cases = load_cases()
    assert any(c.should_flag for c in cases)
    assert any(not c.should_flag for c in cases)


def test_no_false_positives():
    """A false positive erodes trust in the second opinion — hold it at zero."""
    r = _reviewer()
    for case in load_cases():
        if not case.should_flag:
            assert not run_case(case, r).flagged, f"false positive on {case.name}"


def test_catches_true_issues_with_correct_citation():
    r = _reviewer()
    for case in load_cases():
        if case.should_flag:
            res = run_case(case, r)
            assert res.flagged, f"missed true issue {case.name}"
            if case.expect_citation:
                assert res.citation == case.expect_citation, case.name


def test_every_case_scores_correct():
    r = _reviewer()
    assert all(run_case(c, r).correct for c in load_cases())
