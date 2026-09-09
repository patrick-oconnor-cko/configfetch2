---
section: payin-profiles
as_of: 2026-07-29T19:39:54Z
coverage: complete
volatility: medium
sources: /entities/{e}/processing-profiles · /processing-profiles/v2/{id}
---

# Pay-in processing profiles

Acceptance profiles. AFT profiles carry the Business Application Identifier (BAI),
the authorization hold, and SCA exemptions.

| Name | Scheme | Acquirer | BIN | MCC | AFT BAI | Auth hold | Quasi-cash | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| Visa AFT | visa | cko_visa_gb | 402121 | 0742 | FT | 10d | no | e_commerce | Active |
| CB | cartes_bancaires | cko_cb_fr | 51848917208 | 4121 | — | 7d | no | e_commerce | Active |
| Klarna | klarna | klarna_apm_gb | — | 5192 | — | — | no | e_commerce | Active |
| PayPal | paypal | paypal_apm_global | — | — | — | — | no | e_commerce | Active |
| sofort | sofort | sofort_apm_fr | — | 5661 | — | — | no | e_commerce | Active |
| iDEAL | ideal | ideal_apm_fr | — | 5399 | — | — | no | e_commerce | Active |
| Amex Test account | amex | cko_amex_gb | 10000000232 | 5815 | — | 7d | no | e_commerce | Active |

## SCA exemptions

| Profile | TRA | Low value | Secure corp | 3DS outage | Trusted listing | SCA delegation |
|---|---|---|---|---|---|---|
| Visa AFT | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| CB | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
