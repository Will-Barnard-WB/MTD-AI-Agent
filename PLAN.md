# Build Plan — MTD Agent v1

Companion to `CONTRACT.md` (the rules) — this is the **architecture, layout, and action list**.

---

## Why a new repo (not extend either prototype)

| Prototype | Keep | Problem |
|-----------|------|---------|
| `AgentWorkflows` | LangGraph spine, node separation, guardrails, HITL checkpoints, audit, eval harness | not a git repo; carries multi-agent/dashboard scope we don't want in v1 |
| `AIAccountant` | **HMRC plumbing that works** (`auth`, `fraud_headers`, `vat_client`, `bookkeeping`), `.env`, `get_token` | architected as a Claude-Code skill assistant, not a deterministic pipeline |

Greenfield lets us take the **deterministic spine** from one and the **proven HMRC plumbing**
from the other, under one clean git history and the safety contract. Both old repos are
**archived** once `make demo` passes.

---

## Target directory layout

```
mtd-agent/
├── CONTRACT.md            ← binding rules (read first, every session)
├── PLAN.md                ← this file
├── CLAUDE.md              ← session bootstrap for Claude Code instances
├── LOG.md                 ← append-only: every session notes what changed
├── BLOCKERS.md            ← asks that only Will can resolve (creds, VAT rules, test users)
├── README.md
├── .env.example           ← committed; real .env is git-ignored
├── pyproject.toml / requirements.txt
├── Makefile               ← make setup | test | demo
├── data/                  ← sample transaction CSVs (git-ignored if real)
├── audit/                 ← append-only JSONL run logs (git-ignored)
├── src/mtd_agent/
│   ├── models.py          ← [Phase 0] pydantic domain models (shared)
│   ├── interfaces.py      ← [Phase 0] HmrcVatClient Protocol (the contract boundary)
│   ├── config.py          ← [Phase 0] env + model-id + sandbox base URL
│   ├── audit.py           ← [Phase 0] append-only AuditLogger
│   ├── hmrc/              ← [Stream A] auth, fraud_headers, vat_client, fakes
│   │   ├── auth.py
│   │   ├── fraud_headers.py
│   │   ├── vat_client.py        # implements HmrcVatClient
│   │   └── fake_client.py       # FakeHmrcVatClient for offline tests
│   ├── nodes/            ← [Stream B] ingest, extract, guard, compute_vat, approve, submit, audit
│   │   ├── ingest.py
│   │   ├── extract.py           # the ONLY LLM call
│   │   ├── completeness.py
│   │   ├── compute_vat.py       # PURE — fully unit-tested
│   │   ├── approval.py          # HITL gate
│   │   └── submit.py
│   ├── graph/           ← [Stream B] LangGraph wiring + state
│   │   ├── state.py
│   │   └── graph.py
│   └── cli.py           ← [Stream B] `demo` entrypoint
└── tests/
    ├── test_compute_vat.py      # deterministic fixtures → expected boxes
    ├── test_no_llm_figures.py   # the safety test (model output ≠ box figure)
    ├── test_idempotency.py
    ├── test_sandbox_guard.py    # base URL is sandbox
    └── hmrc/test_vat_client.py  # mocked + one live smoke test
```

---

## Domain models (Phase 0 — the shared vocabulary)

- `Transaction` — raw parsed CSV row (date, description, amount, direction, raw fields).
- `CategorisedTransaction` — `Transaction` + LLM-assigned category + VAT treatment + confidence.
- `VatBoxes` — the 9 boxes (box1…box9), all `Decimal`, computed purely.
- `VatReturnPayload` — what HMRC's submit endpoint expects (boxes + periodKey + finalised flag).
- `Obligation` — an HMRC obligation period (periodKey, start, end, due, status).
- `SubmitReceipt` — HMRC response (processingDate, formBundleNumber, chargeRefNumber).
- `AuditEvent` — `{run_id, step, ts, payload}` for the append-only log.

---

## Action list (execution order)

### Phase 0 — Foundations  *(one instance, before the parallel split)*
- [ ] **0.1** Scaffold repo: layout above, `pyproject`/`requirements`, ruff + pytest config, `Makefile`, `.env.example`, `.gitignore` (`.env`, `audit/`, real `data/`).
- [ ] **0.2** `models.py` — all pydantic domain models above, with `Decimal` money + validation.
- [ ] **0.3** `config.py` (env, model id, **sandbox base URL**) + `audit.py` (append-only JSONL `AuditLogger`).
- [ ] **0.4** `interfaces.py` — `HmrcVatClient` Protocol + `hmrc/fake_client.py` `FakeHmrcVatClient` returning canned obligations/receipts. **This unblocks both streams.**

### Stream A — HMRC integration  *(Instance A, branch `stream-a-hmrc`)*
- [ ] **A1** Port + harden `auth.py`: OAuth2 sandbox flow, token cache + refresh.
- [ ] **A2** Port `fraud_headers.py`: mandatory `Gov-Client-*` headers; validate via HMRC's Test Fraud Prevention Headers API.
- [ ] **A3** `vat_client.py` implementing the Protocol: `get_obligations`, `submit_vat_return` (**idempotent** on `(VRN, periodKey)`), `retrieve_vat_return`. Typed errors tagged `user_fixable | system`.
- [ ] **A4** Tests: unit (mocked httpx) + **one live sandbox smoke test** using Will's test user.

### Stream B — Pipeline + deterministic core  *(Instance B, branch `stream-b-pipeline`, codes against the Protocol + Fake)*
- [ ] **B1** `nodes/ingest.py` — CSV → `list[Transaction]`.
- [ ] **B2** `nodes/extract.py` — single structured-output Messages call → `CategorisedTransaction[]`. **The only LLM call.**
- [ ] **B3** `nodes/completeness.py` — deterministic completeness guard; route back if inputs incomplete.
- [ ] **B4** `nodes/compute_vat.py` — **PURE** `compute_vat(txns) -> VatBoxes`. Fully unit-tested with fixtures.
- [ ] **B5** `nodes/approval.py` — render full derivation (boxes + source txns + prior-period deltas + anomaly flags) → await explicit human approval.
- [ ] **B6** `nodes/submit.py` — on approval, call `client.submit_vat_return` via the Protocol; idempotency key.
- [ ] **B7** Audit wiring — emit `AuditEvent` from each node.
- [ ] **B8** `graph/` — LangGraph wiring of the spine + `cli.py demo` entrypoint.

### Phase 3 — Integration  *(either instance, after A + B green on their own)*
- [ ] **3.1** Swap `FakeHmrcVatClient` → real `vat_client`; run the full slice against sandbox.
- [ ] **3.2** `make demo` acceptance run + idempotency re-run.
- [ ] **3.3** Minimal eval harness: a few labelled CSVs → expected boxes (deterministic) + categorisation accuracy.
- [ ] **3.4** Archive `AgentWorkflows` + `AIAccountant` (move to `~/Documents/_archive/`), note in `LOG.md`.

---

## How to run two instances

1. One instance does **Phase 0** alone and commits to `main`.
2. Then launch **Instance A** (`stream-a-hmrc`) and **Instance B** (`stream-b-pipeline`) in
   parallel — they share only `models.py` + `interfaces.py`, which are now frozen.
3. They reconcile at **Phase 3** once both branches are green.

Each instance: read `CONTRACT.md` → check `BLOCKERS.md` → work only its directories → append to
`LOG.md` at session end.
