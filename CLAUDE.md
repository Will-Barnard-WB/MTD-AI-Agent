# MTD Agent — Claude Code session bootstrap

You are working on **MTD Agent v1**: an AI agent that does VAT bookkeeping + prepares + files a
VAT return end-to-end via the HMRC Making Tax Digital sandbox. Deterministic core, expert
human-in-the-loop approval, idempotent submit, full audit trail.

## Read these first, every session
1. **`CONTRACT.md`** — the binding rules. Non-negotiable safety principles + workstream
   ownership + the interface contract. Do not deviate silently.
2. **`PLAN.md`** — architecture, directory layout, and the action list.
3. **`LOG.md`** — what previous sessions changed (newest at top).
4. **`BLOCKERS.md`** — open asks for Will. Don't re-ask what's already there.

## The five rules you will most easily break
1. **The LLM never produces a figure that reaches HMRC.** Model categorises; pure Python computes.
2. **One LLM call only** (structured-output extraction). No agent loop in v1.
3. **Approval gate before every submit** — even in sandbox.
4. **Idempotent submit** keyed on `(VRN, periodKey)`. Never double-file.
5. **Sandbox base URL only.** Never production HMRC.

## Working discipline
- Stay inside your **assigned workstream's directories** (see `CONTRACT.md §4`).
- Branch per stream; small commits; tests green before merge.
- Code Stream B against the `HmrcVatClient` Protocol + `FakeHmrcVatClient`, never the real client.
- Append a session note to `LOG.md` before you stop. New asks for Will → `BLOCKERS.md`.

## Definition of done
See `CONTRACT.md §5`. In short: `make demo` runs the full slice against the sandbox, with a
real approval gate, an idempotent submit, a complete audit log, and a passing safety test that
proves no model output became a box figure.
