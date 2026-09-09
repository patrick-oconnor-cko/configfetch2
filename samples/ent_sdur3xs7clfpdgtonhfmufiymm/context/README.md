# Merchant configuration context pack — PTOC SA

Entity `ent_sdur3xs7clfpdgtonhfmufiymm` (incorporated SA) · client PTOC Sandbox `cli_scna7ew7mxdenl3h36zlmkyh6m`

Snapshot `snap_20260729T1939·sdur3xs7` · generated 2026-07-29T19:39:44Z ·
environment sandbox · ~4862 tokens total.

This is a **point-in-time** export of one entity's Checkout.com configuration,
formatted so an LLM can find an answer without reading everything.

## How to use it

**Claude Code / a repo** (best — native progressive disclosure)
1. Copy this folder into your repo, e.g. `merchant-context/`.
2. Append the contents of `INDEX.md` to your `CLAUDE.md`, or reference the folder
   from it. The card stays in context; sections are read on demand.

**Claude Project**
1. Paste `INDEX.md` into the project instructions.
2. Upload `sections/*.md` and `glossary.md` as project files.

**Single paste (degraded)**
Use `llms.txt` from the app instead. Everything lands in context every turn, so
routing does not apply — only use this where multi-file is impossible.

## Rules the pack asserts
* Authoritative for configuration; overrides documented defaults.
* A missing fact means **unknown** — never inferred from documentation.
* Field names, enums and scheme rules come from Checkout.com docs via MCP — never invented here.
* Payload questions are a **join**: config values select which documented rules apply, so
  read config first, then look up the rules those values trigger. Neither source alone
  answers "is my request right?"
* Bank account numbers are redacted.

Regenerate from the app when config may have changed; high-volatility sections
(routing, webhooks) drift fastest.
