"""Routing eval harness (Phase B3): scheme-classification accuracy + "asks when unsure".

Two things measured over `evals/routing/cases.json`:
- **Accuracy** — did the classifier pick the right scheme when there was a clear signal?
- **Asks when unsure** — on ambiguous/signal-free profiles (expected null), did it correctly
  return None (defer to a human) instead of guessing? Guessing a scheme is the dangerous
  failure — it silently changes which compute runs.

    ./.venv/bin/python -m mtd_agent.routing_eval
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from mtd_agent.models import VatScheme
from mtd_agent.nodes.routing import classify_scheme

CASES_PATH = Path(__file__).resolve().parents[2] / "evals" / "routing" / "cases.json"


@dataclass
class RoutingCase:
    name: str
    profile: str
    expected: VatScheme | None


def load_cases(path: Path = CASES_PATH) -> list[RoutingCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [RoutingCase(c["name"], c["profile"],
                        VatScheme(c["expected"]) if c["expected"] else None) for c in raw]


def main() -> int:
    cases = load_cases()
    print("Routing eval — scheme classifier\n")
    print(f"{'case':<20} {'expected':>10} {'got':>10} {'ok':>4}")
    print("-" * 48)

    decided_ok = decided_total = ask_ok = ask_total = 0
    for c in cases:
        got = classify_scheme(c.profile)
        ok = got == c.expected
        if c.expected is None:
            ask_total += 1
            ask_ok += ok
        else:
            decided_total += 1
            decided_ok += ok
        print(f"{c.name:<20} {(c.expected.value if c.expected else 'ASK'):>10} "
              f"{(got.value if got else 'ASK'):>10} {('yes' if ok else 'NO'):>4}")

    print("-" * 48)
    acc = decided_ok / decided_total if decided_total else 1.0
    ask = ask_ok / ask_total if ask_total else 1.0
    print(f"decided accuracy: {acc:.0%}   asks-when-unsure: {ask:.0%}")
    return 0 if decided_ok == decided_total and ask_ok == ask_total else 1


if __name__ == "__main__":
    raise SystemExit(main())
