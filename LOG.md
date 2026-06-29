# Build Log
_Append-only. Newest at top. Every instance adds a line at session end._

---

## [2026-06-29] stream-A | HMRC VAT client ported + green (offline scope done)
Branch `stream-a-hmrc` (own git worktree at `../mtd-agent-stream-a` so it can't collide with
the main tree). Built `src/mtd_agent/hmrc/`: `errors.py` (typed `HmrcUserError`/`HmrcSystemError`/
`HmrcAuthError`, `kind = user_fixable|system`), `fraud_headers.py` (ported Gov-Client/Vendor
builder, vendor renamed MTDAgent), `auth.py` (OAuth2 token cache + silent refresh, re-pointed
through `config.Settings`/`assert_sandbox` so the sandbox guard is unavoidable), `idempotency.py`
(persisted `(VRN,periodKey)->SubmitReceipt` ledger), `vat_client.py` (implements the
`HmrcVatClient` Protocol; **no box figure originates here** — serialises a ready `VatReturnPayload`;
idempotent submit; typed error mapping). **14 unit tests green, ruff clean**, all offline via
`httpx.MockTransport`. Did NOT touch `models.py`/`interfaces.py`/`fake_client.py`.
**Still blocked (creds):** the one live sandbox smoke test + the `get_token` first-auth flow.
See BLOCKERS for the new `.env`-in-worktree ask.

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
