"""Pretty-print a run's audit trail.

Usage:
    python scripts/show_audit.py            # newest run in audit/
    python scripts/show_audit.py <run_id>   # e.g. 034881039945 or the .jsonl name
    python scripts/show_audit.py path/to/file.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

AUDIT_DIR = Path("audit")


def resolve(arg: str | None) -> Path:
    if arg:
        p = Path(arg)
        if p.exists():
            return p
        cand = AUDIT_DIR / (arg if arg.endswith(".jsonl") else f"{arg}.jsonl")
        if cand.exists():
            return cand
        sys.exit(f"no audit file for {arg!r}")
    files = sorted(AUDIT_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        sys.exit("no audit files in audit/ — run a demo first")
    return files[0]


def main() -> int:
    path = resolve(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"# {path}\n")
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        print(f"{event['step']:<22} {json.dumps(event['payload'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
