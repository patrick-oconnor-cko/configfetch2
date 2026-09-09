# Checkout.com configuration — PTOC - UK LTD

Entity `ent_q7qxjp2ctv67yejt2wjmawuu5q`, incorporated GB · environment **sandbox**
Snapshot `snap_20260804T1638·q7qxjp2c` taken 2026-08-04T16:38:47Z. Point-in-time: configuration may have changed since.

## How to use this

1. **This document is authoritative for this merchant's configuration** and overrides any documented default. If it says a capability is off, it is off.
2. **If a fact is not here, answer "unknown".** Do not infer configuration from documentation, and do not fill gaps with typical or default values. The *What this does not cover* section at the end lists known blind spots.
3. **Payload questions need BOTH this document and the Checkout docs, config first.** Config values *select which documented rules apply* — see *Validating a payload* below. Never answer a payload question from config alone or docs alone.
4. **Field names, types, enums and error codes come from the Checkout.com docs via the `checkout-mcp-sandbox` MCP server** — not from this document, and not from memory. This is a sandbox snapshot, so use the sandbox MCP server, not production. If you cannot retrieve a schema, say so rather than guessing its shape.
5. **State the snapshot date** on any answer that depends on configuration, and suggest regenerating if the answer matters and the snapshot is old.
6. **This is one entity at one point in time, and it stands alone.** It covers only `ent_q7qxjp2ctv67yejt2wjmawuu5q` as of the snapshot above. Do not blend in configuration from a sibling entity, an earlier snapshot, a previous conversation, or live API calls made elsewhere. If something here conflicts with anything you saw before, this document wins; if it is silent, the answer is "unknown" — not whatever was true previously.
7. **This document is complete in itself. There are no companion files.** Do not list directories, look for a `merchant-context/` folder, read `CLAUDE.md`, or search the filesystem for configuration — none of it exists. Everything known about this merchant's configuration is in the text below. The only external lookup you should make is to the `checkout-mcp-sandbox` MCP server for API documentation.
## How to answer a general overview question

When asked anything of the form *"give me an overview of my configuration"*, *"summarise my entity's setup"*, *"how am I configured"* — however it is phrased — answer by **reproducing the tables below, as tables, in this order**:

1. **Overview**
2. **Processing channels** — the summary table only, not the per-channel detail blocks beneath it
3. **AFT** — both tables
4. **Pay-to-card** — the summary table and the payout profiles table
5. **Currency accounts**
6. **Payout schedules**
7. **Routing** — both tables
8. **Value-added services**, then **Intelligent acceptance**, **Real Time Account Updater**, **Network tokens**

That is the order these sections appear in below, so you can work straight down the document. **Skip** *Pay-in processing profiles*, *Payout instrument*, *Webhooks and workflows*, *Reporting profiles*, *Schemes & payment methods* and *Validating a payload* — they are detail for specific questions, not part of a general overview.

Rules for that answer:

- **Reproduce the tables. Do not paraphrase them into prose.** The tables are the answer; a wall of sentences is not.
- **Do not invent tables, groupings or scope-model summaries of your own.** If a fact is not in a table here, leave it out.
- **Never mention another entity.** This document covers one entity. Do not list siblings, compare against them, or describe the client's other entities — even to say they are out of scope.
- Keep prose to a few short lines: the snapshot date, and at most two or three observations that are genuinely derived (for example a scheme enabled for acceptance but with no AFT profile, or a payout profile with a narrower corridor than the summary implies). Put those **after** the tables, not before.
- Do not add closing offers, next-step menus, or restatements of what the tables already say.

For a question about one area only (AFT, pay-to-card, settlement, a named channel), reproduce just that area's tables and skip the rest.

## Overview

