# Dashboard Plan — MTD Agent Console (a self-hosted, LangSmith-style observability + ops console)

A local, **project-tailored** console for the MTD agent — think *"LangSmith, but built for this
one project and running on your own machine."* It borrows LangSmith's information architecture
(a **Runs/trace explorer**, **Datasets**, **Experiments/evals**, a **Playground**, and
**Monitoring**) but every view is specialised to *this* domain: the VAT pipeline, the append-only
audit trail, guardrail findings, intake Q&A, the approval gate, and HMRC submits. You can see and
run the tests + evals, drill into any run's trace, trigger runs (with the HITL gates in the UI),
and check project health — all without shipping a single transaction to a third-party SaaS.

Companion to `PLAN.md` (v1), `V2_PLAN.md` (v2 agents), and `CONTRACT.md` (safety rules). Scheduled
**after the v2 roadmap sessions** (intake calibration → reviewer → flat-rate → hardening) unless
pulled earlier.

> **Why bespoke, not the LangSmith SaaS?** LangSmith is the model to *imitate*, not integrate.
> Self-hosting it keeps transaction data on the machine (LangSmith tracing would send node
> inputs/outputs — incl. pre-redaction descriptions — to a third party, at odds with our safety/
> privacy story), and lets every view speak our domain language (VAT boxes, treatments, obligations,
> guardrail kinds) instead of generic LLM spans. We already emit a rich append-only trail
> (`audit/*.jsonl`) — the console is the LangSmith-style *lens* over it.

---

## 0. Governing principles (the dashboard must not weaken the safety case)

The console is an *operator surface*, not an authority. It obeys the same rules as every agent:

1. **It never bypasses the HITL gate.** Approval + intake clarifications are surfaced *in the UI*
   and resumed through LangGraph `interrupt()` — the dashboard cannot auto-approve or emit a figure.
2. **Audit views are read-only.** The console renders `audit/*.jsonl`; it never edits or deletes them.
3. **Sandbox-only, loudly.** `--live` runs stay behind `config.assert_sandbox`; the UI shows a
   permanent **SANDBOX** badge and requires an explicit confirm before any live submit.
4. **Localhost only.** It can spend OpenAI credits and file to the HMRC sandbox, so it binds to
   `127.0.0.1` and is never exposed publicly. No auth layer needed while local; documented clearly.
5. **Reuse, don't reimplement.** The console is a thin shell over existing code — `run_pipeline`,
   `AuditLogger`, `guardrails.scan_description`, `eval_harness`, `intake_eval`. No business logic
   in the UI.
6. **Self-hosted, no data egress.** Everything runs and stays local. No transaction data leaves the
   machine — a deliberate contrast with cloud tracing, and part of the pitch to accountants.

---

## 1. Tech decision (one open choice)

**Recommended: Streamlit.** Pure Python, matches Will's stack (SQL/backend, already a Streamlit
user), and an admin dashboard is exactly its sweet spot — fast to build, easy to iterate. Lives in
the same repo/venv, imports the package directly.

**Alternative: FastAPI + a small React/React-Flow front-end** (the old `AgentWorkflows` prototype
did this). Better if the goal shifts to a *demo* surface for design partners — a live animated graph
of the pipeline. More work; deferrable. Recommendation: build the **admin** console in Streamlit
now; revisit a React demo view later if a design-partner demo needs the graph animation.

> Decision needed before Dashboard S1: **Streamlit (admin) vs FastAPI+React (demo)**. Plan below
> assumes Streamlit.

Location: `dashboard/` in the repo; run with `streamlit run dashboard/app.py`. Add `streamlit` to
`pyproject.toml` `[dev]` extras.

---

## 1b. LangSmith as the blueprint — its IA, mapped to our domain

We steal LangSmith's structure and specialise each part. This is the north star for the panels:

