# CKO Merchant Configuration Profile

Reads a merchant's Checkout.com configuration from the internal config services and renders
it so an LLM can answer questions about **this merchant's** setup rather than the product in
general.

The premise: answering a merchant's integration question needs three bodies of knowledge —
the product docs (the Checkout MCP already provides these), the merchant's own configuration
(**the gap this fills**), and the merchant's codebase (theirs). Without the middle one, an LLM
can only give generic answers.

**Read-only.** Every call this application makes is a `GET`. There is no write path.

**Two modes: Sandbox and Prod.** The switch is the first control on the page; the selected
mode is green. A run uses the service bases of one mode only (`cat_profile.ENVIRONMENTS`),
stamps `environment` into every document, and picks the matching docs MCP server name
(`checkout-mcp-sandbox` or `checkout-mcp`). Prod mode needs a PROD CAT token; the secret key is
optional in both modes and only unlocks the webhooks section. A secret key from the other
environment is refused (`sk_sbox_` in Prod, plain `sk_` in Sandbox). Switching mode clears any
results on screen, so one mode's data is never shown under the other's label.

> **Production hosts.** `ENVIRONMENTS["production"]` carries all six: the Client Admin Tool
> (`client-admin.cko-prod.ckotech.co/api`, verified live), the public API (`api.checkout.com`),
> and the four internal services on their `.prod.` hosts (merlin, nt-portal, pp-tenet-int,
> rtau — same paths as sandbox). Note the CAT swagger's servers list names
> `client-admin-prod.ckotech.co` as "Prod"; that name has no DNS record and is not used. Any
> base set back to `None` degrades only its own section to `unavailable` with the reason "host
> is not configured for this environment"; CAT unset stops a Prod fetch before any request.
>
> A production document also replaces the test-card block with a warning not to run example
> payloads against the live account.

> Open work and design notes live in [`TODO.md`](TODO.md). Read that before starting anything
> — it carries current priorities and several hard-won API quirks.

---

## Quick start

```bash
python3 app/server.py     # http://localhost:8787
```

| Field | Notes |
|---|---|
| Mode | **Sandbox** (default) or **Prod**. Credentials are kept per mode while the page is open. |
| Client ID | Sandbox: prefills from `app/dev-creds.json`. Prod: typed. |
| **CAT API bearer token** | **paste this** — short-lived Okta token, expires in ~1h. Prod: must be a PROD token. |
| Secret key | **Optional.** Required only for webhook information: it authenticates the public-API workflow calls, which is the one thing the CAT token cannot do. Sandbox prefills `sk_sbox_…`; Prod takes `sk_…`. |

Prefill from `dev-creds.json` applies to Sandbox mode only; Prod fields always start empty.

**Fetch config** produces one pack *per entity* under the client. Expect 8–15s per entity
(~24 CAT calls plus four other services). While it runs the main pane shows a **progress bar
and a live call log**: `POST /api/generate` streams newline-delimited JSON events — `start`,
`entities` (the list, once known), `entity_start`/`entity_done`, one `call` per GET with
service, path, HTTP status and duration, then `result` or `error`. The bar is exact per
completed entity and estimates the in-flight one from the previous entity's call count. Calls
never include the token or response bodies.

**Failures are flagged, not buried.** A call that returns non-200, or gets no response at all
(DNS, VPN, timeout), is tinted red in the log with its status — or "no response" — and error
text. The progress line counts failures split by kind. After the run a warning banner above
the results lists them per service with the reasons and the entities affected, and explains
the consequence: the dependent sections are `unavailable` in the documents, which means
"answer unknown", not "no". The log stays above the results — collapsed when clean, open when
anything failed. A fetch that fails outright (401, unknown client, unreachable host) keeps the
progress panel open with the diagnosis as its last line. `Ctrl+C` to stop the server.

> ### Restart the server after any renderer change
> `server.py` imports `cat_profile` and `llm_bundle` once at startup and Python caches
> modules. Editing a renderer and hitting **Fetch config** on the running process silently
> regenerates with the **old** code. This has caused real confusion — removed sections
> reappearing, fixes seeming not to apply. Restart, every time.

### Requirements

Python **3.9+** and nothing else — pure standard library. `requirements.txt` lists two
optional extras (`pycountry` widens country-code coverage; `jsonschema` is used only by the
CLI).

---

## Output