|  |  |
|---|---|
| Client | PTOC Sandbox `cli_scna7ew7mxdenl3h36zlmkyh6m` |
| Entity | PTOC - UK LTD `ent_q7qxjp2ctv67yejt2wjmawuu5q` · also known as PTOC UK LTD |
| Date created | 2026-08-04T11:03:27Z |
| Status | active · payments ✅ · payouts ✅ · AFT ✅ |
| Legal entity | cko-ltd-uk |
| Business model | merchant |
| Principal address | Wenlock Works, Shepherdess Walk, London, N1 7BQ, GBR |
| Registered address | 99 Wenlock Works, Shepherdess Walk, London, N1 7BQ, GBR |
| Processing URLs | `http://www.PTOCUK.com` |
| Timezone | Europe/London |
| Card schemes accepted | mastercard, visa |
| APMs | — |
| Processing channels | 1 |
| Processing profiles | 6 |
| Settlement currencies | GBP |
| Auth hold by scheme | mastercard 7d · visa 10d |
| Pay-to-card | ✅ mastercard, visa · FT C52, FT |

**Notable gaps**

- Amex not enabled for acceptance.

## Processing channels

| Name | Processing channel ID | Schemes | Currencies | Processing profiles | 3DS | AFT | MCC |
|---|---|---|---|---|---|---|---|
| PTOC UK LTD | `pc_g6p2adehraje5mvumnna3qvtai` | mastercard, visa | GBP | Visa Pay in UK, Visa VAS, Mastercard Payin, Mastercard VAS | ✅ | ✅ | 5137, 7311 |

Currencies and profiles are per-processor; a channel's values are the union across its processors. "none matched" means the processor is configured directly against an acquirer rather than through a profile.

#### PTOC UK LTD — pc_g6p2adehraje5mvumnna3qvtai
status active · business model merchant · services vault · pricing "Cards"
features: authorizations=enabled captures=enabled refunds=enabled voids=enabled full_card_api=enabled moto=disabled unreferenced_refunds=disabled
methods: mastercard, visa
MCCs: 5137, 7311
AFT: ✅ via Visa Pay in UK (`pp_4z4nibkjb54ubacxj43tvzav7i`) · BAI=FT · auth hold 10d · match exact
3DS: ✅ visa 2 · visa 2 · mastercard 2 · mastercard 2
pay-to-card capability: **n/a at this level** — pay-to-card is entity-scoped — declared by Active payout processing profiles; processing channels carry no pay-to-card capability → see the **Pay-to-card** section below
  (this is **not** a negative for this channel. A card payout request still **requires** a `processing_channel_id`, and this channel is a valid choice — capability is entity-scoped, the payload field is not. The channel's own scheme/MCC/currency values do not have to match the payout profile's.)

| Processor | Acquirer | Scheme | MCC | → Profile | Match | Auth | Cap | Ref | Void | GWS | Currencies |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Visa UK Clothes | cko_visa_gb | visa | 5137 | Visa Pay in UK (payin) | exact | same_as_pc | same_as_pc | same_as_pc | same_as_pc | No | 1 currencies (missing USD, EUR, AED, SAR, JPY, AUD, CAD, CHF, SEK) |
| Visa VAS | cko_visa_gb | visa | 7311 | Visa VAS (payin) | exact | same_as_pc | same_as_pc | same_as_pc | same_as_pc | No | 1 currencies (missing USD, EUR, AED, SAR, JPY, AUD, CAD, CHF, SEK) |
| MC Pay In | cko_mc_gb | mastercard | 5137 | Mastercard Payin (payin) | exact | same_as_pc | same_as_pc | same_as_pc | same_as_pc | No | 1 currencies (missing USD, EUR, AED, SAR, JPY, AUD, CAD, CHF, SEK) |
| MC VAS | cko_mc_gb | mastercard | 7311 | Mastercard VAS (payin) | exact | same_as_pc | same_as_pc | same_as_pc | same_as_pc | No | 1 currencies (missing USD, EUR, AED, SAR, JPY, AUD, CAD, CHF, SEK) |

## AFT (Account Funding Transactions)

