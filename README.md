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

## Start here
- **`CONTRACT.md`** — the rules (read first).
- **`PLAN.md`** — architecture + action list.
- **`CLAUDE.md`** — session bootstrap for Claude Code.
- **`BLOCKERS.md`** — what Will needs to provide.

Part of the [tax/MTD startup](../Personal/startup/ideas/tax-mtd-agent.md) thread.