Four tabs, all projections of one canonical profile so they cannot drift.

| Tab | What it is |
|---|---|
| **Client Markdown** | One document for the **client**, with every entity as its own section beneath it — see below. |
| **LLM Markdown** | 17 files per entity: `project-instructions.md` (the single-entity artifact — see below), `INDEX.md`, `README.md`, `lookup.json`, 12 `sections/*.md` and `glossary.md`. |
| **llms.txt** | Single flat ~1–2k-token summary for pasting into a prompt |
| **JSON** | The canonical profile, validated against `schema/merchant-profile.schema.json` |

### Client Markdown — several entities in one document

After a fetch, the tab renders one markdown document covering every entity under the client,
with the hierarchy kept explicit: the client (`cli_…`) at the top, then a `## Entity:` section
per entity, each rendered by **the same functions as `project-instructions.md`** and demoted
one heading level. Per-entity tables are therefore byte-identical to the single-entity
document; only heading depth differs. For a single entity, use that entity's
`project-instructions.md` from the LLM Markdown tab instead.

What changes is the framing. The single-entity rules "this document stands alone" and "never
mention another entity" are replaced by a *resolve the entity first* rule: a question that
names an entity (or an id that appears in only one section) is answered from that section
alone; a question that names none is answered per entity, kept separate, with client-level
services (IA, network tokens, RTAU, webhooks) stated once. So *"summarise my config on
ENT 123"* and *"summarise my config in general"* both work from one paste. The *Validating a
payload* block and test cards appear once at client level; *What this does not cover* stays
per entity because it is derived per entity.

The tab calls `POST /api/client-doc`, which re-renders the profiles the browser already holds.
It makes no CAT call and needs no credentials. The renderer accepts any subset of a client's
profiles and lists the ones left out as needing their own snapshot, so a per-entity selection
can be reinstated without renderer changes.

### `project-instructions.md` — the artifact you actually use

One self-contained document, roughly 5,000–7,600 tokens depending on the entity (measured
across the three sample entities after the CAID and AFT additions), designed to be **pasted
into the project instructions** of a Claude session that has the matching Checkout MCP
enabled — `checkout-mcp-sandbox` for a sandbox snapshot, `checkout-mcp` for production. The
document names the right one itself.

It is entity-scoped: one entity per document, no sibling entities mentioned at all. It opens
with seven rules of engagement (config is authoritative, absent means "unknown", payload
questions need config *then* docs, this document stands alone), then an **answer-format
section** telling the reading session to reproduce its tables as tables, in document order,
for general overview questions — and to skip the six detail sections.

Sections, in the order an overview answer should use them: Overview · Processing channels ·
AFT · Pay-to-card · Currency accounts · Payout schedules · Routing · Value-added services ·
Intelligent acceptance · RTAU · Network tokens. Then detail sections for specific questions:
Pay-in profiles · Payout instrument · Webhooks · Reporting profiles · Schemes · Validating a
payload · What this does not cover.

**Default test cards.** The *Validating a payload* section states which cards to use when
generating an example payload — Visa `4242424242424242` and Mastercard `5436031030606378`,
both 03/30, CVV 211 and 222 — with a precedence rule: a card the user supplies wins, then a
card matching a named scenario pulled from `checkout-mcp-sandbox`, then these. Defined once as
`llm_bundle.TEST_CARDS` and rendered into both output tiers so they cannot diverge.

### The two-tier pack (`INDEX.md` + `sections/*.md`)

Also produced. A small always-in-context "card" (~1,800–2,000 tokens) plus 12 section files
and a glossary read on demand, ~6,400–9,500 tokens in total depending on the entity. This is the better shape **when the consumer can read files**
— a repo with Claude Code, or a Claude Project with uploaded files. It does not work pasted,
because there is no filesystem to route to; use `project-instructions.md` for that.

> **`sections/` is a superset of `project-instructions.md`.** Overview, AFT, value-added
> services and reporting profiles used to exist *only* in the pasted document, so a consumer
> of the two-tier pack had to read both variants and merge them — and where the two disagreed,
> that merge silently picked a winner. Both tiers now render from the same functions, with
> `_promote`/`_fm` adding a section file's H1 and front matter and `_nofm` stripping them again
> for the pasted document. The round trip is byte-identical, so **the two tiers cannot state
> different facts.** Read either one; never reconcile them.

