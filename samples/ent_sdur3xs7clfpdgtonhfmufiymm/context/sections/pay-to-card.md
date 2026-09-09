---
section: pay-to-card
as_of: 2026-07-29T19:39:44Z
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

enabled: **no** — no Active payout processing profiles exist for this entity
forex: not configured

## Payout profiles (the pay-to-card processors)

_none_
