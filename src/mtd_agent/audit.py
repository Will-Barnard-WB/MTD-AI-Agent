"""Append-only audit trail (CONTRACT.md §1.5).

One JSONL file per run under audit/. Every node emits an AuditEvent; events are
only ever appended, never edited. This is the record that lets an accountant —
or HMRC — see exactly how each figure was derived and who approved it.
"""

from __future__ import annotations

from pathlib import Path

from mtd_agent.models import AuditEvent

AUDIT_DIR = Path("audit")


class AuditLogger:
    """Append-only writer for a single run's audit trail."""

    def __init__(self, run_id: str, audit_dir: Path = AUDIT_DIR) -> None:
        self.run_id = run_id
        audit_dir.mkdir(parents=True, exist_ok=True)
        self._path = audit_dir / f"{run_id}.jsonl"

    @property
    def path(self) -> Path:
        return self._path

    def emit(self, step: str, payload: dict | None = None) -> AuditEvent:
        """Record one step. Returns the event so callers can also surface it."""
        event = AuditEvent(run_id=self.run_id, step=step, payload=payload or {})
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(event.model_dump_json() + "\n")
        return event

    def read_all(self) -> list[AuditEvent]:
        """Replay the trail (used in tests + verification)."""
        if not self._path.exists():
            return []
        with self._path.open(encoding="utf-8") as fh:
            return [AuditEvent.model_validate_json(line) for line in fh if line.strip()]