Every pack is a **point-in-time snapshot** with an id, a timestamp and per-section volatility
ratings (taken from provenance, not hardcoded). Output is deterministically ordered, so two
snapshots of the same merchant diff cleanly.

One wrinkle if you put a pack in a repo: rule 7 of `project-instructions.md` says "there are
no companion files, do not list directories". That is correct for a pasted document and wrong
next to a `sections/` tree. Use one delivery mode per consumer.

---

## Where the configuration comes from

Six sources. The five config services each degrade independently — one being unreachable marks
only its own section `unavailable` rather than failing the run.

| Source | Scope | Auth | Sandbox base | Production base |
|---|---|---|---|---|
| CAT | client + entity | CAT bearer | `client-admin.cko-sbox.ckotech.co/api` | `client-admin.cko-prod.ckotech.co/api` |
| Reporting profiles (merlin) | **entity** | CAT bearer | `merlin-alb.sbox.internal/reporting-profiles-config-api` | `merlin-alb.prod.internal/…` |
| Network tokens (nt-portal) | **client**, inherited | CAT bearer | `nt-portal.sbox.checkout.internal/vault-nt-portal` | `nt-portal.prod.checkout.internal/…` |
| Intelligent Acceptance | **client**, inherited | CAT bearer | `pp-tenet-int.sbox.internal/tenet-config-controller/cat-api` | `pp-tenet-int.prod.internal/…` |
| Real Time Account Updater | **client**, inherited | CAT bearer | `rtau.sbox.checkout.internal/vault-rtau-portal` | `rtau.prod.checkout.internal/…` |
| Public API | client | **secret key** | `api.sandbox.checkout.com` | `api.checkout.com` — webhooks/workflows only |

Paths are identical in both environments; only the host changes. The table of record is
`cat_profile.ENVIRONMENTS`. Every call made in one run uses one environment's row, and every
GET is reported to the UI's call log with its service label.

Client-level inheritance was **measured**, not assumed: IA, network tokens and RTAU come back
byte-identical across entities, while channels, currency accounts and reporting profiles all
differ per entity.

All hosts except the public API resolve to private addresses and are reachable only on the
corporate VPN. Off VPN a call gets no HTTP response at all, which the UI reports as such.

### CAT API reference, pagination and failure diagnosis

The CAT swagger is served by every CAT environment at `/api/swagger/v1/swagger.json` — e.g.
`https://client-admin.cko-qa.ckotech.co/api/swagger/v1/swagger.json` (VPN). One contract for all
environments: identical paths and schemas, only the host and the token change. Its `servers`
list names `client-admin-prod.ckotech.co` as Prod; that name does not resolve — production is
`client-admin.cko-prod.ckotech.co` (verified: it serves the same swagger and real data).

**Collections are paged at 25** (`limit`, `skip`, `total_count`), and production clients
routinely exceed a page. `cat_profile._get_paged` follows `total_count` for entities,
processing channels, processing profiles, currency accounts, both routing-rule lists,
sessions channels and payout settings, merging pages into the first page's raw shape so
`normalize` is unchanged. A response without `total_count` is returned as-is.

**Failure diagnosis** (`cat_profile.list_entities_diag`, surfaced verbatim in the UI):

| Symptom | Cause |
|---|---|
| No HTTP status at all | wrong hostname or not on the VPN — the token was never evaluated |
| 401 | token expired, or minted by the other environment's Okta app (the message shows the token's `cid`) |
| 404 | client id does not exist on that host — check the id and the selected mode |
| 200, empty | the client genuinely has no entities |

Tokens are Okta access tokens; sandbox and production use different Okta apps, so a token is
only ever valid for one environment. Decode the payload and read `cid` to tell which.

Quirk worth knowing: **RTAU returns `415` on a `GET` unless `Content-Type: application/json`
is sent**, despite a GET having no body. Confirmed in both environments.

Why nt-portal, pp-tenet-int and rtau exist separately: CAT has its own endpoints for these,
but they return **form definitions with every value null**. The specialist services are the
only readable source of the actual settings.

### Where endpoint mappings and definitions live

| Layer | Location |
|---|---|
| Design intent, endpoint → section (prose) | `cat-api/source-map.md` |
| The calls actually made | `cat_profile.fetch_all()` |
| Raw response → profile section | `SECTION_DEPS` in `cat_profile.normalize()` |
| Output field definitions | `schema/merchant-profile.schema.json` |
| Profile section → output file | `SEC_OF` in `llm_bundle.render_llm_bundle()` |
| Id → output file | `lookup.json`, generated per pack |

