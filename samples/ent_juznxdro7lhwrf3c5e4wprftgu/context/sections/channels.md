---
section: channels
as_of: 2026-07-29T19:39:54Z
coverage: complete
volatility: medium
sources: /entities/{e}/processing-channels · /processing-channels/{id} · /sessions-processing-channels/{id}
join: processor.acquirer_id == profile.acquirer_key + scheme + MCC
---

# Processing channels

### Channel 1 — pc_ciui77f3mfvephdkq7oh6ppxku
status active · business model merchant · services prism, vault · pricing "Default Pricing"
features: authorizations=enabled captures=enabled refunds=enabled voids=enabled full_card_api=enabled moto=disabled unreferenced_refunds=disabled
methods: amex, cartes_bancaires, ideal, klarna, mastercard, paypal, sofort, visa
MCCs: 0742, 4121, 5192, 5399, 5661, 5815
AFT: ✅ via Visa AFT (`pp_etao3gtqj4ielk747rttb2uti4`) · BAI=FT · auth hold 10d · match exact
3DS: ✅ visa 2/1.0.2 · mastercard 1.0.2/2 · amex 2/1.0.2 · visa 2
pay-to-card capability: ❌ not declared here — pay-to-card is entity-scoped — declared by Active payout processing profiles; processing channels carry no pay-to-card capability → see pay-to-card.md
  (but note: a card payout request still **requires** a `processing_channel_id` — capability is entity-scoped, the payload field is not)

| Processor | Acquirer | Scheme | MCC | → Profile | Match | Auth | Cap | Ref | Void | GWS | Currencies |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Visa Processor 1 | Checkout VISA | visa | 5192 | — | — | same_as_pc | same_as_pc | same_as_pc | same_as_pc | No | 157 currencies (all majors) |
| MC Processor 1 | Checkout Mastercard | mastercard | 5815 | — | — | same_as_pc | same_as_pc | same_as_pc | same_as_pc | No | 157 currencies (all majors) |
| Amex 5815 | cko_amex_gb | amex | 5815 | Amex Test account (payin) | exact | same_as_pc | same_as_pc | same_as_pc | same_as_pc | No | 146 currencies (all majors) |
| iDEAL | ideal_apm_fr | ideal | 5399 | iDEAL (payin) | exact | N/A | N/A | N/A | N/A | N/A | 1 currencies (missing USD, GBP, AED, SAR, JPY, AUD, CAD, CHF, SEK) |
| sofort | sofort_apm_fr | sofort | 5661 | sofort (payin) | exact | N/A | N/A | N/A | N/A | N/A | 1 currencies (missing USD, GBP, AED, SAR, JPY, AUD, CAD, CHF, SEK) |
| PayPal | paypal_apm_global | paypal | — | PayPal (payin) | acquirer+scheme | N/A | N/A | N/A | N/A | N/A | 20 currencies (missing AED, SAR, CAD) |
| Visa AFT | cko_visa_gb | visa | 0742 | Visa AFT (payin) | exact | same_as_pc | same_as_pc | same_as_pc | same_as_pc | No | 147 currencies (all majors) |
| Klarna | klarna_apm_gb | klarna | 5192 | Klarna (payin) | exact | N/A | N/A | N/A | N/A | N/A | 9 currencies (missing USD, AED, SAR, JPY, AUD, CAD) |
| CB | cko_cb_fr | cartes_bancaires | 4121 | CB (payin) | exact | same_as_pc | same_as_pc | same_as_pc | same_as_pc | No | 1 currencies (missing USD, GBP, AED, SAR, JPY, AUD, CAD, CHF, SEK) |

### PTOC SBOX Payout — pc_eslelmxntabejezzb5wfcom3uu
status active · business model merchant · services pay_to_bank, vault · pricing "Default Pricing"
features: authorizations=enabled captures=enabled refunds=enabled voids=enabled full_card_api=enabled moto=disabled unreferenced_refunds=disabled
AFT: ❌ no AFT-capable payin profile matches this channel's processors
3DS: ❌ no sessions processing channel exists for this channel — 3DS not configured
pay-to-card capability: ❌ not declared here — pay-to-card is entity-scoped — declared by Active payout processing profiles; processing channels carry no pay-to-card capability → see pay-to-card.md
  (but note: a card payout request still **requires** a `processing_channel_id` — capability is entity-scoped, the payload field is not)

_none_

### South Africa Test — pc_v5dvjmf2sxnujpxkatxyritluu
status active · business model merchant · services vault · pricing "Default Pricing"
features: authorizations=enabled captures=enabled refunds=enabled voids=enabled full_card_api=enabled moto=disabled unreferenced_refunds=disabled
AFT: ❌ no AFT-capable payin profile matches this channel's processors
3DS: ❌ no sessions processing channel exists for this channel — 3DS not configured
pay-to-card capability: ❌ not declared here — pay-to-card is entity-scoped — declared by Active payout processing profiles; processing channels carry no pay-to-card capability → see pay-to-card.md
  (but note: a card payout request still **requires** a `processing_channel_id` — capability is entity-scoped, the payload field is not)

_none_

### Profile PC — pc_xcospfpb44aebbpemakd6eqzsu
status active · business model merchant · services vault · pricing "Default Pricing"
features: authorizations=enabled captures=enabled refunds=enabled voids=enabled full_card_api=enabled moto=disabled unreferenced_refunds=disabled
methods: visa
MCCs: 0742
AFT: ✅ via Visa AFT (`pp_etao3gtqj4ielk747rttb2uti4`) · BAI=FT · auth hold 10d · match exact
3DS: ❌ no sessions processing channel exists for this channel — 3DS not configured
pay-to-card capability: ❌ not declared here — pay-to-card is entity-scoped — declared by Active payout processing profiles; processing channels carry no pay-to-card capability → see pay-to-card.md
  (but note: a card payout request still **requires** a `processing_channel_id` — capability is entity-scoped, the payload field is not)

| Processor | Acquirer | Scheme | MCC | → Profile | Match | Auth | Cap | Ref | Void | GWS | Currencies |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Visa | cko_visa_gb | visa | 0742 | Visa AFT (payin) | exact | same_as_pc | same_as_pc | same_as_pc | same_as_pc | No | 147 currencies (all majors) |