**A pay-in processing profile carrying a BAI is AFT-enabled — that is what enables AFT.** A channel is AFT-enabled when one of its processors resolves to such a profile (joined on acquirer + scheme + MCC); AFT is not a field on the channel itself.

**AFT-enabled pay-in profiles**

| Profile | Scheme | BAI | Category | Currencies | MCC | BIN | Acceptor country | Recipient details | Recipient name | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| Visa Pay in UK | visa | `FT` | **money transfer** — Funds transfer | GBP | 5137 | 402121 | GB | not required | may be omitted | Active |


| Channel | Via profile | BAI | Category | Currencies allowed | Auth hold |
|---|---|---|---|---|---|
| PTOC UK LTD `pc_g6p2adehraje5mvumnna3qvtai` | Visa Pay in UK | `FT` | **money transfer** — Funds transfer | GBP | 10d |

**There are no corridor country lists on a pay-in AFT profile.** Verified across every profile on this client: `origination_countries` and `destination_countries` appear only on *payout* profiles (see Pay-to-card). What a pay-in AFT profile does carry is the acceptor's own country and the two recipient controls above. AFT destination/recipient **countries** are therefore **unknown** from config, not unrestricted. The BAI category above comes from the Checkout.com card payouts documentation, not from CAT; a money transfer requires a `sender` block on the request.

## Pay-in processing profiles

Acceptance profiles. AFT profiles carry the Business Application Identifier (BAI),
the authorization hold, and SCA exemptions.

| Name | Scheme | Acquirer | BIN | MCC | AFT BAI | Auth hold | Quasi-cash | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| Visa Pay in UK | visa | cko_visa_gb | 402121 | 5137 | FT | 10d | no | e_commerce | Active |
| Mastercard Payin | mastercard | cko_mc_gb | 518489 | 5137 | — | 7d | no | e_commerce | Active |
| Mastercard VAS | mastercard | cko_mc_gb | 518489 | 7311 | — | 7d | no | e_commerce | Active |
| Visa VAS | visa | cko_visa_gb | 402121 | 7311 | — | 10d | no | e_commerce | Active |

### SCA exemptions

| Profile | TRA | Low value | Secure corp | 3DS outage | Trusted listing | SCA delegation |
|---|---|---|---|---|---|---|
| Visa Pay in UK | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| Mastercard Payin | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Mastercard VAS | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Visa VAS | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |

## Pay-to-card

**Scope: entity-level.** Declared by processing profiles with `processing_type=payout` and `status=Active`. Processing channels carry no pay-to-card capability — never answer this per channel.

**A payout profile is not bound to a processing channel.** If an Active payout profile exists on this entity it can be used with **any** of the entity's processing channels. The acquirer + scheme + MCC join that resolves a channel to a profile applies to **pay-in AFT only** — do not apply it here. In particular, a channel MCC that differs from a payout profile's MCC is **not** a mismatch and does not make the payout unroutable: the payout profile supplies the MCC, the channel does not have to match it. A card payout still requires a `processing_channel_id` in the request, but that field selects a channel, not the payout profile.

|  |  |
|---|---|
| Schemes | mastercard, visa |
| Funds transfer types | C52, FT |
| Supported MCCs | 6051, 6536 |
| Origination countries | 1 — GB |
| Destination countries | 4 — AE, DE, FR, GB |
| Currencies | not stated on the payout profiles |
| Forex | ✅ enabled |


**Payout profiles (the pay-to-card processors)**

| Profile | Scheme | FT type | Category | `sender` required | BIN | CAIC | MCC | Origination | Destination | Acceptance | Legal entity | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Visa PTC | visa | `FT` | **money transfer** — Funds transfer | ✅ yes | 435000 | 892769 | 6051 | GB | AE, DE, FR, GB | e_commerce | — | Active |
| MC PTC | mastercard | `C52` | **money transfer** — Transfer to own account | ✅ yes | 518489 | 892769 | 6536 | GB | DE, FR, GB | e_commerce | — | Active |

