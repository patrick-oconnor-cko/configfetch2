# Fixtures — the four non-CAT config services

Live responses captured 2026-08-04 for `cli_scna7ew7mxdenl3h36zlmkyh6m`. Kept because these
services sit on internal hosts (`10.69.x.x`) and are unreachable off the corporate network, and
because the CAT bearer token needed to refetch them expires hourly.

Distinct from `../responses/`, which caches **CAT** responses at v1 fidelity and is what
`generate_profile.py --offline` reads. These are not read by any code path — they exist so the
parsers can be exercised without a token or network.

| File | Source | Parser | Scope |
|---|---|---|---|
| `nt-config.json` | `nt-portal.sbox.checkout.internal/vault-nt-portal/cat/configurations/{clientId}` | `parse_nt_config` | client |
| `ia-config.json` | `pp-tenet-int.sbox.internal/tenet-config-controller/cat-api/clients/{clientId}/form` | `parse_ia_config` | client |
| `rtau-config.json` | `rtau.sbox.checkout.internal/vault-rtau-portal/cat/configurations/{clientId}/form` | `parse_rtau_config` | client |
| `reporting-profiles.json` | `merlin-alb.sbox.internal/reporting-profiles-config-api/reporting-profiles/table/{entityId}` | `parse_reporting_table` | **entity** (`ent_q7qxjp2ctv67yejt2wjmawuu5q`) |

## Response-shape traps these capture

These are UI form/table models, not resource representations. Each one has a quirk that
produced a real bug:

- **`form_section` is set to `null` on every ordinary field in `rtau-config.json`.** Walking
  the tree with `if "form_section" in field` therefore treats every field as a section and
  yields nothing. Must be a truthy check. `nt-config.json` and `ia-config.json` omit the key
  instead, so the bug only shows on RTAU.
- **`plainText` fields carry their content in `default_value`, with `value: null`.** That is
  where the Intelligent Acceptance strategy and addon descriptions live. But for an *input*
  control, `default_value` is a fallback and must never be reported as configuration — NT's
  `default_provision_mode` defaults to `async` while the merchant's real value is `sync`.
  Branch on `display_style`.
- **`ia-config.json` carries a full field family for every strategy at once** —
  `description_<s>`, `addons_enabled_<s>`, `addons_<s>`, `addons_description_<s>` for all four.
  Only the active strategy's family is in force; the rest is dormant UI state.
- **`rtau-config.json` repeats `schemes.scheme_merchant_id`** under both Mastercard and Visa.
  Flattening into one name→field map silently collapses them, so parse per section.
- **`reporting-profiles.json` is a table model** — `schema.table.rows[].columns[]` of
  `{name, value}` — with pagination at `schema.pagination`, not a list of resources.
- **RTAU returns `415` on a GET** unless `Content-Type: application/json` is sent.

## Suggested use

A golden-file test: feed each fixture to its parser and assert the parsed output. That would
have caught the `form_section` bug, and it needs no token and no network. See `TODO.md` item 5.
