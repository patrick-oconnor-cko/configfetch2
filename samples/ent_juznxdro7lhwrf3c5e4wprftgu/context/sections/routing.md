---
section: routing
as_of: 2026-07-29T19:39:54Z
coverage: complete
volatility: high
sources: /entities/{e}/{payment,payout}-routing-rules · /{payment,payout}-routing-rules/{id}
note: `status` is the real field; there is no `enabled` field on routing rules
---

# Routing rules

## Payment routing

### rt_mjztfuwxpmeuxbcntfryfsqdfi — Active
applies to sub-entities: *
restrictions: **none** — matches all traffic
  allow_any_processing_channel: True
  allow_any_merchant_category_code: True
  allow_any_processing_currency: True
  allow_any_event_type: True
  allow_any_card_type: True
  allow_any_region: True
  allow_any_banking_partner: True
  allow_any_payment_method: True
revenue → Currency Account 1 (`ca_xd7v5anhc7kuhgy4qvaasvo3ei`)
fees → Fees (`ca_fpztykcwydwubiebbnkpkaq2bm`)

## Payout routing (covers pay-to-card)

### rt_knavxuhbbswufdoi5mqvuf2plq — Active
applies to sub-entities: *
source: Currency Account 1
revenue → Currency Account 1 (`ca_xd7v5anhc7kuhgy4qvaasvo3ei`)
fees → Fees (`ca_fpztykcwydwubiebbnkpkaq2bm`)
