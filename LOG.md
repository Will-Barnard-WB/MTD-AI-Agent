# Build Log
_Append-only. Newest at top. Every instance adds a line at session end._

---

## [2026-06-29] stream-b | Pipeline slice complete, green, demo runs end-to-end
Stream B (pipeline) built against the Fake client + offline categoriser — no creds used.
28 tests pass, ruff clean. Nodes: `ingest` (CSV→Transactions, UK dates/£, direction inference),
`extract` (the ONLY LLM call — OpenAI Structured Outputs `OpenAICategoriser` + offline
`FakeCategoriser`; returns `TxnCategory` with **no money field**, merged to txns by id),
`completeness` (deterministic guard), `compute_vat` (**PURE**, exhaustively tested, gross-strip +
rounding), `approval` (HITL — full derivation render + anomaly flags + `CLIApprover`/`AutoApprover`),
`submit` (delegates to Protocol, idempotent). Spine in `graph/pipeline.py` with audit at every step;
`cli.py demo` runs `examples/sample_transactions.csv` → boxes → approval → fake submit → audit log.
Safety test `test_no_llm_figures` proves model free-text cannot move a figure.
**Deviation flagged (Stream-B-internal, no shared surface):** spine is an explicit orchestrator,
not yet a LangGraph StateGraph — nodes kept pure so a LangGraph/interrupt wrapper layers on later
(see `graph/state.py` docstring). **For Phase 3:** swap `FakeHmrcVatClient` → Stream A's real
`vat_client` in `cli.py` + `run_pipeline`. New VAT-rule questions for the accountant added to
`BLOCKERS.md` (gross vs net amounts, box 6-9 rounding). Did NOT touch `models.py`/`interfaces.py`.

## [2026-06-29] phase-0 | Foundations built — FROZEN SHARED SURFACE, streams may now split
Phase 0 complete and green (13 tests, ruff clean, Python 3.12). Built:
- `models.py` — all domain models. `VatBoxes` enforces box3=box1+box2 and box5=|box3-box4|
  at construction; `CategorisedTransaction` carries NO monetary field (LLM categorises only).
- `interfaces.py` — `HmrcVatClient` Protocol (**contract-version: 1**) — THE parallelisation
  boundary. Stream B codes against this + the Fake; Stream A implements it.
- `config.py` — `assert_sandbox()` chokepoint (rejects prod/lookalike hosts); `Settings.load()`
  is credential-free at import (only reads env when called).
- `audit.py` — append-only JSONL `AuditLogger`.
- `hmrc/fake_client.py` — `FakeHmrcVatClient` (idempotent submit, canned open obligation) =
  the behavioural contract Stream A's real client must match.
- Scaffold: `pyproject.toml` (src layout, py>=3.12), `Makefile`, tests, `.venv` (gitignored).
**Streams may now run in parallel.** Stream A owns `src/mtd_agent/hmrc/` (except fake_client),
Stream B owns `nodes/`, `graph/`, `cli.py`. Do NOT edit `models.py`/`interfaces.py` without a
contract-version bump + a note here. NOTE for setup: use **python3.12** (system python3 is 3.9).

## [2026-06-29] setup | Repo planned + work contract written (pre-code)
Created the handoff package: `CONTRACT.md` (binding rules + safety principles + interface
contract + workstream ownership), `PLAN.md` (architecture, layout, action list), `CLAUDE.md`
(session bootstrap), `BLOCKERS.md`, this log. **No code yet** — next session is Phase 0
(scaffold + `models.py` + `interfaces.py` + `config.py` + `audit.py`), done by one instance
before the Stream A / Stream B parallel split. Decision: greenfield combining `AgentWorkflows`
(LangGraph spine) + `AIAccountant` (HMRC VAT plumbing); both archived once `make demo` passes.
VAT-first (proven plumbing already exists). Waiting on Will for the items in `BLOCKERS.md`.
