# Architecture — MTD Agent

How the system is built, in agent/LLM-harness terms. Companion to `CONTRACT.md` (binding
rules), `PLAN.md` (v1), and `V2_PLAN.md` (v2 roadmap). Reflects v1 (shipped) + v2 Phase A1/A2.

---

## 1. Thesis: LLM at the edges, deterministic core

This is an **agentic workflow**, not an autonomous agent loop. The design principle is that the
**architecture is the safety case**: the LLM is confined to the *edges* (classification, intake
questions, later routing/review) and can never emit a value that reaches HMRC. All arithmetic is
a **deterministic core** of pure functions. In harness terms:

> **the model proposes labels; the system computes figures.**

Everything below serves that separation.

---

## 2. Layered view

| Layer | Role | Where |
|-------|------|-------|
| **Control plane** (orchestration graph) | Sequences steps, routes, drives HITL | `graph/build.py` (LangGraph `StateGraph`), `graph/pipeline.py` (driver) |
| **Edge / generative** | LLM does constrained classification only | `nodes/extract.py`, `nodes/intake.py` |
| **Deterministic core** | Pure, exhaustively tested arithmetic | `nodes/compute_vat.py`, `models.py` |
| **Effect boundary** | The one irreversible side effect (filing) | `hmrc/` (client, idempotency, sandbox guard) |
| **Cross-cutting** | Audit/observability, evals, guardrails, contracts | `audit.py`, `eval_harness.py`, `CONTRACT.md` |

---

## 3. Control plane — the orchestration graph

The pipeline is a **LangGraph `StateGraph`** compiled once and reused:

```
ingest → extract → intake → completeness ─┬─(incomplete)──────────────► END
                                          └─► compute → resolve_period ─┬─(no period)─► END
                                                                        └─► approval ─┬─(declined)─► END
                                                                                      └─► submit ─► END
```

- **State channels** (`GraphState`, a `TypedDict`) carry only **serializable data** (txns,
  categorised, boxes, receipt, status). Node functions return partial updates that merge into
  state (last-write-wins channels).
- **Dependency injection out-of-band.** Runtime collaborators — the HMRC client, the categoriser,
  the approver, the audit logger — travel in the **run config** (`RunnableConfig.configurable`),
  *not* in state. This keeps state serializable for the checkpointer and keeps non-deterministic
  collaborators out of the persisted trace (a standard "context vs state" split).
- **Conditional edges** encode the guard rails as control flow: incomplete inputs, no open period,
  and a declined approval each route straight to `END` — **nothing reaches the effect boundary on
  those paths.**
- **Pure nodes.** LangGraph orchestrates *control flow only*; the core stays plain functions
  (CONTRACT §8). The graph is a thin wrapper the v1 nodes were deliberately written to accept.

---

## 4. Human-in-the-loop (HITL) & durable execution

Two HITL gates, deliberately implemented with different mechanisms:

- **Intake clarification — durable interrupt.** When the categoriser is unsure, the `intake` node
  calls LangGraph `interrupt()`, which **snapshots state to a checkpointer** (`MemorySaver`, keyed
  by `thread_id = run_id`) and pauses. The driver (`run_pipeline`) reads the interrupt payload,
  asks the injected **`Questioner`** for answers, and **resumes** with `Command(resume=…)`. This is
  the server-ready pattern: the pause is *durable* and could survive a process boundary.
  - **Harness gotcha encoded:** LangGraph **ignores a falsy `resume` value**, so an empty
    "keep-all" answer would re-interrupt forever. The resume payload is wrapped
    (`{"answers": …}`) to stay truthy, with a loop safety cap.
- **Approval gate — inline callback.** The final sign-off is a single fixed decision, so it is a
  synchronous **`Approver`** callback inside the node (renders the full derivation, waits for y/N).
  Migrating it to a durable `interrupt()` too is a planned refactor when the system grows a server.

Both gates have **test doubles** (`AutoQuestioner`, `AutoApprover`) so the whole HITL flow runs
unattended in CI.

---

## 5. The generative edge — constrained classification

- **Single LLM call, schema-constrained.** `extract.py` uses **OpenAI Structured Outputs** with a
  `strict` JSON schema. The schema is the safety boundary: the model returns `TxnCategory`
  `{id, treatment, category, confidence, reasoning}` — **no monetary field exists**, so a model can
  never produce a figure. Labels are joined back to transactions **by id**.