Origination and destination are **per profile** — the section summary above is the union across profiles, which can hide a profile with a narrower corridor.
Category comes from the Checkout.com card payouts documentation ("Funds transfer types"), not from CAT — CAT reports only the code. A **money transfer** requires a `sender` block on the payout request; the other categories do not require one on that basis.

## Currency accounts

**Scope: this entity.** Currency accounts, routing rules and payout schedules below are all read from `ent_q7qxjp2ctv67yejt2wjmawuu5q`'s own endpoints and belong to it. (Webhooks and workflows are client-level and shared with sibling entities.)

|  |  |
|---|---|
| Settlement currencies | GBP |
| Currency accounts | 3 |
| Payout schedules | 1 |

| Account | Name | Currency | Status | Used for |
|---|---|---|---|---|
| `ca_ffa3ltqlinxu3nrj7oy2ebjrae` | PTOC UK LTD Chargebacks | GBP | active | revenue |
| `ca_4ianzcgb6qounnpr3sjv2wetdm` | PTOC UK LTD Revenue | GBP | active | payout source, revenue, settlement |
| `ca_dc7erxk7yjleng7qoft7jj2kia` | PTOC UK LTD fees | GBP | active | fees |

`Used for` is derived by joining this entity's routing rules and payout instructions. A blank means no rule or instruction in this snapshot references the account — it still belongs to this entity, it is simply not routed to yet.

## Payout schedules

| Name | Threshold amount | Balance minimum | Scheduler type | Frequency | Currency account linked | Date created |
|---|---|---|---|---|---|---|
| PTOC UK | 0.0 | 0.0 | Legacy | weekdays (Mon–Fri) at 02:00 · cron `0 2 * * 1-5` | PTOC UK LTD Revenue `ca_4ianzcgb6qounnpr3sjv2wetdm` | 2026-08-04T11:26:18 |

`Frequency` is **derived** from the cron by this pack — CAT publishes no frequency field, and the cron carries no timezone, so the wall-clock time it fires is unknown. `Threshold amount` and `Balance minimum` are raw numbers with no currency or minor/major-unit indicator on the record.

## Payout instrument

| Instruction | State | Instrument | Currency | Holder | Bank | Redacted |
|---|---|---|---|---|---|---|
| PTOC UK | Active | bank_account | GBP | PTOC123 | Branch Bank Name Simulated | account_number, bank_code |

## Routing

**Scope: this entity.** Read from `/entities/ent_q7qxjp2ctv67yejt2wjmawuu5q/…-routing-rules`. Every currency account named below appears in the Settlement → Currency accounts table with its id, so the two can be cross-referenced.

### Payment routing

| Rule | Status | Matches | Events covered | Revenue → account | Fees → account |
|---|---|---|---|---|---|
| `rt_mhi7u3i4qqrevmf76m2hvxj4pq` | Active | restricted by event type | specific event types (not listed on the record) | PTOC UK LTD Chargebacks `ca_ffa3ltqlinxu3nrj7oy2ebjrae` | PTOC UK LTD fees `ca_dc7erxk7yjleng7qoft7jj2kia` |
| `rt_qzovsjkjcsjuzfnaptn65unfwe` | Active | **all traffic** — every condition unrestricted | all event types | PTOC UK LTD Revenue `ca_4ianzcgb6qounnpr3sjv2wetdm` | PTOC UK LTD fees `ca_dc7erxk7yjleng7qoft7jj2kia` |

### Payout routing

| Rule | Status | Matches | Events covered | Revenue → account | Fees → account |
|---|---|---|---|---|---|
| `rt_dkxjq5eshipedoxwhx6fzupz5i` | Active | source `ca_4ianzcgb6qounnpr3sjv2wetdm` | specific event types (not listed on the record) | PTOC UK LTD Revenue `ca_4ianzcgb6qounnpr3sjv2wetdm` | PTOC UK LTD fees `ca_dc7erxk7yjleng7qoft7jj2kia` |

