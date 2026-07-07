# Build Log
_Append-only. Newest at top. Every instance adds a line at session end._

---
## [2026-07-08] supervisor | Scheme router promoted to a live front-of-graph node (interrupt HITL)
Closed the half-wired gap: `classify_scheme` was tested/eval'd but not a live node — scheme came
in as config. Now a `supervisor` node runs first (`START → supervisor → ingest → …`), resolving the
scheme: explicit > classified-from-`business_profile` > **ask the human via `interrupt()` when
unsure** > standard default. Scheme now flows through `GraphState` (resolved by the node); `_compute`
reads it. New `SchemeChooser`/`AutoSchemeChooser`/`CLISchemeChooser` (parallel to intake's Questioner);
`run_pipeline` gains `business_profile` + `scheme_chooser`; the interrupt driver handles both the
scheme question and intake gaps. CLI: `demo --scheme/--profile/--flat-rate-percent` (verified live —
a conflicting profile prompts "Which scheme?"). Audit: `scheme_resolved` with source
(provided/classified/asked/default). Both supervisor halves (gather=intake, route=this) are now live
nodes. 100 tests green, ruff clean.

## [2026-07-07] v2 Sessions 2–5 | Phase C (reviewer+skills), Phase B (schemes), hardening — v2 DONE
Built the rest of v2 in one block (96 tests green, ruff clean):
- **Session 2 (C1+C2):** versioned skills KB `skills/hmrc/2026-27/*.md` (anchored, citable rules) +
  `reviewer/` — a read-only-by-construction reviewer emitting grounded, **cited** comments, wired
  into the approval view (`reviewed` audit event). Catches confidently-wrong via independent rules
  (e.g. fuel-as-standard → `[skill: vat-rates#reduced]`).
- **Session 3 (C3+C4):** `cli review` batch sweep over audit logs (extract event now records the
  sanitised description so runs re-review from the trail alone) + reviewer eval (100% precision/
  recall, citation-checked; false positives held at zero).
- **Session 4 (Phase B):** pure `compute_vat_flat_rate` + `compute_vat_cash`; `classify_scheme`
  supervisor router (standard/flat-rate/cash, **asks when unsure**); compute node routes on scheme
  (via run config); routing eval 100% accuracy + 100% asks-when-unsure.
- **Session 5 (hardening):** output guardrails — `enforce_advisory` drops any reviewer comment that
  carries a figure or a box-mutation directive or is ungrounded (`reviewer_guardrail` audit); a
  structural test proves **submit is only reachable via approval** (no gate bypass); adversarial
  guardrails eval (PII + injection variants + clean controls) all pass.
Eval harnesses now: intake, reviewer, routing, guardrails (+ core). Deferred non-goals stand (ITSA,
RAG, multi-tenant, production recognition). **v2 roadmap complete.** Next track: the dashboard.

## [2026-07-07] v2 Session 1 | Intake calibration — the dormant HITL gate is now live
Fixed the dormant intake gate (FakeCategoriser hardcoded 0.9; gpt-4o-mini overconfident, so
`detect_gaps` <0.6 never fired). Two complementary layers, for two failure modes:
- **Explicit `needs_review` self-flag** (+ `candidates`) replaces the arbitrary numeric score as the
  primary signal — the model says "I'm unsure" and lists plausible treatments (Fake flags its
  default guesses; OpenAI prompt/schema updated; real-model behaviour pending a live `--real-llm`).
  Catches what the model *knows* it's shaky on.
- **Provider-independent ambiguity heuristic** in `detect_gaps` (`extract.matched_treatments` +
  opaque-description check) — flags objectively-hard transactions (opaque/generic, or conflicting
  cues) regardless of confidence. Catches what the model is *confidently wrong* about.
Gaps carry `reasons` (surfaced in the question + audited in `intake_clarified.qa`). FakeCategoriser
now reports honest confidence (0.9 matched / 0.35 guess) so intake fires offline (verified: sample
CSV flags S1+P1). New eval case `confidently_wrong`; 67 tests green, eval 100%, ruff clean.
**Deferred:** OpenAI logprobs (self-report shares the confidently-wrong blind spot, so the explicit
flag + heuristic supersede it). **Next: Session 2** — Skills KB + real-time reviewer (Phase C1+C2).

## [2026-07-06] v2 A4 | Input guardrails (PII redaction + injection neutralisation) — Phase A DONE
New `src/mtd_agent/guardrails.py`: a pure, deterministic regex scanner that runs as a graph node
**between `ingest` and `extract`** (`ingest → guardrails → extract → …`). It **redacts PII**
(email, UK NINO, card, sort code, phone) and **neutralises prompt-injection** spans ("ignore
previous instructions", role tokens, etc.) in transaction descriptions before the one LLM call
ever sees them — descriptions are data, not instructions (CONTRACT §8 A4). Sanitised text flows on;
the untouched original stays in `txn.raw`. Audit: `guardrails_flagged` records PII *kinds* (never
raw values) + the injection phrases as evidence, else `guardrails_ok`. Defence-in-depth: the core
already blocks figures (§1.1), so worst case an injection mislabels a treatment → still hits the
HITL gate. Tests: 62 green (was 53), ruff clean; incl. an E2E test proving the categoriser only
ever sees sanitised text. **Phase A (A1–A4) complete. Next: Phase B** — supervisor VAT-scheme
routing + pure `compute_vat_flat_rate`/`compute_vat_cash` + routing eval set.

## [2026-07-06] v2 A3 | Full intake Q&A audited + intake eval set (completeness detection)
Phase A A3 done. **Audit:** `intake_clarified` now carries a structured `qa` log — per gap the
exact question, the human's raw answer, and the outcome (kept vs changed, from→to *label* only,
never a figure). New `intake.clarification_log()`. The intake node also emits `intake_no_questions`
when it runs but has nothing to ask, so the agent's activity is always in the trail (CONTRACT §8 A6).
**Eval:** new `src/mtd_agent/intake_eval.py` + `evals/intake/cases.json` (5 golden cases) measure
whether the detector catches what it should — recall (safety-critical: a miss lets an uncertain item
through unasked) and precision (don't over-ask). `detect_gaps` scores 100%/100%. Tests: 53 green
(was 44), ruff clean. **Next: A4** — guardrails v1 (PII + prompt-injection scan on txn descriptions).

## [2026-07-01] v2-plan | V2_PLAN.md written — agents at the edges
Planned v2: a conversational **supervisor** (intake + VAT-scheme routing, with an `ask_user` HITL
tool), an **audit reviewer** (read-only, cited comments from versioned HMRC **skill files** —
real-time in the approval view first, batch `review` second), and the harness (adopt **LangGraph**
`StateGraph`/`interrupt()`, permissioned tools, guardrails vs prompt-injection, agent evals,
richer audit). Governing rule preserved: agents gather/route/question/comment — never compute a
figure or bypass the gate. Locked: VAT-scheme routing first (ITSA deferred), skill files (no RAG
yet), real-time reviewer first. LangGraph is currently a dep but unused; v1 stays a pure orchestrator.


## [2026-07-01] v1-DONE | Live sandbox submit + idempotent re-run PASS — DoD met
**v1 is functionally complete.** Will ran `demo --live` against the real HMRC VAT sandbox:
submitted and got form bundle **034881039945**; re-ran and got the **same** bundle (idempotent,
no double-file) → DoD #3 and #5 proven end-to-end. Fixes this session:
- `pipeline.py`: obligations query window was ±365 days (>HMRC's 366-day cap) → live
  `INVALID_DATE_RANGE`. Narrowed to ±180 days.
- `fake_client.py`: default open obligation was hard-coded to Q1-2026; once "today" advanced past
  it the today-relative window missed it (demo + tests returned NO_OPEN_PERIOD). Made the default
  obligation **anchored to today** (start−45/end+45/due+75) → date-stable demo and tests.
- **Eval harness (PLAN 3.3)** added: `src/mtd_agent/eval_harness.py` + `evals/cases/` (3 labelled
  CSVs) + `tests/test_evals.py`. Measures deterministic-core correctness (compute_vat vs
  hand-computed expected boxes) and categorisation accuracy. Offline Fake = 90%; run the online
  OpenAI eval with `python -m mtd_agent.eval_harness --real-llm`.
- **44 tests green, ruff clean.** Subscriptions needed on the sandbox app: VAT (MTD) [required],
  Create Test User, Test Fraud Prevention Headers.
**Only remaining (optional):** archive the old prototypes (3.4) now that make demo passes live.

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
