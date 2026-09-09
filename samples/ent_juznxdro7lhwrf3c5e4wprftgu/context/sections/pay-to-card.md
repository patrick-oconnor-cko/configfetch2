---
section: pay-to-card
as_of: 2026-07-29T19:39:54Z
coverage: complete
volatility: medium
scope: entity
sources: /entities/{e}/processing-profiles · /processing-profiles/v2/{id}
not_covered: per-FT-type corridors (CAT pay-to-card-schemes endpoint returns 503)
---

# Pay-to-card

**Scope: entity-level.** Declared by processing profiles with
`processing_type=payout` and `status=Active`. Processing channels carry no
pay-to-card capability — never answer this question per-channel.

enabled: **yes**
schemes: mastercard, visa
funds transfer types: C52, FT
MCCs: 6012, 6536
origination: 249 countries (global) · includes US, GB, AE, FR, SA, DE, IN, BR, CN, JP
destination: 249 countries (global) · includes US, GB, AE, FR, SA, DE, IN, BR, CN, JP
forex: enabled

## Payout profiles (the pay-to-card processors)

| Profile | Scheme | FT | BIN | CAIC | MCC | Acceptance | Legal entity | Status |
|---|---|---|---|---|---|---|---|---|
| Visa Payout | visa | FT | 435000 | 538990 | 6012 | e_commerce | cko-ltd-uk | Active |
| Mastercard Payout | mastercard | C52 | 518489 | 538990 | 6536 | e_commerce | cko-ltd-uk | Active |
| Payout | visa | FD | 435000 | 538990 | 4722 | e_commerce | cko-ltd-uk | Suspended |

## Payout (bank) routes — enabled corridors

1 enabled of 51 total

| Country | Currency | Schemes |
|---|---|---|
| GB | GBP | Local/Local |
