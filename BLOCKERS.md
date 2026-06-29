# Blockers — asks only Will can resolve

_Instances: add asks here instead of stalling; work unblocked tasks meanwhile. Will clears these._

## Open (needed to start / finish)
- [ ] **HMRC sandbox `client_id` + `client_secret`** → put in `.env` (never commit). *Code ready; now blocks only the live smoke test + get_token.*
- [ ] **Sandbox test user(s):** VRN + credentials, with an **open VAT obligation period**. *Blocks A4 live smoke test + Phase 3.*
- [x] **Sample transactions CSV** → **synthetic** (Will's call, 2026-06-29). *Stream B generates one.*
- [ ] **Redirect URI** registered on the sandbox app for the OAuth2 flow. *Blocks get_token first-auth.*
- [ ] **`.env` must exist in the Stream-A worktree** (`../mtd-agent-stream-a/.env`). Git worktrees do
  NOT share untracked files, so the creds `.env` in the main tree isn't visible to Stream A.
  Symlink before the live test: `ln -s ../mtd-agent/.env ../mtd-agent-stream-a/.env`. *Blocks A4 live + Phase 3 from the worktree.*

## VAT rule questions (fill as they come up)
- [ ] **Are CSV transaction amounts gross (VAT-inclusive) or net?** Stream B v1 assumes **gross** and strips the rate. If clients export net, compute_vat needs a flag. (Ask mum / the accountant interviews.)
- [ ] **Rounding convention for boxes 6-9** — v1 rounds net totals to the nearest whole pound (ROUND_HALF_UP). HMRC permits rounding *down*. Confirm the accountant's expected convention.
- [ ] **Per-transaction vs per-total VAT rounding** — v1 rounds VAT to the penny per transaction then sums. Confirm this matches practice.
- [ ] **Exempt vs zero-rated in box 6/7** — v1 includes both in the net sales/purchases totals and excludes only outside-scope. Confirm.

## Resolved
- _(move cleared items here with the answer)_
