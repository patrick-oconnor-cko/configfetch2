# TODO

Open work, in priority order.

---

## 1. Retest the answer-format rule

The generated document carries an **answer-format rule**: for a general overview question,
reproduce the named tables *as tables*, in the document's own order, skip the six detail
sections, and never mention another entity. It has **not been tested end to end**.

You don't need a token for this — `samples/ent_q7qxjp2ctv67yejt2wjmawuu5q/project-instructions.md`
is current renderer output. Paste it into the project instructions of a fresh Claude session
with `checkout-mcp-sandbox` enabled and run four questions:

1. general overview of the entity's configuration
2. how am I configured for AFT
3. how am I configured for pay-to-card
4. validate this payload against my config and the CKO docs

What to check:

- **Q1** — tables reproduced as tables, in the stated order, per-channel detail blocks and the
  six skip-list sections actually skipped, no sibling entity mentioned, prose confined to a few
  lines *after* the tables.
- **Q3** — does it keep Visa PTC's four destination countries separate from Mastercard PTC's
  three, or collapse them into the union?
- **Q4** — config-specific findings, not just schema-shape validation. Did it call
  `checkout-mcp-sandbox` for the request schema?

Whichever reads worst tells you what to fix. Don't restructure on spec.

**Known wrinkle to confirm or dismiss:** the overview rule says "work straight down the
document", but *Pay-in processing profiles* sits between AFT and Pay-to-card, and *Payout
instrument* between Payout schedules and Routing. Both are on the skip list, so working straight
down means stepping over two sections the rule implies aren't in the way.

---

## 2. Fix two known bugs where data arrives and is dropped

Both were found while working on something else, and both make the document state something
false rather than incomplete — which is worse than a gap.

**Routing rule event types.** The document says "specific event types (not listed on the
record)". CAT does list them — the rule *detail* endpoint returns the full array, and a
separate capture read all 14 chargeback events from it. `fetch_all` already fetches that detail
(`cat_profile.py`, the `/payment-routing-rules/{id}` call), but `normalize` keeps only the
`allow_any_*` flags in `conditions` and drops `event_types`, so the renderer's fallback always
fires. Carry the array through and render it.

**Payout schedule timezone.** `cat_profile` reads no schedule timezone at all — the only
timezone fields are entity-level. A newer CAT payout-settings response appears to carry
`schedule_expression_timezone` inside `schedule_trigger_rules`. If so, the document's "the cron
carries no timezone, so the wall-clock fire time is unknown" line is wrong.

**Verify which field it actually is before changing anything** — the entity's own `timezone` is
also `Europe/London` on the reference entity, so it is easy to mistake one for the other and
introduce a wrong fact while trying to fix a wrong fact.

---

## 3. Restructure for fast overview answers

**Do item 1 first — the answer-format rule may already have solved this.**

Measured baseline: UK LTD `project-instructions.md` ~6,700 tokens; the two-tier pack ~8,500
with a ~1,750-token index. Summary content is ~600 of the paste document; deep detail
~4,400–6,000; instructions ~1,080. A high-level answer needs ~10% of the document and the other
90% competes for attention.

Biggest blocks: `Intelligent acceptance` ~712 (mostly the 19 unselected addons), `RTAU` ~545,
and per-channel detail on multi-channel entities.

Key constraint: pasted as project instructions the whole document is in context every turn, so
this is **not** an I/O problem. The problems are (a) finding the right lines, (b) aggregating
scattered facts for a summary, (c) nothing telling the model to skip detail.

Remaining ideas, if item 1 shows they're still needed:

- Hoist every summary table into one "At a glance" block above a hard detail divider.
- Denormalise derived observations the model currently has to compute — e.g. "GBP-only across
  acceptance and settlement", "cards only, no Amex/APMs", "AFT is Visa-only because 1 of 4
  pay-in profiles carries a BAI".
- One capability matrix (capability x scope x verdict) replacing AFT / 3DS / pay-to-card /
  network-token verdicts scattered across four places at three scopes.
- Move rarely-needed detail to a labelled appendix: the 19 unselected IA addons, the
  34-event webhook list, the glossary.

**Do not trim for size alone.** Several of the highest-value additions are caveats that prevent
confident wrong answers: the forex agreement, "blank != not registered" (RTAU statuses), "off is
a real negative" (IA addons), the units warning (settlement threshold/balance_minimum), and the
network-token `allowed=false` vs `provisioning=true` contradiction. Move them next to the values
they qualify; don't shorten them.

---

## 4. Design spike: expose this as an MCP server

Core shift: today is *push* (generate a point-in-time document, paste it, so everything must be
in context always). An MCP makes it *pull*. That deletes much of the apparatus that exists only
because the document must be self-sufficient.

Tool surface — keep small, every description is permanent context:

```
list_entities(client_id)
get_config(client_id, entity_id, sections=[...])   # workhorse; beats 10 separate getters
validate_card_payout(client_id, entity_id, payload)
classify_funds_transfer_type(code)
render_config_document(client_id, entity_id)       # keeps the paste/email/ticket artifact
```

**Return pre-rendered markdown, not raw JSON.** The failure this project keeps hitting is a
model paraphrasing well-structured source into prose. Returning JSON reintroduces it in full;
returning the exact markdown table makes pass-through the cheapest path.