`source-map.md` is documentation and can drift; `fetch_all` is the truth.

---

## Design principles

- **Never fabricate a config value.** If a source does not expose something, the answer is
  "unknown". Every bug that mattered came from a plausible-looking value that was not read
  from anything: `bool(net_tokens)` reported network tokens as enabled for every merchant;
  `entity_id` was stamped onto currency accounts that had none; `processing_urls` was
  classified unreadable when the GET returns it. A confident wrong answer is worse than a gap.
- **Never assert a gap either.** The mirror of the above, and it bit twice. The *What this
  does not cover* table used to hardcode rows for the network-token provisioning mode and the
  money-send classification of FT codes — both of which the document states a few sections
  earlier. Since that table's closing line converts every row into "answer unknown", a false
  row made the document contradict itself and suppress facts it had already reported. Rows
  there are now derived, never asserted.
- **Verify against live data, not `samples/`.** Those are a different entity and stale.
  Previewing from them produced two wrong conclusions about field scoping.
- **Facts are entity-scoped, even in the client document.** One client can hold several legal
  entities with genuinely different capabilities. Pay-to-card is an *entity*-level capability —
  never answer it per channel. Reporting profiles are per entity. IA, network tokens and RTAU
  are per client. The Client Markdown document puts several entities in one paste but keeps
  each in its own section and tells the reader to resolve the entity before answering; it
  never merges two entities' values into one fact.
- **Capabilities are derived, not read.** CAT exposes building blocks, not answers. AFT on a
  channel requires joining processors to profiles on acquirer + scheme + MCC. A pay-in profile
  carrying an AFT code *is* AFT-enabled — Visa's code is the BAI (`custom_settings.aft`),
  Mastercard's is the Payment Transaction Type Identifier, TTI
  (`custom_settings.transaction_type_identifier`); the two are equivalents and the documents
  name whichever applies. Pay-to-card means `processing_type=payout` profiles with
  `status=Active`.
- **Rule out the wrong reasoning, not just the wrong answer.** Saying "never answer this per
  channel" was not enough to stop a reading session from applying the AFT acquirer+scheme+MCC
  join to a *payout* profile and reporting a false MCC mismatch. The Pay-to-card section now
  states the negative directly: a payout profile is not bound to a channel, that join is
  pay-in only, and a differing channel MCC is not a mismatch.
- **Distinguish "no" from "we didn't look."** Six states: `complete`, `partial`, `empty`,
  `unavailable`, `not_collected`, `excluded`. Only `empty` means no; the rest mean **unknown**.
  An absent capability flag is a gap, never a negative.
- **Config and docs are a join, not two silos.** Config values *select which documented rules
  apply* — funds transfer type decides whether a `sender` block is required, country of
  incorporation decides whether `billing_address` is mandatory. Config first, then the rules
  those values trigger.
- **Network Tokens, Intelligent Acceptance and RTAU are distinct value-added services.**
  Separate products, separate services, separate config. Never present them as facets of one
  thing; "value-added services" is only ever an *index* pointing at each service's own section.
- **Don't aggregate away a difference.** A union presented as one fact hides real config: the
  pay-to-card summary said four destination countries, but Visa PTC reaches AE and Mastercard
  PTC does not. Show per-profile values alongside any summary.
- **One model, several renders — and one renderer per fact.** JSON is the source of truth;
  everything else is a projection. Two projections must never contain the same fact rendered
  by different code, because then they can disagree and a consumer has to arbitrate. Where the
  pasted document and the section files overlap, they call the *same* function; the only
  difference is front matter and heading level.

### Terminology the documents use — and avoid

The wording in generated documents is deliberate; a reading model repeats whatever label it is
given, so a wrong label becomes a wrong answer. Keep to these:

| Say | Not | Why |
|---|---|---|
| **CAID (MID)** | CAIC | CAT's field is `card_acceptor_identification_code`; merchants and schemes call it the CAID or MID. "CAIC" was an internal abbreviation and has been removed everywhere. |
| **AFT code — BAI (Visa) / TTI (Mastercard)** | "BAI" for all schemes | Mastercard AFT profiles carry a Payment Transaction Type Identifier, not a BAI. Same role, different name. |
| **Use case** (for an AFT code) | Category / money transfer | The money-transfer split and its `sender` rule belong to pay-to-card funds transfer types only. |
| **Origination countries** and **destination countries** | corridor(s) | Two distinct per-profile lists: where a payout can be funded from, and where it can be sent to. "Corridor" is not Checkout terminology and blurred the distinction. |
| **Funds transfer type** (payout profile) | BAI | Different field, different rules; see the AFT note above. |

### CAID (MID) on processing profiles

`card_acceptor_identification_code` — the **CAID**, which merchants call the **MID** — is the
identifier a scheme sees for a processing profile. CAT sets it per MCC inside the profile's
`business_settings`, so a profile can carry several MCC ↔ CAID pairs. The profile keeps every
pair (`acceptor_ids`) and the distinct code list (`card_acceptor_identification_codes`); the
pay-in, AFT and pay-to-card tables show a **CAID (MID)** column, profiles with more than one
pair get a per-pair table so the pairing is never lost, `lookup.json` routes `caid:<code>` to
the right section, and the documents instruct the reader to state CAID(s) and MCC(s) in any
answer about a profile. Acceptor legal and trade names are captured alongside.

### Funds transfer type categories

`cat_profile.FT_CATEGORIES` maps the 14 Visa / Mastercard Send funds-transfer codes to their
category, so the pack can state whether a **pay-to-card** code is a **money transfer** (and
therefore requires a `sender` block) rather than telling the reader to look it up. It is a
**three-way** classification, and it is a **payout rule only**:

| Category | Codes | `sender` required |
|---|---|---|
| money transfer | `AA` `C07` `C52` `FT` `LA` `PP` `WT` | ✅ yes |
| non-money transfer | `C55` `C65` `FD` `LO` `PD` | ❌ no |
| online gambling | `OG` `C04` | ❌ no |