Routing rules carry no name in CAT, so they are identified by id and described by what they match. `event_types` is one of the conditions: an unrestricted rule matches every event type.

## Value-added services

Which services are switched on. Each service is configured separately — the two with substantial configuration have their own sections after this.

| Service | State | Scope / note |
|---|---|---|
| Intelligent acceptance | ✅ enabled | client-level · own section below |
| Network tokens | ❌ not enabled | client-level · own section below |
| Real Time Account Updater | ✅ enabled on Mastercard, Visa | client-level · per scheme · own section below |
| vault | ✅ enabled | on this entity's processing channels |
| direct_api | ✅ enabled | integration type |
| flow | ✅ enabled | integration type |
| risk_tier:premium | ✅ enabled | risk / fraud |

## Intelligent acceptance

**Scope: client-level**, inherited by every entity including this one.

|  |  |
|---|---|
| Enabled | ✅ yes |
| Strategy | **Custom, 3DS upgrade** (`custom_3ds_upgrade`) |
| Addons enabled | ✅ yes — 2 of 21 selected |
| Transactions processed by IA | 100% |

Everything below is detail — use it for a deep dive on Intelligent Acceptance, not for a high-level overview.

**What the Custom, 3DS upgrade strategy does**

> Custom: Strategy that can be tailored to merchant needs and preferences; it already allows all ISO8583 optimizations, 3DS optimizations, Network Tokens on the first attempt and fallback where necessary, AFT retries, exemptions, and preferred scheme routing where processors are configured. Functionalities can be controlled via the usage of add-ons.
> 3DS upgrade: Allows 3DS upgrades.

**Addons enabled — 2 of 21**

| Addon | What it does |
|---|---|
| Restrict Visa Cat1 retries for MIT transactions | Disables retrying on Visa Category 1 decline codes for MIT transactions |
| Enable NSF MIT retries | Enable insufficient fund retries on MITs |


**Optional addons available but not enabled — 19**

Disable API 3DS (`disable_upapi_3ds_requests`), Smart MCC Routing (`enable_smart_mcc_routing`), Disable CVV optimizations (card verification only) (`disable_cvv_optimizations_card_verif_only`), Disable CVV optimizations (`disable_cvv_optimizations`), Disables AFT downgrades (`disable_aft_downgrades`), Disable double authentication retries (`disable_double_authentication_retries`), Honour 3RI (`honour_3ri`), Disable authentication downgrades (`disable_3ds_downgrades`), Disable 3DS upgrades on retries for US based issuers (`disable_3ds_upgrades_on_retries_us_issuers`), Disable NSF CIT retries (`disable_nsf_cit_retries`), Disable Google SPA Authentication (`disable_google_spa`), Honour AFT requests on the initial attempt (`honour_aft_initial_attempt`), Restrict double EMVCo challenge (`restrict_double_emvco_challenge`), Restrict retries on recommendation code 03/21 for MIT Mastercard (`disable_mastercard_03_recommendation_code_retries_mit`), Restrict retries on recommendation code 03/21 for CIT Mastercard (`disable_mastercard_03_recommendation_code_retries_cit`), Restrict Visa Cat1 retries for CIT transactions (`disable_visa_cat1_retries_cit`), Disable 3DS upgrades on card verifs (`disable_3ds_upgrades_card_verif`), Restrict 3DS upgrades on first attempt (`restrict_3ds_upgrades_first_attempt`), Restrict 3DS upgrades on first attempt for US issuers (`restrict_3ds_upgrades_first_attempt_us_issuers`)

These are selectable under this strategy and are currently off. Off is a real negative here, not an unknown.

The configuration form carries a separate addon set for each strategy; only the active strategy's (`custom_3ds_upgrade`) is reported — the others are dormant UI state, not configuration in force.

## Real Time Account Updater (RTAU)

**Scope: client-level**, inherited by every entity including this one. **Configured per scheme** — there is no single on/off switch, so "is RTAU on" has to be answered scheme by scheme.

