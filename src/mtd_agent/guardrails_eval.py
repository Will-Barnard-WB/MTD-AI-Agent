"""Adversarial guardrails eval (hardening): does the input scanner catch PII + injection?

Golden set of PII variants (email, card grouped/plain, sort code, NI number spaced/tight,
UK/intl phone), prompt-injection variants (ignore/disregard/role-token/act-as/new-instructions),
combos, and clean controls that must NOT trip a false positive. Detection is the safety metric;
a false positive on clean text (over-redaction) is the quality metric.

    ./.venv/bin/python -m mtd_agent.guardrails_eval
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from mtd_agent.guardrails import scan_description

CASES_PATH = Path(__file__).resolve().parents[2] / "evals" / "guardrails" / "cases.json"


@dataclass
class GCase:
    name: str
    text: str
    pii: set[str]
    injection: bool


def load_cases(path: Path = CASES_PATH) -> list[GCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [GCase(c["name"], c["text"], set(c["pii"]), bool(c["injection"])) for c in raw]


def main() -> int:
    cases = load_cases()
    print("Guardrails eval — input scanner\n")
    print(f"{'case':<16} {'want-pii':>18} {'got-pii':>18} {'inj':>5} {'ok':>4}")
    print("-" * 66)

    ok_all = True
    for c in cases:
        r = scan_description(c.text)
        got = set(r.pii_kinds)
        inj = bool(r.injection_hits)
        ok = got == c.pii and inj == c.injection
        ok_all &= ok
        print(f"{c.name:<16} {','.join(sorted(c.pii)) or '-':>18} {','.join(sorted(got)) or '-':>18} "
              f"{str(inj):>5} {('yes' if ok else 'NO'):>4}")

    print("-" * 66)
    print("all cases pass" if ok_all else "FAILURES present")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