- **Provider abstraction.** A `Categoriser` **Protocol** with swappable backends
  (`OpenAICategoriser`, offline `FakeCategoriser`). Model id + provider come from config — a
  provider swap (e.g. back to Anthropic) is configuration, not a code change.
- **Intake is also an edge agent**, but its output is *questions*, resolved by a human — again,
  never a figure (`nodes/intake.py`).

---

## 6. Deterministic core

- `compute_vat(categorised) -> VatBoxes` is **pure** — no LLM, no I/O, no clock. Every figure HMRC
  sees originates here.
- **Types enforce the invariants.** `VatBoxes` validates `box3 = box1+box2` and `box5 = |box3−box4|`
  at construction, so a compute bug fails fast *before* the human or HMRC sees it.
- **The safety property is tested two ways** (`test_no_llm_figures.py`): structurally (the model's
  output type has no money field) and behaviourally (a *malicious* categoriser's free text produces
  byte-identical boxes).

---

## 7. Effect boundary — the one irreversible action

- **Contract-first integration.** `hmrc/interfaces.py` defines the `HmrcVatClient` **Protocol**
  (`contract-version: 1`); the pipeline depends only on it. `FakeHmrcVatClient` is a **test double
  that encodes the real behavioural contract**, so the whole pipeline runs offline and the real
  client is a drop-in.
- **Idempotent effect.** `submit` is keyed by `(VRN, periodKey)` via a **persisted idempotency
  ledger** — a re-run returns the stored receipt and never double-files. Idempotency is
  **client-side and authoritative** (it does not rely on HMRC's obligation state).
- **Sandbox guard.** `config.assert_sandbox()` is a chokepoint that makes production physically
  unreachable by misconfiguration.
- **Typed errors** (`user_fixable` vs `system`) so the harness can surface "you can fix this"
  vs "retry/escalate."

---

## 8. Cross-cutting

- **Audit trail / observability.** `audit.py` writes an **append-only JSONL trace**, one event per
  node (inputs, model labels, computed figures, the approval, the HMRC response). A run is fully
  **reconstructable** — this is the artefact an accountant/HMRC relies on and the substrate the v2
  reviewer agent reads.
- **Evals.** `eval_harness.py` + `evals/cases/` is an offline **golden-set eval**: a
  **deterministic-core regression gate** (compute vs hand-computed expected boxes) plus
  **categorisation accuracy** (offline Fake 90% / OpenAI 100%). LLM-as-judge evals for the v2
  agents are planned.
- **Guardrails (v2 A4, planned).** Input/output guardrails: PII + prompt-injection scanning of
  transaction descriptions and skill content, treating untrusted text as *data, not instructions*.
- **Safety invariants (CONTRACT §1 + §8):** deterministic core; one schema-constrained LLM call;
  HITL before every submit; idempotency; append-only audit; sandbox-only; and — for agents — no
  agent computes a figure, bypasses the gate, or (for the reviewer) writes.

---

## 9. Terminology map (how this maps to standard agent-harness practice)

| Concept | Here |
|---------|------|
| Orchestration graph / control plane | LangGraph `StateGraph` |
| Durable execution / checkpointing | `MemorySaver`, `interrupt()`/`Command(resume)`, `thread_id` |
| Context vs state | deps in `RunnableConfig`; data in `GraphState` |
| Constrained generation / structured output | OpenAI Structured Outputs, `strict` schema, no money field |
| Tool/provider abstraction | `Categoriser` / `HmrcVatClient` Protocols |
| Effect management / idempotency | `(VRN, periodKey)` ledger, sandbox guard |
| HITL | intake (durable interrupt) + approval (inline callback) |
| Observability / tracing | append-only JSONL audit |
| Evaluation | golden-set eval harness (regression + accuracy) |
| Contract-first / test double | `HmrcVatClient` Protocol + `FakeHmrcVatClient` |

---

## 10. Status

- **v1:** shipped — files to the HMRC VAT sandbox with expert HITL, idempotency, audit; verified
  live (real + idempotent).
- **v2 Phase A:** A1 (LangGraph backbone) + A2 (intake HITL agent) done, on branch `v2-phase-a`,
  49 tests green. **Remaining:** A3 (audit the Q&A + intake eval), A4 (input guardrails), then merge.
- **Next:** Phase B — supervisor/router + VAT-scheme workflows (see `V2_PLAN.md`).
