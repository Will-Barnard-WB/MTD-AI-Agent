# Work Contract — MTD Agent v1 (VAT vertical slice)

> This file is the **binding agreement** for every Claude Code instance working on this repo.
> Read it in full at the start of every session. It exists so **two instances can build in
> parallel without colliding**. If a rule here conflicts with something you want to do, stop
> and flag it — do not silently deviate.

---

## 0. What we are building (one paragraph)

A new project that combines the best of two prior prototypes — `AgentWorkflows` (LangGraph
deterministic spine, nodes, guardrails, HITL checkpoints, audit) and `AIAccountant` (working
HMRC sandbox plumbing: OAuth2 auth, fraud-prevention headers, VAT client, CSV bookkeeping) —
into **one clean vertical slice**:

```
drop a transactions CSV
  → INGEST            (deterministic: CSV → typed Transactions)
  → EXTRACT/CATEGORISE (the ONLY LLM call — structured output, schema-constrained)
  → COMPLETENESS GUARD (deterministic — not the model's judgement)
  → COMPUTE VAT        (PURE Python — the 9 boxes; no LLM)
  → APPROVAL GATE      (HITL — expert reviews full derivation, then approves)
  → SUBMIT             (idempotent call to HMRC VAT sandbox)
  → AUDIT              (append-only log of every step)
```

v1 proves this spine **end-to-end on the HMRC VAT sandbox**. Nothing more.

Both old prototypes are **superseded** by this repo and should be archived once v1 runs — do
not import from them at runtime; port deliberately, file by file.

---

## 1. Non-negotiable safety principles (the architecture IS the safety case)

These are not style preferences. Violating one is a defect, even if tests pass.

1. **Deterministic core.** The LLM **never emits a number that reaches HMRC.** The model only
   *categorises/extracts* transactions into typed objects. **All arithmetic** (box totals, VAT
   due) is pure Python over those typed objects. Enforced by types: `compute_vat()` takes
   `CategorisedTransaction[]` and returns `VatBoxes` — there is no code path where model text
   becomes a box figure.
2. **Structured outputs only.** The single LLM step is one schema-constrained call — OpenAI
   **Structured Outputs** (`response_format` = a strict `json_schema`). No free-form agent
   "deciding" figures, no multi-agent loop in v1.
3. **Human-in-the-loop approval, built for an expert.** Before submit, render the **full
   derivation**: each box figure, the source transactions behind it, prior-period deltas, and
   anomaly flags. A human explicitly approves. The gate is in from day one — **even in sandbox.**
4. **Idempotent submit.** Submission is keyed by `(VRN, periodKey)`. Re-running the pipeline
   must never double-file. A repeat submit returns the existing receipt, not a new submission.
5. **Append-only audit trail.** Every node emits an immutable `AuditEvent`: inputs, LLM raw
   output, computed figures, the approver, and the HMRC request/response. JSONL, never edited.
6. **Sandbox only.** No production HMRC base URL anywhere. A guard test asserts the configured
   base URL is the sandbox host. Production recognition is explicitly out of v1 scope.

> If you are about to write code that lets a model output flow into a figure, a submit, or
> bypass the approval gate — **stop and flag it.**

---

## 2. v1 Scope

**In:**
- One route only: **VAT** (the 9-box return). VAT-first is deliberate — the proven plumbing
  (`vat_client`, `fraud_headers`) already exists in `AIAccountant` and is VAT.
- Input: a CSV of transactions (watched folder or CLI arg).
- The full spine above, against the **VAT sandbox**: obligations lookup (find the open period)
  → submit → retrieve.
- A minimal **CLI** is sufficient. (The React dashboard from AgentWorkflows is **out** for v1.)

**Out (do not build in v1):**
- ITSA route, supervisor/multi-agent, clarification loop, production HMRC recognition,
  multi-tenant / user accounts, the dashboard polish, the policy-engine rule UI.
  (These are deliberate v2 enhancements, not v1.)

---

## 3. The interface contract (this is what lets us parallelise)

The two build streams meet at **one typed boundary**, defined in `src/mtd_agent/interfaces.py`:

