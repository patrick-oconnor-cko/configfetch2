---
section: channels
as_of: 2026-07-29T19:39:44Z
coverage: complete
volatility: medium
sources: /entities/{e}/processing-channels · /processing-channels/{id} · /sessions-processing-channels/{id}
join: processor.acquirer_id == profile.acquirer_key + scheme + MCC
---

# Processing channels

### PTOCSA — pc_uawoyrryxkgejhfk6wofeusbnm
status active · business model merchant · services vault · pricing "PTOCSA"
features: authorizations=enabled captures=enabled refunds=enabled voids=enabled full_card_api=enabled moto=disabled unreferenced_refunds=disabled
methods: mada
MCCs: 5999
AFT: ❌ no AFT-capable payin profile matches this channel's processors
3DS: ✅ mada 2
pay-to-card capability: ❌ not declared here — pay-to-card is entity-scoped — declared by Active payout processing profiles; processing channels carry no pay-to-card capability → see pay-to-card.md
  (but note: a card payout request still **requires** a `processing_channel_id` — capability is entity-scoped, the payload field is not)

| Processor | Acquirer | Scheme | MCC | → Profile | Match | Auth | Cap | Ref | Void | GWS | Currencies |
|---|---|---|---|---|---|---|---|---|---|---|---|
| PTOCSAMADA | sabb_mpgs_sa | mada | 5999 | pp_3ftjpvejbifuvgu74nfqyuwbye (payin) | exact | same_as_pc | same_as_pc | same_as_pc | same_as_pc | Yes | 1 currencies (missing USD, EUR, GBP, AED, JPY, AUD, CAD, CHF, SEK) |
