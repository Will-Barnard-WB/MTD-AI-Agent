# V2 Plan — MTD Agent (conversational front-end + advisory brain)

Companion to `CONTRACT.md` (v1 binding rules) and `PLAN.md` (v1 architecture). v1 is complete:
the deterministic VAT slice files to the HMRC sandbox with expert HITL, idempotency, and audit.
v2 adds **agency at the edges** — intake, routing, and review — without weakening the safety case.

---

## 0. Governing principle (unchanged from v1, extended)

The architecture *is* the safety case: **the LLM must not emit a figure that reaches HMRC.**
Every v2 agent sits at an **edge** and obeys three rules:

1. Agents may **gather, route, question, and comment** — never compute a box figure, mutate
   pipeline state, or make the submit decision.
2. The **deterministic core (`compute_vat`) + expert HITL approval gate stay authoritative.**
   No agent can bypass the gate.
3. The **audit reviewer is advisory and read-only** — it annotates, it never blocks or changes.

If we hold this line, we add a lot of agency without spending the safety case.

---

## 1. Locked decisions (this session)

- **Router first target:** VAT **scheme** routing — standard vs flat-rate vs cash accounting
  (valuable now, reuses existing VAT plumbing). A second tax type (ITSA / Self-Assessment) is
  **deferred** to a later phase.
- **Skills KB:** curated **skill files** (versioned markdown) only for now — **no RAG yet.**
- **Audit reviewer timing:** **real-time first** (comments in the approval view), **batch second**
  (same engine, a `review` command). Not either/or — a sequence.
- **Orchestration:** adopt **LangGraph** in v2 (`StateGraph` + `interrupt()`). It orchestrates
  control flow only; the pure deterministic core stays plain functions.
- **Router asks when unsure:** the supervisor gets an `ask_user` tool (HITL interrupt) — intake
  and routing are one conversational front-end, not two agents.
- **Build:** single instance (no parallel two-stream setup).

---

## 2. The three agents

### 2.1 Supervisor (Intake + Routing) — Phase A/B
One conversational front-end that runs **before** the workflow. It:
- Talks to the user, **classifies the workflow** (Phase B: VAT scheme), and **gathers/validates
  inputs**, replacing today's silent `completeness` node with an interactive loop.
- Uses an **`ask_user` tool** (LangGraph `interrupt()`) to ask targeted questions when routing is
  ambiguous or data is missing/low-confidence — asks instead of guessing.
- Emits a structured **`IntakeResult`** (confirmed transactions + resolved ambiguities + chosen
  route + unanswered flags) that feeds `ingest`/`extract`.
- **Boundary:** produces inputs, clarifications, and a route — never figures. All questions +
  answers are audited.

