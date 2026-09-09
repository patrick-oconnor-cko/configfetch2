# CAT API → Merchant Profile source map

Maps the CAT GET API onto the 9 profile sections. `{clientId}` and `{entityId}` are the two keys
everything hangs off. Grounded in the OpenAPI spec (`swagger.json`, 159 paths / 134 GET).

**Environments:** base URL is `https://client-admin.cko-{env}.ckotech.co/api`, env ∈ `sbox` | `prod` | `qa`.
Run against **sbox** (`https://client-admin.cko-sbox.ckotech.co/api`); swagger was pulled from qa.
**Auth:** header `Authorization`; value `Bearer <Okta token>` (read-only needs an `app.atlas.cat.*` group) **or** `ApiKey <key>`.
**Response format:** HAL — lists come wrapped in `_embedded.<key>[]` with `limit/skip/total_count`. Countries are ISO-3.

## ✅ Confirmed field locations (from swagger)
- **FT types + corridors** → `GET /entities/{entityId}/pay-to-card-schemes/{scheme}` returns `ApprovedFundsTransferType`: `funds_transfer_type`, `approved_origination_countries[]`, `approved_destination_countries[]`, `merchant_category_code`. *(list schemes first via `/entities/{entityId}/pay-to-card-schemes` → `scheme_value`)*
- **Scheme / acquirer / MID / capture** → `GET /processing-channels/{processingChannelId}` returns `ProcessorListItem[]`: `acquirer_id`, `acquirer_name`, `scheme`, `merchant_category_code`, `processing_currencies[]`, `mode`, and `authorizations/captures/refunds/voids` flags.
- **Reserves, settlement schedule, MCCs, capabilities, currency scope** → all inside `GET /entities/{entityId}` (`Reserves.rolling`, `Settlements.schedule`, `processing_scope.merchant_category_codes`, `capabilities.is_payments/payouts/issuing_available`, `currency_scope.holding_currencies`).
- **PCI level** → `GET /processing-entities/{entityId}` (`ProcessingEntityResponse`: `pci_compliance_level`, `pci_compliance_expiry_date`).

## ⚠️ Corrections to earlier assumptions
- **Reserve rules** ARE in CAT (entity `funding.reserves.rolling`), not only the public API.
- **Settlement schedule/model** is in the entity object (`sub_entities_profile.settlements`), not a standalone endpoint.
- **Authorization-hold expiry** is NOT clearly present in this spec (the only `expiry` field is PCI compliance). Treat auth-expiry as **source TBC** — likely a scheme default or inside a processing-profile JSON that the spec types as `any`.
- Endpoints typed as `any` in the spec (need live calls to see real shape): `/entities/{e}/services`, `/entities/{e}/pay-to-card-entity`, `/entities/{e}/payout-settings`, `/entities/{e}/currency-accounts`.

**Convention:** endpoints ending in `/configuration` or `/json-schema*` return the *shape/enums* of a setting (reference data), **not** a merchant's values. The generator fetches **instance** endpoints (those below); it may fetch `/configuration` once, cached, to resolve labels/enums.

---

## Fetch order (dependency graph)
```
1. /clients/:clientId                      -> client identity
2. /clients/:clientId/entities             -> entity list (ids)
3. per entity: /configuration/breadcrumb?entityId  -> parentage -> build tree
4. per entity: fan out to all section endpoints below
```

---

## §1 Identity & business profile
| Field | Endpoint |
|---|---|
| client name, legal entity, region | `/clients/:clientId` (+ `/v2`) |
| processing region | `/clients/:clientId/processing-region` |
| MCC label lookup | `/configuration/merchant-category-codes` (reference) |
| CKO legal entity / region labels | `/configuration/cko-legal-entities`, `/configuration/regions` (reference) |

## §2 Entity structure
| Field | Endpoint |
|---|---|
| all entities for client | `/clients/:clientId/entities` |
| entity detail (country, type, status) | `/entities/:entityId` |
| **parentage / hierarchy** | `/configuration/breadcrumb?entityId=` |
| enabled services (≈ capabilities) | `/entities/:entityId/services` |
| processing-entity view | `/processing-entities/:entityId` |

## §3 Processing channels  ← core
| Field | Endpoint |
|---|---|
| channels for entity | `/entities/:entityId/processing-channels` |
| all channels for client | `/clients/:clientId/processing-channels` |
| channel detail | `/processing-channels/:processingChannelId` |
| processing profiles (per entity / by id) | `/entities/:entityId/processing-profiles`, `/processing-profiles/:id` (+ `/v2/:id`) |
| processor on a channel (MID/acquirer link) | `/processing-channels/:pcId/processors/:prId` |
| acquirer settings | `/acquirers/:id/settings` |
| processor→acquirer currencies | `/processors/configuration/currencies?acquirerId=` |
| processor profiles for entity | `/entities/:entityId/processors/configuration/profiles` |

⚠️ **auth expiry / auto-capture** location unconfirmed — expected inside `processing-profiles/:id` or the processor object. Confirm from a response body.

