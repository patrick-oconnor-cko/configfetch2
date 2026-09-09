# Checkout.com Configuration Profile — Northwind Commerce

> **Generated:** 2026-07-09 06:00 UTC · **Environment:** Production · **Schema:** v0.1.0 · **Client:** `cli_northwind_7f3a`
> Every section below is stamped with its own *as-of* date and source. Where coverage is *partial*, do not assume unlisted settings.

## 1. Business profile
- **Legal name:** Northwind Commerce Ltd
- **Account type:** Full
- **What they do:** Online brokerage and trading platform. Accepts card deposits from customers and disburses withdrawals to customer cards (pay-to-card).
- **MCC(s):** 6211 (Security brokers/dealers)
- **Operating regions:** IT, CY, AE, GB
- **Live since:** 2024-03-01

## 2. Entity structure
Single-entity account.

| Entity | ID | Incorporated | Payments | Payouts | Status |
|---|---|---|---|---|---|
| Northwind Commerce Ltd (root) | `ent_northwind_root` | IT | ✅ | ✅ | active |

## 3. Processing channels
_Source: CAT internal · as of 2026-07-09_

### Northwind IT - Cards (`pc_it_main`)
- **Entity:** `ent_northwind_root` · **Processing country:** IT · **Status:** active
- **Schemes:** Visa, Mastercard
- **MIDs:** Visa `4123001` (BIN 412300), Mastercard `5301002` (BIN 530100) · descriptor `NORTHWIND`
- **Currencies:** EUR, USD, GBP · **MCC:** 6211
- **Auth:** auto-capture ON · **auth expiry 7 days** (Visa 7 / Mastercard 7)

### Northwind FR - Cards (`pc_fr_cards`)
- **Entity:** `ent_northwind_root` · **Processing country:** FR · **Status:** active
- **Schemes:** Visa, Mastercard, Cartes Bancaires
- **MIDs:** Visa `4990211` (BIN 499021) · descriptor `NORTHWIND FR`
- **Currencies:** EUR · **MCC:** 6211
- **Auth:** auto-capture OFF (capture delay 168h) · **auth expiry 30 days** (all schemes)

## 4. Scheme & payment-method enablement
| Scheme | Enabled | Countries | Channels |
|---|---|---|---|
| Visa | ✅ | IT, FR | pc_it_main, pc_fr_cards |
| Mastercard | ✅ | IT, FR | pc_it_main, pc_fr_cards |
| Cartes Bancaires | ✅ | FR | pc_fr_cards |
| Amex | ❌ | — | — |

**APMs:** Apple Pay (IT, FR / EUR), Google Pay (IT, FR / EUR).

## 5. Money-out / payouts
- **FT types:** ✅ FD (Funding Disbursement) · ❌ GP (Gambling Payout)
- **Pay-to-card:** **Enabled**
  - IT → AE — Visa, Mastercard — FT: FD — EUR, AED
  - CY → AE — Visa — FT: FD — EUR
- **Payout destinations:** Card (AE, GB, IT) · Bank account (IT, GB)
- **Schedule:** Daily, T+1

## 6. Settlement
- **Model:** Net · **Frequency:** Daily · **Currencies:** EUR, GBP
- **Pools:** `pool_eur` (EUR → sub_it_eur), `pool_gbp` (GBP → sub_gb_gbp)
- **Reserve:** Rolling 5%, 30-day hold
- **Bank accounts:** IT/EUR (verified), GB/GBP (verified)

## 7. Capabilities matrix (derived)
**Pay-to-card:** ✅ Enabled · corridors IT→AE (Visa, MC, FD), CY→AE (Visa, FD) · MCC 6211.
**Accept payments:** IT, FR · Visa, MC, CB · EUR, USD, GBP.

⚠️ **Notable gaps (explicit "not configured"):**
- Pay-to-card to **US** is **NOT** configured.
- **Amex** is not enabled on any channel.
- No in-country **USD acquiring** channel (USD accepted on IT channel as processing currency only).

## 8. Risk & authorization  _(coverage: partial)_
- **3DS:** Enabled, risk-based · SCA exemptions: TRA
- **Auth optimization:** Network tokens ✅ · Account Updater ✅ · Intelligent retries ❌

## 9. Reporting & integration  _(coverage: partial)_
- **Reporting profile:** daily_settlement_v2 · **Reconciliation:** payment_id matched · **Format:** CSV
- **Webhooks:** payment_captured, payment_declined, payout_paid
- **Integration:** Direct API · **API version:** 2023-11-01