| LangSmith concept        | Our tailored version                                                        |
|--------------------------|-----------------------------------------------------------------------------|
| **Projects / Runs list** | The run history — every pipeline run from `audit/`, with status (submitted/declined/incomplete), scheme, VRN, period, £ net VAT, duration, cost. Sortable/filterable. |
| **Trace view** (span tree)| A run's node timeline — `ingest → guardrails → extract → intake → … → submit` — each step expandable with its inputs/outputs, timing, and (for `extract`) tokens/cost. Rendered from the audit trail, VAT-aware (shows boxes, treatments, guardrail kinds, the intake Q&A, the approval derivation). |
| **Datasets**             | The labelled eval cases we already have — `evals/cases/*` (compute + categorisation) and `evals/intake/cases.json`. Browsable/editable in-UI; add a case from a real run. |
| **Experiments** (eval runs over a dataset, tracked over time) | Run `eval_harness` / `intake_eval` (and later routing + reviewer evals) and **store each result** so you can chart accuracy/precision/recall trends across commits — not just a one-off print. |
| **Playground**           | The **guardrail playground** (paste text → live redaction/flagging) and a categoriser playground (one description → treatment + confidence). |
| **Monitoring / dashboards** | The health page: pass/fail, latest accuracy, cost, HMRC auth + sandbox status, error rates over recent runs. |