`get_config`'s `sections` enum is the 12 section names emitted by `render_llm_bundle` — and
because `sections/` is now a superset of the pasted document, this is a dict lookup rather than
new rendering work.

Three hard problems:

1. **Auth is the blocker — resolve before writing code.** The CAT token is a ~1h Okta bearer.
   An env var goes stale hourly; a token parameter puts credentials in conversation context.
   Either the server runs its own OAuth device flow and caches, or accept a `set_token` tool
   called hourly. This decides whether the result is better or worse than today.
2. **Network reach** — four of six sources are internal (`10.69.x.x`), so v1 is local stdio on
   the laptop, not a hosted service. Each user runs their own.
3. **Latency** — a full fetch is ~24 CAT calls plus four services, 8–15s. Needs an in-memory
   TTL cache keyed by `(client_id, entity_id)` and a `refresh=true` escape. Staleness returns,
   but at minutes rather than days.

Runtime note: the default `python3` here is Apple's 3.9, and the official `mcp` SDK needs 3.10+.
Either hand-write the JSON-RPC stdio loop (~250 lines, zero dependencies, keeps "3.9+ and
nothing else" true) or stand up a venv on a newer interpreter.

Best-value tool: **`validate_card_payout`**. The config half is deterministic server-side — is
this FT type on an Active payout profile, does `source.id` exist and its currency match, is
`processing_channel_id` present (any Active channel is valid), is the destination within *that
profile's* corridor, is `sender` required per the FT category, is `billing_address` required per
incorporation, is `purpose` required per destination country. Return findings; no model
judgement on the mechanical half.

**Do not put CKO docs in this server** — `checkout-mcp-sandbox` already does that. Two servers
compose: config from ours, schemas from theirs.

What survives untouched: all the derived logic, which is the actual value. `cat_profile.py` and
the `llm_bundle` section renderers stay as-is; the MCP is a thin transport (~300 new lines).
Keep the web app for eyeballing a full config and producing the artifact.

---

## 5. Smaller items

- **No tests.** Every bug found so far surfaced as a live 422 or a wrong rendering, not from
  anything automated. Two cheap wins:
  - A **golden-file test over `cat-api/fixtures/`** — four captured responses, four parsers
    (`parse_nt_config`, `parse_ia_config`, `parse_rtau_config`, `parse_reporting_table`), no
    token and no network. The fixtures README documents six response-shape traps that each
    caused a real bug; this would have caught the `form_section` one.
  - A **golden-file test over the renderers** — render from a saved `merchant-profile.json` and
    diff against committed expected output. Today that check is done by hand.
- **Schema not enforced.** `schema/merchant-profile.schema.json` has no
  `additionalProperties: false` and only five required sections, so it validates by accident.
  Roughly ten newer field groups aren't formalised. Tightening it turns silent upstream drift
  into a loud failure.
- **Degraded generation isn't recorded in the artifact.** `cat-api/generate_profile.py --offline`
  prints `!! DEGRADED` to the terminal, but the pack itself carries no trace. Hand that pack to
  an LLM and it states AFT verdicts derived from fields that were never present. The fidelity
  flag belongs in the envelope and on the document.
- **Glossary duplication.** `glossary.md` is the largest bundle file (~1,760 tokens) and only
  ~30 of 131 lines differ between two entities — ~77% is boilerplate regenerated per merchant.
- **Rule 7 vs the two-tier pack.** `project-instructions.md` rule 7 says "there are no companion
  files, do not list directories". Correct when pasted, wrong beside a `sections/` tree. Decide
  whether to make it conditional on delivery mode.
- **`checkout_legal_entity_code` on payout profiles** renders as `—`. It is in the raw v2
  response but `normalize` doesn't carry it to the profile rows.

---

## Notes worth keeping

**Six sources.** Five config services all accepting the same CAT bearer token, each degrading
independently, plus the public API on the secret key for webhooks/workflows.

| Source | Scope | Base |
|---|---|---|
| CAT | client + entity | `client-admin.cko-sbox.ckotech.co/api` |
| Reporting profiles | **entity** | `merlin-alb.sbox.internal/reporting-profiles-config-api` |
| Network tokens | **client** (inherited) | `nt-portal.sbox.checkout.internal/vault-nt-portal` |
| Intelligent Acceptance | **client** (inherited) | `pp-tenet-int.sbox.internal/tenet-config-controller` |
| RTAU | **client** (inherited) | `rtau.sbox.checkout.internal/vault-rtau-portal` |
| Public API (workflows) | client | `api.sandbox.checkout.com` — **secret key**, not the CAT token |

Client-level inheritance was **measured**, not assumed: IA, NT and RTAU come back byte-identical
across two entities, while channels (1 vs 5), currency accounts (3 vs 4) and reporting profiles
(same count, different names) all differ.

**RTAU returns 415 on a GET unless `Content-Type: application/json` is sent**, despite a GET
having no body. The other services don't need it.

**CAT's own endpoints for NT / IA / RTAU return form definitions with null values.** The
specialist services are the only readable source of the actual settings — which is also why
their parsers are the fiddliest code here.

**Network Tokens, Intelligent Acceptance and RTAU are distinct value-added services** — separate
products, separate services, separate configuration. Never model or present them as facets of
one thing. "Value-added services" is only ever an *index* of which services are on, pointing at
each service's own section.
