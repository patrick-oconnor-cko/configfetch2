---
section: settlement
as_of: 2026-07-29T19:39:54Z
coverage: complete
volatility: low
sources: /entities/{e}/currency-accounts · /entities/{e}/payout-settings/{id}
redaction: bank account numbers and bank codes are redacted by policy
---

# Settlement

currencies: AED, EUR, GBP

## Currency accounts

| Currency account | Currency | Status |
|---|---|---|
| `ca_e2dsy22ixb5endsc7lkjepyzcq` | AED | active |
| `ca_kyiqw3tirhte7dqizy6ezh5sv4` | EUR | active |
| `ca_fpztykcwydwubiebbnkpkaq2bm` | GBP | active |
| `ca_xd7v5anhc7kuhgy4qvaasvo3ei` | GBP | active |

## Payout instruction — Payout

instrument: bank_account in GBP · holder PTOC Sandbox INC · bank Branch Bank Name Simulated
redacted: account_number, bank_code
  threshold_amount: 1000000000.0
  cron_schedule: 0 2 * * 1-5
  currency_account_ids: ca_fpztykcwydwubiebbnkpkaq2bm, ca_xd7v5anhc7kuhgy4qvaasvo3ei
  settlement_type: Legacy
  carry_forward_enabled: False
  instruction_state: Active
  balance_minimum: 0.0
  → **cron timezone: unknown.** The schedule object carries no timezone field, so the wall-clock time this fires is not determinable from config.