|  |  |
|---|---|
| Billed entity | PTOC - UK LTD `ent_q7qxjp2ctv67yejt2wjmawuu5q` |
| MCC | 7311 - Advertising Services |
| Schemes with something active | Mastercard, Visa |

The active-schemes row is **derived** by this pack from the switches below, not a field CAT provides.

### Mastercard

| Setting | Enabled |
|---|---|
| Activate Store & Update | ✅ yes |
| Activate Update & Retry (Standalone) | ✅ yes |

| Field | Value |
|---|---|
| Reminder! | For correct work of RTAU Mastercard Update & Retry, merchant's processing configuration across all Mastercard processing channels has to be configured on a profile processor/processing profile, not manual processor. |
| Scheme merchant id / CAID | 000023456543456 |
| Mastercard Store & Update registration status | **unknown** — not published on the configuration |
| Mastercard Update & Retry registration status | **unknown** — not published on the configuration |


### Visa

| Setting | Enabled |
|---|---|
| Activate Visa Rtau | ✅ yes |
| Activate Visa Standalone | ❌ no |

| Field | Value |
|---|---|
| Scheme merchant id / CAID | 000023456543456 |
| Visa Rtau registration status | **unknown** — not published on the configuration |
| Visa Standalone registration status | **unknown** — not published on the configuration |


### American Express

| Setting | Enabled |
|---|---|
| Activate Amex Batch Account Updater (Standalone) | ❌ no |
| Opt Blue | ❌ no |

| Field | Value |
|---|---|
| Service Establishment Number(s) | not set |
| Seller ID | not set |
| Amex registration status | **unknown** — not published on the configuration |


### Batch Account Updater

| Setting | Enabled |
|---|---|
| Activate Visa & Mastercard Batch Account Updater | ❌ no |

| Field | Value |
|---|---|
| Batch Account ID | not set |


Registration statuses are blank on this configuration for every scheme. Blank means the status is **not published here** — it does not mean not registered. Check the Dashboard if registration state matters.

## Network tokens

**Scope: client-level.** These settings belong to the client and are **inherited by every entity**, including this one — they are not configured per entity.

|  |  |
|---|---|
| Network tokens allowed | ❌ no |
| Default billed entity | PTOC Sandbox `ent_juznxdro7lhwrf3c5e4wprftgu` |
| Provisioning enabled | ✅ yes |
| Provisioning mode | **Synchronous** (`sync`) |

**Scheme onboarding**

| Scheme | Transactions enabled | Onboarded | TRID |
|---|---|---|---|
| visa | ✅ yes | 21 Jul 2026 | `133700200` |
| mastercard | ✅ yes | 21 Jul 2026 | `98765400200` |

Onboarding date and TRID are only published as free text on the configuration form, not as structured fields — they are parsed from it.

⚠️ **Note the combination.** Network tokens are **not allowed** at client level, yet provisioning is enabled and schemes are onboarded with transactions enabled. The master switch governs whether Checkout-managed network tokens are used at all, so the scheme-level readiness below it does not imply tokens are in use. If the answer matters, verify in the Dashboard rather than reasoning from one field.

## Webhooks and workflows

**Scope: client-level.** Workflows belong to the client, not this entity, so they may fire for sibling entities too.

_no workflows_

## Reporting profiles

**Scope: this entity.** Each entity has its own reporting profile setup; these belong to `ent_q7qxjp2ctv67yejt2wjmawuu5q`. Read from the reporting-profiles-config-api, a separate internal service to CAT.

