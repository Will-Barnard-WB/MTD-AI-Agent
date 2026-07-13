# MTD Agent

An AI agent that does VAT bookkeeping, prepares the return, and **files it end-to-end** via the
official HMRC Making Tax Digital (MTD) API. Built for accountants: the model does the grunt work,
an expert reviews a full derivation, and only then does it submit.

**v1 is a vertical slice to the HMRC VAT sandbox:**

```
CSV → categorise (LLM) → compute VAT boxes (pure) → expert approves → idempotent submit → audit
```

Safety is the architecture: the **LLM never produces a figure that reaches HMRC** (it only
categorises; all arithmetic is pure Python), there's a **human approval gate** before every
submit, submits are **idempotent**, and every step is **audited**. Sandbox only in v1.

## Observability (LangSmith)

Every run is traceable in [LangSmith](https://smith.langchain.com) — the graph nodes
(`supervisor → ingest → guardrails → extract → intake → compute → approval → submit`),
the HITL interrupts, and the LLM categoriser call (prompt, response, tokens) as a nested
span. It's **opt-in** and off by default.

```bash
# 1. Create an API key: smith.langchain.com → Settings → API Keys
# 2. In .env:
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=ls-...
LANGSMITH_PROJECT=mtd-agent      # auto-creates on first trace — no UI setup needed
# 3. Run as normal; traces appear under the project:
python -m mtd_agent.cli demo --real-llm
```

Wiring lives in `config.configure_tracing()` (env activation) + `wrap_openai` on the
categoriser (`nodes/extract.py`); LangGraph auto-traces the nodes. Note: enabling this
sends run data (including transaction descriptions) to LangChain's cloud — v1 uses HMRC
**sandbox** / example data only.

## Start here
- **`CONTRACT.md`** — the rules (read first).
- **`PLAN.md`** — architecture + action list.
- **`CLAUDE.md`** — session bootstrap for Claude Code.
- **`BLOCKERS.md`** — what Will needs to provide.

Part of the [tax/MTD startup](../Personal/startup/ideas/tax-mtd-agent.md) thread.