## §4 Scheme & payment-method enablement
| Field | Endpoint |
|---|---|
| card scheme enablement (acquirer/scheme) | `/sessions-processors/acquirer-scheme-settings`, `/session-profile-processors/scheme-configuration` |
| sessions (3DS/auth) channel config | `/entities/:entityId/sessions-processing-channels`, `/sessions-processing-channels/:id` |
| APM enablement (via pricing profiles) | `/entities/:entityId/apm-pricing-profiles` (+ `/v2`) |

Note: card acceptance schemes are derived from **processors** (§3) + acquirer-scheme-settings; there is no single "schemes enabled" endpoint.

## §5 Money-out / payouts  ← core
| Field | Endpoint |
|---|---|
| payout routes | `/entities/:entityId/payout-routes` (+ `/v2`) |
| payout routing rules | `/entities/:entityId/payout-routing-rules`, `/payout-routing-rules/:id` |
| payout settings / schedule | `/entities/:entityId/payout-settings`, `/entities/:entityId/payout-settings/:scheduleId` |
| available networks per corridor | `/entities/:entityId/payment-networks/:countryIso3/:currency` |
| **pay-to-card entity config** | `/entities/:entityId/pay-to-card-entity` |
| **pay-to-card schemes (per entity / per scheme)** | `/entities/:entityId/pay-to-card-schemes`, `/entities/:entityId/pay-to-card-schemes/:scheme` |
| pay-to-card routing / pricing | `/entities/:entityId/pay-to-card-routing-rules`, `/entities/:entityId/pay-to-card-pricing-profiles` |
| forex for pay-to-card / liquidity | `/entities/:entityId/forex-pay-to-card`, `/entities/:entityId/forex-instant-liquidity` |
| pay-to-bank pricing | `/entities/:entityId/pay-to-bank/pricing-profiles` |
| payout instruments (destinations) | `/payment-instruments/:paymentInstrumentId` |
| bank payout processors/profiles | `/bank-payout-processors`, `/bank-payout-profiles` |

⚠️ **FT types (e.g. FD)** location unconfirmed — expected inside `pay-to-card-schemes` or `payout-routes`. Confirm from a response body.

## §6 Settlement & funds
| Field | Endpoint |
|---|---|
| currency accounts | `/entities/:entityId/currency-accounts`, `/currency-accounts/:id` |
| settlement/payout schedules (client settlements config) | `/schedulers` |
| vault / flow accounts | `/clients/:clientId/vault-account`, `/clients/:clientId/flow-account`, `/clients/:clientId/legacy-vault-account` |

⚠️ **Gaps:** no obvious **reserve-rules** or explicit **settlement model (net/gross)** GET here — may live in `payout-settings` or `/schedulers` body, or be out of scope for this collection. Confirm.

## §7 Capabilities matrix (derived — no direct endpoint)
Derived in the generator from:
- `/entities/:entityId/services` (what's switched on)
- `/configuration/feature-toggles` (feature flags)
- `/entities/:entityId/payment-networks/:country/:currency` (pay-to-card corridor truth)
- §3 processors + §5 pay-to-card-schemes

## §8 Risk & authorization
| Field | Endpoint |
|---|---|
| client risk settings | `/clients/:clientId/risk-settings` |
| entity risk settings | `/entities/:entityId/risk-settings` |
| network tokens (auth optimization) | `/clients/:clientId/network-tokens` |
| 3DS / authentication (sessions) | `/entities/:entityId/sessions-processing-channels`, `/sessions-processors/*` |

## §9 Reporting & integration surface
| Field | Endpoint |
|---|---|
| API credentials (access keys) | `/clients/:clientId/access-keys`, `/access-keys/:id` |
| public keys | `/clients/:clientId/public-keys` |
| standalone reference tokens | `/clients/:clientId/standalone-reference-tokens` |
| integration products (flow/vault) | `/clients/:clientId/flow-account`, `/clients/:clientId/compass-settings` |
| dashboard users / access | `/clients/:clientId/dashboard-users` |
| enabled features | `/configuration/feature-toggles` |

⚠️ **Gaps:** no **reporting profiles** or **webhook subscriptions** GET in this collection.

---

## Cross-cutting / reference (fetch once, cache — not per-merchant)
`/configuration/countries|currencies|regions|merchant-category-codes|us-states|cko-legal-entities|country-calling-codes|timezones|statuses-and-reasons|feature-toggles|json-schema-integrations`
All `*/configuration` and `*/json-schema*` endpoints.

## Operational
- `/permissions/me`, `/permissions/permitted-actions` — the **caller's** scopes. Generator should call this first: coverage of each section depends on what the service account is allowed to read. Missing scope → mark that section `coverage: unknown` rather than empty.

---

## Remaining before writing normalize code
1. **Live responses for the `any`-typed endpoints** — services, pay-to-card-entity, payout-settings, currency-accounts. Run `fetch_samples.py` with a token + test client/entity.
2. **Confirm auth-expiry** — whether it exists anywhere in CAT, or comes from scheme defaults / public API. Flag as `coverage: unknown` until confirmed.
3. **ISO-3 → ISO-2** — CAT uses ISO-3 country codes; profile schema uses ISO-2. Generator normalizes.
4. **Public API** sources reserve rules were expected there but are actually in CAT; still use public API for **reporting profiles** and **webhook subscriptions** (absent from CAT).
