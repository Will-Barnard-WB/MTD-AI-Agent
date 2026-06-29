# Blockers — asks only Will can resolve

_Instances: add asks here instead of stalling; work unblocked tasks meanwhile. Will clears these._

## Open (needed to start / finish)
- [ ] **HMRC sandbox `client_id` + `client_secret`** → put in `.env` (never commit). *Blocks A1.*
- [ ] **Sandbox test user(s):** VRN + credentials, with an **open VAT obligation period**. *Blocks A4 live smoke test + Phase 3.*
- [ ] **Sample transactions CSV** (or "generate a synthetic one" — say which). *Blocks B1/B4 fixtures.*
- [ ] **Redirect URI** registered on the sandbox app for the OAuth2 flow. *Blocks A1.*

## VAT rule questions (fill as they come up)
- [ ] **Are CSV transaction amounts gross (VAT-inclusive) or net?** Stream B v1 assumes **gross** and strips the rate. If clients export net, compute_vat needs a flag. (Ask mum / the accountant interviews.)
- [ ] **Rounding convention for boxes 6-9** — v1 rounds net totals to the nearest whole pound (ROUND_HALF_UP). HMRC permits rounding *down*. Confirm the accountant's expected convention.
- [ ] **Per-transaction vs per-total VAT rounding** — v1 rounds VAT to the penny per transaction then sums. Confirm this matches practice.
- [ ] **Exempt vs zero-rated in box 6/7** — v1 includes both in the net sales/purchases totals and excludes only outside-scope. Confirm.

## Resolved
- _(move cleared items here with the answer)_