`requires_sender` is true only for money transfer, so going by that flag alone collapses the
last two rows — which is why the category stays three-way. Sourced from the Checkout.com card
payouts docs, hardcoded because the Checkout MCP could not return the table (its search only
ever yields the section's opening excerpt, and the docs page is JS-rendered). Unrecognised
codes are never defaulted to a category. If Checkout adds a code, this map needs updating by
hand.

**AFTs are different.** A pay-in profile's BAI (Visa) or TTI (Mastercard) identifies the AFT
*use case* and must be valid for the MCC — it does **not** decide whether `sender` or any other
field is required. AFT sender/recipient requirements are driven by scheme, transaction
jurisdiction (domestic vs cross-border) and geography; the source is the docs page *Perform an
account funding transaction*
(`https://www.checkout.com/docs/payments/manage-payments/perform-an-account-funding-transaction`),
which the Checkout MCP can retrieve. The documents therefore show
an AFT code with a *Use case* label only (taken from this table where the code is listed), never
a money-transfer category or a `sender` verdict, and they say so explicitly next to every AFT
table and in the payload-validation rows. Mastercard AFT TTIs such as `P71` are not in the table
and render as "use case not listed in this document — the code is real config": not a
misconfiguration, not "not AFT".

---

## Known gaps

| Topic | State |
|---|---|
| Velocity limits | Not exposed by the CAT API |
| AFT destination / recipient countries | Do not exist on a pay-in AFT profile — origination and destination country lists live only on payout profiles. Verified across every profile on the client. |
| Pay-to-card origination / destination countries per FT type | Not from CAT `pay-to-card-schemes` (503) — read from payout profile `custom_settings` instead, one FT type per profile. **Origination** (funded from) and **destination** (sent to) are two distinct lists and are always reported separately; the word "corridor" is not Checkout terminology and is not used. |
| Payout cron timezone | The schedule carries no timezone **as read today** — but see the note below; this may be a gap in `normalize` rather than in CAT |
| Settlement threshold / balance minimum units | Raw numbers with no currency or minor/major-unit indicator |
| Mastercard AFT TTI use cases | `FT_CATEGORIES` covers payout funds-transfer-type codes; Mastercard AFT identifiers (e.g. `P71`) render as AFT-enabled with the use case unlisted |
| Pricing | Excluded — commercially sensitive |
| Bank account numbers | Redacted **by this app, not by CAT** — `cat_profile.SENSITIVE` strips them and records `redacted_fields`. CAT returns them in full. |

Reporting profiles and the network token provisioning mode **used to be** listed here. Both are
readable — from merlin and nt-portal respectively — and both are now reported.

**Routing rule scope.** A rule's `allow_any_*` flags say *whether* each dimension is
restricted; sibling fields say *to what* — the list item carries `processing_channel_name`
when `allow_any_processing_channel` is false and `processing_currency_count` when the currency
is scoped, and the detail endpoint can add arrays such as `event_types`. `normalize` used to
keep only the flags, so a rule bound to the BLIK channel rendered as "restricted by processing
channel" with the channel never named. It now keeps every dimension's stated values in
`scope` (resolving channel names to this entity's `pc_*` ids where the name is unique), and
the routing tables print them. Where the record carries only a count, the document says so
rather than inventing values. Confirmed from a real production detail: the detail names the
values as plural arrays (`processing_currencies: ["PLN"]`) and adds the currency-account *ids*
where the list gives *names*, so the merged rule carries both. The same array pattern is
expected for `event_types`, `regions`, `card_types`, `processing_channels`,
`merchant_category_codes`, `banking_partners` and `payment_methods`; the capture matches on
the dimension stem, so it needs no per-field code.

**One known bug, not a gap.** Data arrives and is dropped:
- **Payout schedule timezone.** `cat_profile` reads no schedule timezone at all — only the
  entity's own `timezone`. A newer CAT payout-settings response appears to carry
  `schedule_expression_timezone`; if so, the document's "carries no timezone" line is wrong.
  Verify which field it is before fixing, and do not confuse it with the entity timezone.

---

## CLI

Same engine, no browser. Writes `samples/<entity_id>/`.

```bash
BASE_URL=https://client-admin.cko-sbox.ckotech.co/api \
TOKEN=<cat-bearer> CLIENT_ID=cli_… [ENTITY_ID=ent_…] \
python3 cat-api/generate_profile.py
```

`ENTITY_ID` unset processes every entity under the client. Profiles are validated against the
schema and failures printed.

Rebuild from saved responses, no network:

```bash
python3 cat-api/generate_profile.py --offline cat-api/responses
```

> **Caveat:** the cached responses in `cat-api/responses/` are v1-fidelity and lack
> `custom_settings`, so offline runs cannot determine AFT state. The CLI prints `!! DEGRADED`.
> Do not treat an offline pack as authoritative — and note the pack itself carries no trace of
> having been degraded (see `TODO.md`).

---

## Layout

```
TODO.md                # open work, priorities, API quirks — read first
app/
  server.py            # stdlib HTTP server, port 8787; streams /api/generate progress; /api/client-doc
  index.html           # front end: mode switch, progress + call log, 4 tabs
  favicon.svg          # tab icon
  cat_profile.py       # fetch (ENVIRONMENTS, paging, diagnostics) + normalise; render_md / render_llms
  llm_bundle.py        # renders project-instructions.md, the client document and the two-tier pack
  dev-creds.example.json   # template for the prefill file
  dev-creds.json       # SANDBOX-ONLY prefill — gitignored, create from the example
schema/
  merchant-profile.schema.json   # JSON Schema draft 2020-12, v0.1.0
cat-api/
  generate_profile.py  # CLI
  source-map.md        # endpoint -> schema field mapping
  responses/           # cached CAT responses (v1 fidelity — see caveat)
  fixtures/            # captured responses from the four non-CAT services
samples/<entity_id>/   # generated output
```

### `cat-api/fixtures/`

Live responses captured 2026-08-04 from the four non-CAT services, kept because those hosts
are unreachable off the corporate network and the token to refetch them expires hourly.
**Not read by any code path** — they exist so the four parsers can be exercised without a
token or network, and its README documents six response-shape traps that each caused a real
bug. They are the obvious input for the golden-file test in `TODO.md`.

---

## Credentials

`app/dev-creds.json` holds a **sandbox-only** Client ID and SK for prefill convenience.
It is **gitignored**: copy `app/dev-creds.example.json` to `app/dev-creds.json` and fill it in.
Without it the form fields simply start empty. Never put production keys or a CAT bearer
token in it — the token is short-lived and always pasted at run time.

This repo also contains real sandbox merchant configuration under `samples/`,
`cat-api/responses/` and `cat-api/fixtures/`. **Keep it private.**