```python
class HmrcVatClient(Protocol):
    def get_obligations(self, vrn: str, *, from_: date, to: date,
                        status: str | None = None) -> list[Obligation]: ...
    def submit_vat_return(self, vrn: str, payload: VatReturnPayload) -> SubmitReceipt: ...   # idempotent
    def retrieve_vat_return(self, vrn: str, period_key: str) -> VatReturnPayload: ...
```

- **Stream B codes against this Protocol + a `FakeHmrcVatClient`** — it never imports the real
  HMRC code directly.
- **Stream A implements this Protocol** with the real sandbox client.
- The Protocol + the shared domain models in `src/mtd_agent/models.py` are the **only** shared
  surface. Change them **only** in Phase 0, or by an explicit agreed update noted in `LOG.md`
  (bump a `# contract-version: N` comment at the top of `interfaces.py`).

---

## 4. Workstream ownership (who edits what)

| Stream | Owner dir(s) | Mandate |
|--------|--------------|---------|
| **Phase 0 — Foundations** | repo root, `src/mtd_agent/models.py`, `interfaces.py`, `config.py`, `audit.py` | Built **first, by one instance**, before the split. |
| **Stream A — HMRC** | `src/mtd_agent/hmrc/` | Port + harden auth, fraud headers, VAT client; implement the Protocol; live sandbox smoke test. |
| **Stream B — Pipeline** | `src/mtd_agent/graph/`, `src/mtd_agent/nodes/`, `src/mtd_agent/cli.py` | LangGraph spine, the LLM extraction node, pure `compute_vat`, HITL gate, audit wiring. |

**Rules of engagement for multiple instances:**
- **Stay in your directories.** Do not edit the other stream's files. Cross-cutting changes go
  through Phase-0 files only, with a note in `LOG.md`.
- **Branch per stream** (`stream-a-hmrc`, `stream-b-pipeline`). Small commits. Tests green
  before any merge to `main`.
- **Append a line to `LOG.md`** at the end of every working session: what you changed, any
  interface impact, anything you handed off.
- **Never touch production HMRC.** Sandbox base URL only.
- When blocked on something only Will can provide (creds, a VAT rule, a test user), **write the
  ask into `BLOCKERS.md`** and continue on unblocked work.

---

## 5. Definition of Done (v1 acceptance)

`make demo` (or `python -m mtd_agent.cli demo`) runs the full slice against the sandbox with
Will's test user and:

1. Reads a sample transactions CSV → categorises → computes the 9 VAT boxes.
2. Prints the **full derivation** and pauses for explicit human approval.
3. On approval, finds the open obligation period and **submits** to the VAT sandbox; prints the
   HMRC receipt.
4. Writes a complete **append-only audit log** for the run.
5. **Re-running is idempotent** — a second submit for the same `(VRN, periodKey)` returns the
   existing receipt, does not double-file.
6. All **pure-compute unit tests pass**, including a test proving **no LLM output reaches a box
   figure or the submit payload**.
7. A guard test asserts the **base URL is the sandbox**.

---

## 6. What Will provides (the human side of the contract)

- HMRC Developer Hub **sandbox** `client_id` / `client_secret` (into `.env`, never committed).
- One or more **sandbox test users** (VRN + credentials) with an open VAT obligation period.
- A **representative transactions CSV** (or permission to generate a synthetic one).
- Answers on **VAT edge cases** when a box rule is ambiguous (logged as asks in `BLOCKERS.md`).

---

## 7. Tech baseline

- Python 3.12, **LangGraph** for the spine, **pydantic v2** for all domain models, **httpx**
  for HMRC, **pytest** + **ruff**.
- LLM: **OpenAI, Structured Outputs** (`response_format` = strict `json_schema`). Chosen for v1
  to spend existing OpenAI credits. Default extraction model `gpt-4o-mini` (cheap; good for the
  budget); stronger option `gpt-4o`. Model id + provider client via `config.py` / env, **never
  hard-coded in nodes** — keep the LLM call behind a thin `extract` boundary so the provider can
  be swapped (back to Anthropic, etc.) by changing config alone. (Extraction is classification →
  a single call, not an agent.)
- Secrets via `.env` (a `.env.example` is committed; real `.env` is git-ignored).
