# Build Log
_Append-only. Newest at top. Every instance adds a line at session end._

---

## [2026-06-29] setup | Repo planned + work contract written (pre-code)
Created the handoff package: `CONTRACT.md` (binding rules + safety principles + interface
contract + workstream ownership), `PLAN.md` (architecture, layout, action list), `CLAUDE.md`
(session bootstrap), `BLOCKERS.md`, this log. **No code yet** — next session is Phase 0
(scaffold + `models.py` + `interfaces.py` + `config.py` + `audit.py`), done by one instance
before the Stream A / Stream B parallel split. Decision: greenfield combining `AgentWorkflows`
(LangGraph spine) + `AIAccountant` (HMRC VAT plumbing); both archived once `make demo` passes.
VAT-first (proven plumbing already exists). Waiting on Will for the items in `BLOCKERS.md`.