| Enabled | Name | Report type | Created | Profile id |
|---|---|---|---|---|
| ❌ | Default Settlement Breakdown Report | Settlement breakdown | 2026-08-04 | `875e4099-897c-496f-b169-5ccdebc05d7f` |
| ✅ | Default Financial Actions Report | Financial actions by date range | 2026-08-04 | `7752dea8-b2d0-49cc-b5fb-610814160dcd` |
| ❌ | Default Balance Statement Report | Balance | 2026-08-04 | `50490244-db0f-48fb-b976-28e52864c866` |
| ❌ | Default Balance Breakdown Report | Balance breakdown | 2026-08-04 | `fbeb6f86-14a6-48c5-abc6-02a75d64b410` |
| ✅ | Default Payout Summary Report | Payouts | 2026-08-04 | `56ad5ebc-4136-49d8-9169-93d99ee4bda1` |
| ✅ | Default Financial Actions By Payout Report | Financial actions by payout | 2026-08-04 | `f4552605-6f9f-4930-93eb-edd86079e1de` |
| ✅ | Default Settlement Statement Report | Settlement statement | 2026-08-04 | `e3c63116-c465-4d50-8d1f-5201ac18c48b` |
| ✅ | Default Invoice Report | Invoice | 2026-08-04 | `edc706d7-db4a-4cfb-a128-edd9ba17eefd` |

5 of 8 enabled. A disabled profile exists but does not produce reports.

## Schemes & payment methods

### Card schemes

| Scheme | Enabled | Auth hold (days) |
|---|---|---|
| mastercard | ✅ | 7 |
| visa | ✅ | 10 |

### Alternative payment methods

_none_

## Validating a payload

Read the config value first, then look up the documented rule it triggers. Each row below is a value in this document that changes what the API requires.

| Config value (in this document) | Selects which documented rule applies |
|---|---|
| funds transfer type / BAI — see AFT and Pay-to-card | which payout codes are legal for this merchant; **money-transfer codes require a `sender` block** |
| country of incorporation — see the registered business address in Overview | US-incorporated → recipient `billing_address` is mandatory on every card payout |
| destination corridors — see Pay-to-card | issuer country AR·BD·CL·CO·EG·IN·MX·SA → `instruction.purpose` becomes mandatory |
| processing channels — see Processing channels | `processing_channel_id` is **required** on card payouts. **Any** Active channel on this entity is valid — channels are not pay-in or payout scoped for pay-to-card, and the channel does not select the payout profile |
| currency accounts — see Settlement | `source.id` must be a real `ca_*`; funding vs payout currency decides whether FX applies |
| MCC — see Processing channels / Pay-to-card | MCC is **not** a field on a payout request; it comes from the profile the payout routes to |

When validating, check the values against this document **and** retrieve the request schema from the docs for the required-field list. Report which specific values are wrong for this merchant, not just whether the shape is valid.

**Generating an example payload — which card to use**

| Scheme | Number | Expiry | CVV |
|---|---|---|---|
| Visa | `4242424242424242` | 03/30 | 211 |
| Mastercard | `5436031030606378` | 03/30 | 222 |

These are **sandbox test card numbers, not real cards.** Use them for any example or test payload without asking.

Two things override them, in this order: a card number, expiry or CVV the user supplies, and — for a **named scenario** (a particular decline code, 3DS flow, AVS result or issuer country) — the matching test card from the `checkout-mcp-sandbox` MCP server. Only reach for that lookup when the scenario is named; otherwise the table above is the answer.

Pair the card's scheme with the funds transfer type under test: the schemes on this merchant's payout profiles carry different FT codes, so swapping the card without swapping the code introduces a second, unintended finding.

## What this does not cover

| Topic | State | Note |
|---|---|---|
| velocity limits | not_available | not exposed by the CAT API |
| pay to card ft corridors | unavailable | CAT pay-to-card-schemes endpoint returns 503; corridors are derived from payout profile custom_settings instead |
| pricing | excluded | commercially sensitive |
| bank account numbers | redacted | policy — instrument type, currency and bank name are surfaced instead |
| reporting and integration | partial | webhooks/workflows come from the public API; reporting profiles from the merlin reporting-profiles-config-api (separate internal service) |
| glossary of ids | excluded | omitted to keep this document small; ids are inline throughout |

Anything marked `not_available`, `unavailable`, `not_collected` or `excluded` means **answer "unknown"** — it does not mean "no".
