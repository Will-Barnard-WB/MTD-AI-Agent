# Build Log
_Append-only. Newest at top. Every instance adds a line at session end._

---

## [2026-06-29] phase-3 | Streams integrated; --live wired; get_token built — only the live run remains
Merged `stream-a-hmrc` into master (resolved the predicted LOG.md conflict, kept both stream
blocks). Wired the real client into `cli.py`: new `--live` flag swaps `FakeHmrcVatClient` →
`HmrcVatClient` (offline Fake stays the default); creds/VRN pre-checks + a graceful `HmrcError`
catch (no more tracebacks — points the user at get_token). Ported the one-time OAuth flow to
`src/mtd_agent/hmrc/get_token.py` (`python -m mtd_agent.hmrc.get_token`). **42 tests green, ruff
clean; offline `demo --fake-llm` runs the full slice end-to-end.** Discovery: `.env` already has
HMRC_CLIENT_ID/SECRET/TEST_VRN — the ONLY remaining blocker for the live run is the OAuth token
(run get_token, which needs the redirect URI registered) + `.env` present in the run's working tree.
**Not yet done (DoD #3/#5):** a real submission to the VAT sandbox + idempotent re-run. Also still
open: eval harness (3.3) and archiving the old prototypes (3.4, after make demo passes live).

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
