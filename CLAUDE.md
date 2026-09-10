# Project instructions

Generates a per-merchant Checkout.com configuration document for an LLM. See
[README.md](README.md) for how it works and [TODO.md](TODO.md) for open work — **read TODO.md
before starting anything substantial**; it carries current priorities and several API quirks
that are expensive to rediscover.

**This application is read-only.** Every call it makes is a `GET`. Do not add a write path.

## Working rules

**Never fabricate a config value.** If a source doesn't expose something, the answer is
"unknown" — not a plausible default. Every bug that mattered here came from a value that
looked read but wasn't: `bool(net_tokens)` reported network tokens enabled for every merchant;
`entity_id` was stamped onto currency accounts that carry none; `processing_urls` was called
unreadable when the GET returns it. Prefer a stated gap over a confident guess.

**Never assert a gap either.** A hardcoded "not available" row is as damaging as a fabricated
value, because the generated document converts every such row into an "answer unknown"
instruction — which once made it suppress facts it had printed three sections earlier. Rows in
*What this does not cover* must be derived from what was actually read.

**Verify against live data or a payload the user pastes — not `samples/`.** Those files are a
different entity and stale. Previewing from them produced two wrong conclusions about field
scoping. If a question is "is this correctly scoped?", only live data answers it.

**Don't conclude from a truncated dump.** Several wrong calls came from printing the first 400
characters of an object and inferring a field was absent. Print all keys, or say you haven't
checked.

**Restart the server after any renderer change.** `server.py` imports `cat_profile` and
`llm_bundle` once and Python caches modules, so edits appear to have no effect until restart.
This has repeatedly looked like a bug in the code.

**Don't start the server yourself** — Patrick runs it. Give the command:
`python3 app/server.py`

**Commit only when asked.** Work locally; don't prompt for it.

## Domain facts that are easy to get wrong

- **Scope differs per capability.** Pay-to-card, reporting profiles, currency accounts, routing
  and settlement are **entity**-level. Intelligent Acceptance, Network Tokens and RTAU are
  **client**-level and inherited by every entity. Webhooks/workflows are **client**-level. Card
  acceptance, AFT and 3DS are **channel**-level.
- **Network Tokens, Intelligent Acceptance and RTAU are three distinct value-added services** —
  separate products, separate config services. Never model or present them as facets of one
  thing.
- **A pay-in processing profile carrying an AFT code is AFT-enabled.** That is the definition.
  The code's name is scheme-specific: Visa's is the **Business Application Identifier (BAI)**
  at `custom_settings.aft.business_application_identifier`; Mastercard's is the **Payment
  Transaction Type Identifier (TTI)** at `custom_settings.transaction_type_identifier`. They
  are equivalents — a question about either is a question about the AFT code. Verified on
  live production profiles (Visa: BAI only; Mastercard: TTI only, e.g. `P71`). Detecting AFT
  from the BAI alone reported every Mastercard AFT profile as not enabled.
- **Pay-to-card means** processing profiles with `processing_type=payout` and `status=Active`.
  It is never a per-channel capability — but a card payout request still requires a
  `processing_channel_id`, and **any** Active channel on the entity is valid. The
  acquirer+scheme+MCC join applies to pay-in AFT only; a channel MCC differing from a payout
  profile's MCC is **not** a mismatch.
- **Funds transfer types have three categories**, not two: money transfer, non-money transfer,
  online gambling. Only money transfer requires a `sender` block. The map lives in
  `cat_profile.FT_CATEGORIES`.
- **Don't aggregate away a difference.** A union shown as one fact hides real config — the
  pay-to-card summary said four destination countries while Mastercard PTC only reached three.
  Show per-profile values next to any summary.
- **`sections/` is a superset of `project-instructions.md`.** Both tiers render from the same
  functions. Never let a fact exist in one tier rendered by different code than the other.

## Config sources

Six sources, five of them config services sharing one CAT bearer token (short-lived, ~1h — ask
for a fresh one rather than working around an expired one). Each degrades independently; one
failing marks only its own section `unavailable`.

CAT · merlin (reporting profiles) · nt-portal (network tokens) · pp-tenet-int (Intelligent
Acceptance) · rtau (RTAU). Bases are in `cat_profile.py`. All but CAT are on `10.69.x.x` and
need the corporate network. RTAU returns `415` on a GET unless `Content-Type: application/json`
is sent.

The sixth is the **public API** (`api.sandbox.checkout.com`), authenticated with the secret
key rather than the CAT token, used only for webhooks/workflows.

## Documentation lookups

For Checkout API schemas, field names and error codes, use the **`checkout-mcp-sandbox`** MCP
server when working on sandbox output — not `checkout-mcp` (production). The two servers
index different API surfaces. The app has a Sandbox and a Prod mode; generated documents name
the matching server via `llm_bundle._mcp_name`. Its search returns only a section's opening
excerpt, so it cannot retrieve long reference tables.

**Production bases live in `cat_profile.ENVIRONMENTS["production"]`** — all six are set. Change
one only from a verified source, never by deriving a production hostname from the sandbox one;
the CAT swagger's own "Prod" server entry (`client-admin-prod.ckotech.co`) does not resolve.

## Test payloads

When building a test payload or example request, default to these sandbox test cards:

| Scheme | Number | Expiry | CVV |
|---|---|---|---|
| Visa | `4242424242424242` | 03/30 | 211 |
| Mastercard | `5436031030606378` | 03/30 | 222 |

Not real cards. A card the user supplies wins; for a **named scenario** (a specific decline
code, 3DS flow, AVS result, issuer country) pull the matching card from
`checkout-mcp-sandbox` instead. Otherwise use the table above without asking.
