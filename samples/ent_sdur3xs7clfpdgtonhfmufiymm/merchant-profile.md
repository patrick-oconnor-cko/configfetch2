# Checkout.com Configuration Profile — PTOC Sandbox

> **Generated:** 2026-07-29T19:39:44Z · **Env:** sandbox · **Client:** `cli_scna7ew7mxdenl3h36zlmkyh6m`

## 1. Business profile
- **Account type:** full
- **Doing business as:** PTOC SA
- **MCCs:** 5999
- **Regions:** SA

## 2. Entity structure
| Entity | ID | Incorp. | Payments | Payouts | Status |
|---|---|---|---|---|---|
| PTOC SA | `ent_sdur3xs7clfpdgtonhfmufiymm` | SA | ✅ | ❌ | active |
| PTOC Sandbox | `ent_juznxdro7lhwrf3c5e4wprftgu` | GB | — | — | active |

## 3. Processing channels  _(coverage: complete)_
- **PTOCSA** (`pc_uawoyrryxkgejhfk6wofeusbnm`) — active · merchant · pricing: PTOCSA
  - Methods: mada
  - MCCs: 5999
  - Features: authorizations=enabled, captures=enabled, refunds=enabled, voids=enabled, full_card_api=enabled, moto=disabled, unreferenced_refunds=disabled
  - proc PTOCSAMADA: mada / sabb_mpgs_sa, MCC 5999, mode gateway_services, auth=same_as_pc/cap=same_as_pc/ref=same_as_pc/void=same_as_pc, currencies: SAR

## 3b. Processing profiles  _(coverage: complete)_
- **pp_3ftjpvejbifuvgu74nfqyuwbye** (payin): mada / sabb_mpgs_sa, BIN —, MCC 5999, Active, auth 7d

## 4. Scheme & payment-method enablement
- **Card schemes:** —
- **APMs:** mada

## 5. Money-out / payouts  _(coverage: complete)_
- **Pay-to-card:** ❌ enabled

## 6. Settlement  _(coverage: complete)_
- **Currencies:** SAR

## 7. Capabilities matrix (derived)
- **Accept:** none (card) in SA
- **Pay-to-card:** ❌ not enabled
- **Auth hold (per scheme):** mada 7d
- ⚠️ **Gaps:**
  - Amex not enabled for acceptance.
  - No active pay-to-card (payout) processing profiles found.

## 8. Reporting & integration  _(coverage: complete)_
- **Integration:** direct_api, flow
- **Workflows:** USD, TEST p500, Capture test
- **Webhook events:** card_payout.payment_approved, card_payout.payment_declined, client_balances.sub_account_low_balance_threshold_exceeded, gateway.batch_successful, gateway.batch_unsuccessful, gateway.card_verification_declined, gateway.card_verified, gateway.payment_approved, gateway.payment_authentication_failed, gateway.payment_authorization_increment_declined, gateway.payment_authorization_incremented, gateway.payment_authorized, gateway.payment_canceled, gateway.payment_capture_declined, gateway.payment_capture_pending, gateway.payment_captured, gateway.payment_declined, gateway.payment_expired, gateway.payment_paid, gateway.payment_pending, gateway.payment_refund_declined, gateway.payment_refund_pending, gateway.payment_refunded, gateway.payment_retry_scheduled
- **Webhook endpoints:** https://webhook.site/08289c25-9be7-4ffc-bcf9-7e0e6f05dbbd, https://webhook.site/988f4820-aab4-4c76-adf3-4dc156f21b4e, https://webhook.site/c5947431-0884-4929-83f8-e4066f727f96