**Enabling change — richer per-run telemetry (small, do early).** To get a real LangSmith-style
trace we want per-node **duration** and, for the one LLM call, **token usage + estimated cost**.
Today `AuditLogger.emit(step, payload)` records step + payload but no timing/cost. Add: (a) a
`ts`-delta or explicit `duration_ms` per event (cheap — wrap node execution), and (b) capture the
OpenAI response `usage` in the `extract` event. This is exactly `V2_PLAN §4.5` ("Observability +
richer audit") and it's what turns the audit log from a compliance record into a *traceable* one.
Keep it additive — the append-only compliance semantics don't change.

> Note: the old `AgentWorkflows` prototype already wired the real LangSmith SaaS + LLM-as-judge
> evaluators — useful **prior art for eval design** to port conceptually, but here we render our own
> local views instead of sending traces out.

---

## 2. Integration map (what each feature reuses)

| Dashboard feature        | Reuses (existing code)                                             |
|--------------------------|-------------------------------------------------------------------|
| Audit log viewer         | `AuditLogger.read_all()`, `audit/*.jsonl`, `scripts/show_audit.py` logic |
| Test / eval runner       | `subprocess` → `pytest`, `ruff`, `mtd_agent.eval_harness`, `mtd_agent.intake_eval` |
| Trigger a run            | `graph.build.PIPELINE_GRAPH` + checkpointer (driven directly, see §3) |
| Intake clarification     | `nodes.intake.detect_gaps` / `Gap` / `apply_answers` (via interrupt payload) |
| Approval gate            | `nodes.approval.build_derivation` (via interrupt payload — see §3 refactor) |
| Guardrail playground     | `guardrails.scan_description`                                      |
| Health / config          | `config.Settings.load()`, HMRC token status, OpenAI key presence  |

---

## 3. Prerequisite refactor — approval as an `interrupt()`

Today `intake` pauses via `interrupt()` (checkpointer-backed, resumable), but **approval is a
blocking callback** (`_approval` calls `approver.approve()` synchronously inside the node). A web UI
can't block on a terminal `input()`, so before Dashboard S3 we convert the approval gate to a
LangGraph `interrupt()` too — emitting the derivation as the interrupt payload and resuming with the
human's approve/decline. This is already called for in `V2_PLAN §4.1` ("`interrupt()` for every HITL
point"). Benefits: one uniform HITL mechanism, and the CLI (`CLIApprover`) + web both drive the same
resumable graph. Small, well-tested change; do it as step 1 of Dashboard S3.

The dashboard then drives `PIPELINE_GRAPH` directly (like `pipeline.py`'s loop, but across UI
interactions): `invoke` → if `__interrupt__`, render the gap/derivation panel → on submit,
`invoke(Command(resume=...))` with the same `thread_id`. State persists in the checkpointer between
Streamlit reruns.

---

## 4. Feature panels (each is a specialised version of a LangSmith view — see §1b)

1. **Runs list** *(≈ LangSmith Runs)* — every run from `audit/`: status, scheme, VRN, period, £ net
   VAT, duration, cost. Sort/filter/search; click through to the trace.
2. **Trace view** *(≈ LangSmith trace)* — one run's node timeline (`ingest → guardrails → … →
   submit`), each step expandable with inputs/outputs, timing, and (for `extract`) tokens/cost.
   VAT-aware rendering: boxes, treatments, guardrail kinds, the intake Q&A, the approval derivation.
   Colour-coded by type; download as JSON. *Read-only.*
3. **Test & experiments runner** *(≈ LangSmith Datasets + Experiments)* — buttons: full `pytest`,
   per-file tests, `ruff`, `eval_harness` (fake/real), `intake_eval`. Streams stdout; shows pass/fail
   + the accuracy table; **stores each eval result so trends chart over time**. Browse the datasets
   (`evals/…`); add a case from a real run.
4. **Trigger a run** — form: choose/upload a CSV (defaults to `examples/`), categoriser (fake/real),
   HMRC client (fake/**live** w/ confirm), draft toggle. Handles the **intake clarification** form
   and **approval** derivation in-UI (§3). Ends with the result + a jump to its trace.
5. **Playground** *(≈ LangSmith Playground)* — guardrail playground (paste text → live
   `scan_description` redaction/flagging) + categoriser playground (one description → treatment +
   confidence). Ties directly to the A4 safety feature; great for demos.
6. **Monitoring / health** *(≈ LangSmith dashboards)* — pass/fail snapshot, latest accuracy, cost,
   HMRC auth + sandbox status, error rate over recent runs, config summary + permanent SANDBOX badge.
7. **Command catalog** — a rendered, copy-pasteable reference of all the CLI commands (the set we
   walked through), so the console doubles as living docs.

---

## 5. Phased build (sessions, cheap/safe → richer)

### Dashboard S1 — Skeleton + Runs list + Trace view (read-only, zero risk)
First: the **richer-telemetry** enabling change (§1b — per-node `duration_ms` + `extract` token/cost
in the audit events; additive, keeps append-only semantics). Then the Streamlit scaffold + the
Runs list (panel 1) and Trace view (panel 2). The safest, most immediately useful slice — you can
inspect every run as a proper LangSmith-style trace.

### Dashboard S2 — Test & experiments runner + Playground + Command catalog
Panels 3, 5, 7. All read-only or subprocess — no pipeline mutation, no HITL. Adds the experiment
store so eval accuracy/precision/recall trend over time. Turns the console into "run everything from
earlier, in a UI, and track it."

### Dashboard S3 — Trigger runs with in-UI HITL
Step 1: the approval-as-`interrupt()` refactor (§3). Then panel 4: the run form + intake + approval
in the browser, offline (fake/fake) first, then enable `--real-llm` and `--live` (sandbox, gated).
This is the meaty session.

### Dashboard S4 — Monitoring/health + polish
Panel 6, filters/search, auto-refresh, a tidy landing page. Optional: SQLite index over `audit/` for
fast run history + trend queries.

### Deferred / optional
- FastAPI + React-Flow **live animated graph** demo view (for design partners) — the richer trace UI
  if Streamlit's ceiling is hit.
- Per-client history, multi-run comparison, anomaly trends (pairs with the Phase C reviewer's batch
  `review` output).

---

## 6. Risks & decisions
- **Decided:** LangSmith is the *blueprint*, not a dependency — self-hosted, bespoke, no data egress
  (§1b / principle 6).
- **Open decision:** Streamlit (fast, Python, admin-grade) vs FastAPI+React (richer trace UI, demo-
  grade) — see §1. Pick before S1; plan assumes Streamlit.
- **HITL across Streamlit reruns** — the main technical risk; the checkpointer + `thread_id` pattern
  in §3 handles it, but prototype it early in S3.
- **Telemetry change is additive** — adding `duration_ms`/token-cost to audit events must not break
  the append-only compliance record or existing tests; new fields only.
- **Live runs from a UI** — gated, confirmed, sandbox-only, localhost-only. Never auto-approve.
- **Long-running LLM/live calls** — show spinners/streaming; keep the UI responsive; consider running
  the pipeline in a thread with status polling if Streamlit blocking becomes annoying.
