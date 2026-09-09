# Checkout.com configuration — PTOC Sandbox  (SANDBOX · point-in-time snapshot)
entity `ent_juznxdro7lhwrf3c5e4wprftgu` (incorporated GB) · client PTOC Sandbox `cli_scna7ew7mxdenl3h36zlmkyh6m`
snapshot `snap_20260729T1939·juznxdro` · generated 2026-07-29T19:39:54Z · schema v0.1.0

## Rules
1. This pack is **authoritative for configuration** and overrides any documented default.
2. If a fact is absent here, or its section is marked `not_collected` / `unavailable` /
   `not_available`, answer **"unknown"**. Never infer configuration from documentation.
3. **Payload and integration questions need BOTH sources — config first.** Config
   values *select which documented rules apply*: the same endpoint has different
   required fields depending on funds transfer type / BAI, country of incorporation,
   destination issuer country, and which channel and currency account you use. So
   read the config values here, **then** look up the rules those values trigger.
   Never answer a payload question from this pack alone, or from the docs alone.
4. Field names, types, enums, error codes and scheme rules → **Checkout.com docs via
   MCP**. This pack never invents a field name. If you cannot retrieve a schema,
   say so — do not guess its shape.
5. Point-in-time snapshot. Configuration may have changed since generated_at. State the snapshot date on config-sensitive answers, and recommend regenerating for high-volatility sections.

## Scope model — read before answering any capability question

| Capability | Scope | Where to answer from |
|---|---|---|
| card acceptance | channel | sections/channels.md |
| AFT | channel (derived join) | sections/channels.md — per-channel verdict |
| 3DS / authentication | channel | sections/channels.md — per-channel verdict |
| **pay-to-card** | **entity** | sections/pay-to-card.md — *never* answer per-channel |
| payment & payout routing | entity | sections/routing.md |
| settlement, currency accounts | entity | sections/settlement.md |
| webhooks / workflows | client | sections/webhooks.md |


## Payload questions — config values that change the required fields

Read the config value, then look up the rule it triggers (Rule 3).

| Config value (in this pack) | Selects which documented rule applies |
|---|---|
| funds transfer type / BAI — pay-to-card.md | which payout codes are legal for you; **money-transfer codes require a `sender` block** |
| country of incorporation — entities.md | US-incorporated → recipient `billing_address` is mandatory on every card payout |
| destination corridors — pay-to-card.md | issuer country AR·BD·CL·CO·EG·IN·MX·SA → `instruction.purpose` becomes mandatory |
| processing channels — channels.md | `processing_channel_id` is **required** on card payouts — use the payout channel, not a pay-in one |
| currency accounts — settlement.md | `source.id` must be a real `ca_*`; funding vs payout currency decides whether FX applies |
| MCC — channels.md / pay-to-card.md | MCC is **not** a field on a payout request; it comes from the profile the payout routes to |

## Can / cannot

- accept: amex, cartes_bancaires, mastercard, visa · APMs: ideal, klarna, paypal, sofort
- pay-to-card: ✅ mastercard, visa · FT C52, FT · destinations 249 countries (global) · includes US, GB, AE, FR, SA, DE, IN, BR, CN, JP
- auth hold: amex 7d · cartes_bancaires 7d · visa 10d
- settlement currencies: AED, EUR, GBP
- entity timezone: **unknown** — never assume UTC (qualifies wall-clock answers; not necessarily the payout cron's tz — see settlement.md)
- 3DS configured on: Channel 1
- channels 4 · profiles 10 · workflows 3
- sibling entities: PTOC SA (`ent_sdur3xs7clfpdgtonhfmufiymm`, SA)

## What this snapshot does NOT know

| Topic | State | Note |
|---|---|---|
| reporting profiles | not_available | not exposed by the CAT API — check the Dashboard |
| velocity limits | not_available | not exposed by the CAT API |
| pricing | not_available | excluded by policy (commercially sensitive) |
| bank account numbers | not_available | redacted by policy |

## Where to look

| Question about | Read |
|---|---|
| a `pc_*` id · channel schemes, MIDs, features, services | sections/channels.md |
| **AFT** on a specific channel · BAI | sections/channels.md |
| **3DS** / protocol versions | sections/channels.md |
| SCA exemptions · auth hold · quasi-cash · a `pp_*` id | sections/payin-profiles.md |
| **pay-to-card** · funds transfer types · payout BIN/CAIC · corridors | sections/pay-to-card.md |
| **routing rules** · an `rt_*` id · where revenue/fees land | sections/routing.md |
| settlement · currency accounts · a `ca_*` id · payout schedule | sections/settlement.md |
| **webhooks** · workflows · events · reporting profiles | sections/webhooks.md |
| scheme / APM enablement | sections/schemes.md |
| **building a payload** · required fields · "is my request right?" | config first: pay-to-card.md + channels.md + settlement.md + entities.md → **then** docs via MCP |
| what an ID or a code means | glossary.md |
| entity structure · a `ent_*` id | sections/entities.md |

## Section index

| File | Coverage | Volatility | ~tokens |
|---|---|---|---|
| sections/entities.md | complete | low | 153 |
| sections/channels.md | complete | medium | 1371 |
| sections/payin-profiles.md | complete | medium | 322 |
| sections/pay-to-card.md | complete | medium | 337 |
| sections/routing.md | complete | high | 258 |
| sections/settlement.md | complete | low | 281 |
| sections/schemes.md | complete | medium | 113 |
| sections/webhooks.md | complete | high | 675 |
| glossary.md | complete | low | 1865 |