### 2.2 VAT scheme routing (the thing the supervisor routes to) — Phase B
Each scheme is a **deterministic subgraph** with its own pure compute + HITL gate:
- **Standard** (v1's `compute_vat`).
- **Flat-rate** — turnover × flat-rate %; different box logic. New pure `compute_vat_flat_rate`.
- **Cash accounting** — VAT on payments received/made, not invoice date. New pure computation.
The router picks the path; the path's compute is still pure and gated. Router can't skip the gate.

### 2.3 Audit Reviewer — Phase C
A **read-only** agent with (a) audit-log read access and (b) the HMRC skills KB. Produces
**grounded, cited** comments on a trace. Two triggers, same engine:
- **Real-time:** comments render inside the approval view (advisory, pre-submit).
- **Batch:** a `review` command sweeps historical audit logs → anomaly/pattern report.
**Non-negotiables:** read-only tools (no state mutation, no submit); **every comment cites a skill
file** — no ungrounded assertions; it is a second opinion for the expert, never an authority.

---

## 3. HMRC skills knowledge system (skill files, versioned)

- **Format:** curated markdown **skill files** under `skills/hmrc/<tax-year>/…` (e.g.
  `vat-scope.md`, `vat-rates.md`, `flat-rate-scheme.md`), each rule with a stable anchor id so
  comments can cite `[skill: vat-rates#reduced]`.
- **Versioned by tax year** — a 2026/27 return is reviewed against 2026/27 rules (correctness, not
  polish). The tax year is part of intake/state.
- **Provenance-first** — retrieval returns the citation; reviewer comments must carry it.
- **Reference, never a figure source** — informs labels + comments, never arithmetic.
- **RAG over the full legislation corpus is deferred** — revisit once skill files prove the shape.

---

## 4. Agent-harness infrastructure (the "what else")

1. **LangGraph orchestration** — `StateGraph` for the supervisor + workflow subgraphs; `interrupt()`
   for every HITL point (intake questions + approval gate). Core compute stays pure.
2. **Typed, permissioned tools** — narrow per-agent surfaces; reviewer is **read-only by
   construction** (can't write state or submit). Enforced, not conventional.
3. **Guardrails** — new risk surface is **prompt injection via transaction descriptions and skill
   files**. Input guardrails (PII, injection); output guardrails (router can't bypass the gate;
   reviewer can't emit a figure-change instruction). Core already protects figures; guardrails
   protect *decisions*.
4. **Agent evals** (extend the v1 eval harness) — golden sets + LLM-as-judge for **routing
   accuracy**, **intake completeness** (caught the missing thing?), **reviewer quality** (true
   issues vs false positives). Added agency must not silently regress safety.
5. **Observability + richer audit** — trace multi-agent flows; extend the audit log to record each
   agent's reasoning **and citations**, so a run stays fully reconstructable.
6. **State & memory** — conversation state for intake; per-client memory (prior periods, recurring
   vendors → better categorisation + anomaly deltas).
7. **Model routing / cost** — cheap model for categorise/route, stronger for review; cache skills.

---

## 5. Safety addendum (promote into CONTRACT.md when Phase A starts)

New binding rules for agents (extend CONTRACT §1):
- **A1. No agent computes a figure.** Agents output labels, routes, questions, comments — never a
  box value or a submit payload. (Extends v1 §1.1.)
- **A2. No agent bypasses the HITL gate.** The supervisor may choose a path; the path always ends
  at the expert approval gate before submit.
- **A3. The reviewer is read-only and advisory.** Its tools cannot mutate state or submit; it never
  blocks — the human decides. Every comment cites a skill file.
- **A4. Untrusted text is data, not instructions.** Transaction descriptions and skill-file content
  are treated as data; input/output guardrails defend routing/gathering/review decisions.
- **A5. Tax-year-correct rules.** Reviewer + categoriser consult the skill set for the return's tax
  year.
- **A6. Everything an agent does is audited** — reasoning + citations into the append-only log.

---

## 6. Phased action list (cheap → expensive, validate as we go)

### Phase A — Supervisor (intake/gathering) + LangGraph backbone
- [ ] A1 Introduce LangGraph `StateGraph`; wrap the existing pure nodes (no core changes).
- [ ] A2 `ask_user` tool via `interrupt()`; interactive completeness loop → `IntakeResult`.
- [x] A3 Audit every question/answer; intake eval set (completeness detection).
- [x] A4 Guardrails v1: PII + injection input scan on transaction descriptions.

### Phase B — Supervisor routing + VAT schemes
- [ ] B1 Supervisor classifies scheme (standard/flat-rate/cash); route to subgraph.
- [ ] B2 Pure `compute_vat_flat_rate` + `compute_vat_cash` (fully unit-tested, like v1 core).
- [ ] B3 Routing eval set (accuracy + "asks when unsure").

### Phase C — Skills KB + audit reviewer
- [ ] C1 `skills/hmrc/<year>/*.md` with anchored rules (VAT scope, rates, schemes).
- [ ] C2 Reviewer (read-only) → real-time cited comments in the approval view.
- [ ] C3 `review` batch command over historical audit logs.
- [ ] C4 Reviewer eval set (true issues vs false positives).

### Cross-cutting (from the start)
- [ ] Promote §5 addendum into `CONTRACT.md`; bump interface contract-version if the boundary moves.
- [ ] Extend evals + observability alongside each phase — never bolt on later.

### Deferred (explicit non-goals for now)
- ITSA / Self-Assessment as a second tax type; RAG over full legislation; multi-tenant/accounts;
  production HMRC recognition.

---

## 7. Founder note
v2 features should be pulled by **what accountants (Will's mum / design partners) actually ask
for**. The **intake agent** ("it chases missing info") and the **reviewer** ("it sanity-checks
against the rules") are the two most likely real selling points — good things to put in front of a
design partner early, before over-building.
