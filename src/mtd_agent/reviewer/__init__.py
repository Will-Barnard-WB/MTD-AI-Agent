"""v2 Phase C — the read-only audit reviewer + its HMRC skills knowledge base.

The reviewer is a **second opinion for the expert**, never an authority (CONTRACT §8 A3):
it reads the categorised transactions and a versioned skills KB and emits grounded,
**cited** comments. It cannot mutate pipeline state or submit, and it never blocks — the
human decides. Every comment carries a skill-file citation.
"""

from mtd_agent.reviewer.reviewer import ReviewComment, Reviewer
from mtd_agent.reviewer.skills import SkillRule, SkillSet

__all__ = ["ReviewComment", "Reviewer", "SkillRule", "SkillSet"]
