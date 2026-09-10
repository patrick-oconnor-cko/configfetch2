#!/usr/bin/env python3
"""
Render a merchant-profile dict into a static, point-in-time LLM context bundle.

Two tiers:
  INDEX.md        always-loaded card — scope model, can/cannot, what-it-doesn't-know,
                  routing table. Small enough to sit in context permanently.
  sections/*.md   fetched on demand, one per config area, each self-describing via
                  front-matter (they are read in isolation, without the card).

Design rules:
  * Denormalise the answer. Never make an LLM join across sections.
  * Explicit negatives, and a tri-state: a missing `enabled` means NOT DETERMINABLE,
    never "no".
  * Near-global lists collapse to counts + notable includes/excludes.
  * IDs in headings, one fact per line, so `grep pc_xxx` lands somewhere useful.
  * Deterministic output; timestamps only in front-matter, so snapshots diff cleanly.
"""

import re

# Funds transfer type categories. Mirrors cat_profile.FT_CATEGORIES — imported lazily so
# llm_bundle stays usable on a profile dict alone, with a local fallback if unavailable.
def _classify_ft(code):
    try:
        import cat_profile
        return cat_profile.classify_ft(code)
    except Exception:
        return None


def _aft_code(a):
    """(code, indicator) from a profile's `aft` block or a channel's AFT verdict. Visa's
    indicator is the Business Application Identifier (BAI); Mastercard's is the Payment
    Transaction Type Identifier (TTI). Same role, different name — both mean AFT-enabled."""
    a = a or {}
    code = a.get("code") or a.get("aft_code") or a.get("business_application_identifier") or a.get("transaction_type_identifier")
    ind = a.get("indicator") or a.get("aft_indicator") or ("BAI" if a.get("business_application_identifier") else "TTI" if a.get("transaction_type_identifier") else None)
    return code, ind

def _aft_cell(a):
    code, ind = _aft_code(a)
    return f"`{code}` ({ind})" if code and ind else f"`{code}`" if code else "—"

AFT_INDICATOR_NOTE = ("The AFT indicator is scheme-specific: **Visa** calls it the Business Application "
                      "Identifier (**BAI**); **Mastercard** calls it the Payment Transaction Type Identifier "
                      "(**TTI**). They are the same thing under two names — when a question mentions either, "
                      "answer from the code shown here whichever the scheme.")


def est_tokens(s): return max(1, len(s) // 4)


# Default cards for a generated example payload. Sandbox test numbers, not real cards.
# Precedence: a card the user supplies wins; then a card matching a named scenario (a
# specific decline code, 3DS flow, AVS result, issuer country), pulled from the Checkout
# MCP; then these. A generic filler PAN produces findings about the card rather than about
# the config under test, which is the failure this removes.
TEST_CARDS = (
    ("Visa", "4242424242424242", "03/30", "211"),
    ("Mastercard", "5436031030606378", "03/30", "222"),
)


def _test_cards_block(mcp="the Checkout.com docs MCP server", sandbox=True):
    """Test-card defaults for example payloads. Rendered into both tiers.

    Only for a sandbox snapshot: the numbers below are sandbox-only, and a production
    document must not invite anyone to send test — or real — cards at a live account."""
    if not sandbox:
        return ["**Generating an example payload — production snapshot**", "",
                "This document describes a **production** account. Do not run example or "
                "test payloads against it: sandbox test card numbers are not valid on "
                "production, and a real card number would create a live transaction. Build "
                "and test any example request in the sandbox first, then carry over only "
                "the production identifiers from this document (processing channel, "
                "currency account, profile ids) into the live request.",
                ""]
    return ["**Generating an example payload — which card to use**", "",
            _tbl(["Scheme", "Number", "Expiry", "CVV"],
                 [[s, f"`{n}`", e, c] for s, n, e, c in TEST_CARDS]),
            "These are **sandbox test card numbers, not real cards.** Use them for any "
            "example or test payload without asking.",
            "",
            "Two things override them, in this order: a card number, expiry or CVV the "
            f"user supplies, and — for a **named scenario** (a particular decline code, "
            f"3DS flow, AVS result or issuer country) — the matching test card from "
            f"{mcp}. Only reach for that lookup when the scenario is named; otherwise the "
            "table above is the answer.",
            "",
            "Pair the card's scheme with the funds transfer type under test: the schemes "
            "on this merchant's payout profiles carry different FT codes, so swapping the "
            "card without swapping the code introduces a second, unintended finding.",
            ""]

def _fm(**kw):
    out = ["---"]
    for k, v in kw.items():
        if v in (None, "", [], {}): continue
        if isinstance(v, (list, tuple)): v = " · ".join(str(x) for x in v)
        out.append(f"{k}: {v}")
    out.append("---")
    return "\n".join(out)

def _ident(p):
    """Entity-scoped identity for a pack: (entity name, ISO-2 incorporation, qualified snapshot id).

    A pack covers ONE entity, but snapshot_id and identity.client_name are both
    client-wide — using them to label a pack makes every sibling pack identical.
    """
    env = p.get("envelope") or {}
    es = p.get("entity_structure") or {}
    eid = es.get("root_entity_id")
    this = next((e for e in es.get("entities", []) if e.get("entity_id") == eid), {})
    snap = env.get("snapshot_id")
    return (this.get("name") or (p.get("identity") or {}).get("client_name", "?"),
            this.get("country_of_incorporation"),
            f"{snap}·{eid.split('_', 1)[-1][:8]}" if (snap and eid) else snap)


def _prov(p, sec):
    return (p.get(sec) or {}).get("provenance") or {}

def _tbl(cols, rows):
    if not rows: return "_none_\n"
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        out.append("| " + " | ".join("—" if c in (None, "") else str(c) for c in r) + " |")
    return "\n".join(out) + "\n"

def _geo(s, full=None):
    """Country summary. Short lists read better enumerated than summarised."""
    if not s: return "—"
    n = s.get("count", 0)
    if full and n and n <= 12:
        return f"{n} — {', '.join(full)}"
    if n == 1 and (s.get("includes") or []):
        return f"1 — {s['includes'][0]}"
    inc = ", ".join(s.get("includes") or []) or "none of the usual majors"
    g = " (global)" if s.get("is_global") else ""
    miss = f" · not incl. {', '.join(s.get('excludes') or [])}" if s.get("excludes") else ""
    return f"{n} countries{g} · incl. {inc}{miss}"

def _cur(s):
    if not s: return "—"
    absent = s.get("majors_absent") or []
    return f"{s.get('count',0)} currencies" + (f" (missing {', '.join(absent)})" if absent else " (all majors)")

def _verdict(v, yes, no):
    """Tri-state. `enabled` absent => not determinable; never render that as 'no'."""
    if not isinstance(v, dict): return "⚠️ unknown"
    if "enabled" not in v and "applicable" not in v:
        return f"⚠️ {v.get('coverage','unknown')} — {v.get('reason','not determinable')}"
    if v.get("enabled") or v.get("applicable"): return yes(v)
    return no(v)


# ---------------------------------------------------------------- sections

def _sec_entities(p):
    es = p.get("entity_structure") or {}
    pv = _prov(p, "entity_structure")
    rows = [[e.get("name"), f"`{e.get('entity_id')}`", e.get("country_of_incorporation"),
             e.get("type"), e.get("status"), e.get("timezone") or "unknown",
             "✅" if (e.get("capabilities") or {}).get("payments") else ("❌" if e.get("capabilities") else "—"),
             "✅" if (e.get("capabilities") or {}).get("payouts") else ("❌" if e.get("capabilities") else "—")]
            for e in es.get("entities", [])]
    tz = es.get("root_timezone")
    note = ("\n\n**Timezone.** The `Timezone` column is the entity's own IANA timezone, as configured on\n"
            "the entity record. Use it to interpret any wall-clock time in an answer — report cut-offs,\n"
            "statement periods, \"end of day\". It is **not** automatically the timezone of the settlement\n"
            "payout cron; see settlement.md, whose schedule object carries no timezone of its own.\n"
            if tz else
            "\n\n**Timezone.** Not present on the entity record in this snapshot — answer **unknown** for\n"
            "any question that depends on the merchant's local time. Do not assume UTC.\n")
    return (_fm(section="entities", as_of=pv.get("as_of"), coverage=pv.get("coverage"),
                volatility=pv.get("volatility"), sources="/clients/{c}/entities · /entities/{id}")
            + "\n\n# Entity structure\n\n"
            + _tbl(["Entity", "ID", "Incorp.", "Type", "Status", "Timezone", "Payments", "Payouts"], rows)
            + note)

def _sec_channels(p, nm):
    pc = p.get("processing_channels") or {}
    pv = _prov(p, "processing_channels")
    out = [_fm(section="channels", as_of=pv.get("as_of"), coverage=pv.get("coverage"),
               volatility=pv.get("volatility"),
               sources="/entities/{e}/processing-channels · /processing-channels/{id} · /sessions-processing-channels/{id}",
               join="processor.acquirer_id == profile.acquirer_key + scheme + MCC"),
           "", "# Processing channels", ""]
    for ch in pc.get("channels", []):
        out.append(f"### {ch.get('name')} — {ch.get('processing_channel_id')}")
        bits = [f"status {ch.get('status','?')}"]
        if ch.get("business_model_type"): bits.append(f"business model {ch['business_model_type']}")
        if ch.get("services"): bits.append("services " + ", ".join(ch["services"]))
        if ch.get("payment_pricing_profile"): bits.append(f"pricing \"{ch['payment_pricing_profile']}\"")
        out.append(" · ".join(bits))
        f = ch.get("features") or {}
        if f: out.append("features: " + " ".join(f"{k}={v}" for k, v in f.items()))
        if ch.get("schemes_enabled"): out.append("methods: " + ", ".join(ch["schemes_enabled"]))
        if ch.get("mccs"): out.append("MCCs: " + ", ".join(ch["mccs"]))

        out.append("AFT: " + _verdict(ch.get("aft"),
            lambda v: "✅ " + " · ".join(
                f"via {m.get('profile_name')} (`{m.get('profile_id')}`) {m.get('scheme') or ''} "
                f"{_aft_code(m)[1] or 'AFT code'}={_aft_code(m)[0]} · auth hold {m.get('authorization_validity_period')}d · match {m.get('match')}"
                for m in (v.get("matches") or [v])),
            lambda v: f"❌ {v.get('reason','no AFT-capable profile')}"))
        out.append("3DS: " + _verdict(ch.get("three_ds"),
            lambda v: "✅ " + " · ".join(
                f"{s.get('scheme')} {'/'.join(s.get('protocol_versions') or [])}" for s in v.get("schemes", [])),
            lambda v: f"❌ {v.get('reason','not configured')}"))
        p2c = ch.get("pay_to_card") or {}
        out.append(f"pay-to-card capability: **n/a at this level** — {p2c.get('reason','entity-scoped')} "
                   f"→ see pay-to-card.md")
        out.append("  (this is **not** a negative for this channel. A card payout request still "
                   "**requires** a `processing_channel_id`, and this channel is a valid choice — "
                   "capability is entity-scoped, the payload field is not. The channel's own "
                   "scheme/MCC/currency values do not have to match the payout profile's.)")

        rows = [[pr.get("name"), pr.get("acquirer_name") or pr.get("acquirer_id"), pr.get("scheme"),
                 pr.get("merchant_category_code"),
                 (f"{pr['profile_name']} ({pr.get('profile_type')})" if pr.get("profile_name") else None),
                 pr.get("profile_match"), pr.get("authorizations"), pr.get("captures"),
                 pr.get("refunds"), pr.get("voids"), pr.get("gws_only"),
                 _cur(pr.get("processing_currencies_summary"))]
                for pr in ch.get("processors", [])]
        out += ["", _tbl(["Processor", "Acquirer", "Scheme", "MCC", "→ Profile", "Match",
                          "Auth", "Cap", "Ref", "Void", "GWS", "Currencies"], rows)]
    return "\n".join(out)

def _sec_payin(p):
    pp = p.get("processing_profiles") or {}
    pv = _prov(p, "processing_profiles")
    payin = [x for x in pp.get("profiles", []) if x.get("type") == "payin"]
    rows = [[x.get("name"), x.get("scheme"), x.get("acquirer_key"), x.get("acquiring_bin"),
             x.get("merchant_category_code"),
             _aft_cell(x.get("aft")),
             (f"{x['authorization_validity_period']}d" if x.get("authorization_validity_period") is not None else None),
             ("yes" if x.get("is_quasi_cash") else "no"), x.get("acceptance_mode"), x.get("status")]
            for x in payin]
    out = [_fm(section="payin-profiles", as_of=pv.get("as_of"), coverage=pv.get("coverage"),
               volatility=pv.get("volatility"),
               sources="/entities/{e}/processing-profiles · /processing-profiles/v2/{id}"),
           "", "# Pay-in processing profiles", "",
           "Acceptance profiles. AFT profiles carry the AFT code (Visa: BAI; Mastercard: TTI),",
           "the authorization hold, and SCA exemptions. " + AFT_INDICATOR_NOTE, "",
           _tbl(["Name", "Scheme", "Acquirer", "BIN", "MCC", "AFT code", "Auth hold",
                 "Quasi-cash", "Acceptance", "Status"], rows)]
    FL = [("enable_transaction_risk_analysis", "TRA"), ("enable_low_value", "Low value"),
          ("enable_secure_corporate_payment", "Secure corp"), ("enable_3ds_outage", "3DS outage"),
          ("enable_trusted_listing", "Trusted listing"), ("enable_sca_delegation", "SCA delegation")]
    sca = [x for x in payin if x.get("sca_exemptions_settings")]
    if sca:
        out += ["## SCA exemptions", "",
                _tbl(["Profile"] + [l for _, l in FL],
                     [[x.get("name")] + ["✅" if (x["sca_exemptions_settings"] or {}).get(k) else "❌"
                                          for k, _ in FL] for x in sca])]
    m2m = [x for x in payin if (x.get("me_2_me_settings") or {}).get("is_enabled")]
    if m2m:
        out += ["## Merchant-to-merchant", "",
                _tbl(["Profile", "Merchant name", "CAIC"],
                     [[x.get("name"), (x["me_2_me_settings"] or {}).get("merchant_name"),
                       (x["me_2_me_settings"] or {}).get("card_acceptor_identification_code")] for x in m2m])]
    return "\n".join(out)

def _sec_p2c(p):
    mo = p.get("money_out") or {}
    v = mo.get("pay_to_card") or {}
    pv = _prov(p, "money_out")
    out = [_fm(section="pay-to-card", as_of=pv.get("as_of"), coverage=pv.get("coverage"),
               volatility=pv.get("volatility"), scope="entity",
               sources="/entities/{e}/processing-profiles · /processing-profiles/v2/{id}",
               not_covered="per-FT-type corridors (CAT pay-to-card-schemes endpoint returns 503)"),
           "", "# Pay-to-card", "",
           "**Scope: entity-level.** Declared by processing profiles with",
           "`processing_type=payout` and `status=Active`. Processing channels carry no",
           "pay-to-card capability — never answer this question per-channel.", ""]
    if v.get("enabled"):
        out += [f"enabled: **yes**",
                "schemes: " + ", ".join(v.get("enabled_schemes") or []),
                "funds transfer types: " + ", ".join(v.get("ft_types") or []),
                "MCCs: " + ", ".join(v.get("supported_mccs") or []),
                "origination: " + _geo(v.get("origination_summary")),
                "destination: " + _geo(v.get("destination_summary"))]
    else:
        out.append("enabled: **no** — no Active payout processing profiles exist for this entity")
    fx = mo.get("forex") or {}
    if "pay_to_card_forex_enabled" in fx:
        out.append(f"forex: {'enabled' if fx['pay_to_card_forex_enabled'] else 'not configured'}")
    rows = [[x.get("name"), x.get("scheme"), x.get("funds_transfer_type"), x.get("acquiring_bin"),
             x.get("card_acceptor_identification_code"), x.get("merchant_category_code"),
             x.get("acceptance_mode"), x.get("checkout_legal_entity_code"), x.get("status")]
            for x in v.get("processors", [])]
    out += ["", "## Payout profiles (the pay-to-card processors)", "",
            _tbl(["Profile", "Scheme", "FT", "BIN", "CAIC", "MCC", "Acceptance", "Legal entity", "Status"], rows)]
    pr = mo.get("payout_routes") or []
    if pr:
        out += ["## Payout (bank) routes — enabled corridors", "",
                f"{(mo.get('payout_routes_summary') or {}).get('enabled')} enabled of "
                f"{(mo.get('payout_routes_summary') or {}).get('total')} total", "",
                _tbl(["Country", "Currency", "Schemes"],
                     [[r.get("country"), r.get("currency"),
                       ", ".join(f"{s.get('name')}/{s.get('fee_type')}" for s in r.get("schemes") or [])]
                      for r in pr])]
    return "\n".join(out)

def _sec_routing(p, nm):
    rt = p.get("routing") or {}
    pv = _prov(p, "routing")
    out = [_fm(section="routing", as_of=pv.get("as_of"), coverage=pv.get("coverage"),
               volatility=pv.get("volatility"),
               sources="/entities/{e}/{payment,payout}-routing-rules · /{payment,payout}-routing-rules/{id}",
               note="`status` is the real field; there is no `enabled` field on routing rules"),
           "", "# Routing rules", ""]
    for label, key in (("Payment routing", "payment_routing_rules"),
                       ("Payout routing (covers pay-to-card)", "payout_routing_rules")):
        out += [f"## {label}", ""]
        rules = rt.get(key) or []
        if not rules:
            out += ["_no rules_", ""]; continue
        for r in rules:
            out.append(f"### {r.get('rule_id')} — {r.get('status','?')}")
            if r.get("name"): out.append(f"name: {r['name']}")
            if r.get("sub_entity_id"): out.append(f"applies to sub-entities: {r['sub_entity_id']}")
            if "unrestricted" in r:
                out.append("restrictions: **none** — matches all traffic" if r["unrestricted"]
                           else "restrictions: some conditions are scoped (see below)")
            for k, val in (r.get("conditions") or {}).items():
                out.append(f"  {k}: {val}")
            if r.get("source_identifier"): out.append(f"source: {nm(r['source_identifier'])}")
            if r.get("revenue_currency_account_id") or r.get("revenue_currency_account_name"):
                out.append(f"revenue → {r.get('revenue_currency_account_name') or nm(r.get('revenue_currency_account_id'))}"
                           f" (`{r.get('revenue_currency_account_id','—')}`)")
            if r.get("fees_currency_account_id") or r.get("fees_currency_account_name"):
                out.append(f"fees → {r.get('fees_currency_account_name') or nm(r.get('fees_currency_account_id'))}"
                           f" (`{r.get('fees_currency_account_id','—')}`)")
            out.append("")
    return "\n".join(out)

def _sec_settlement(p):
    st = p.get("settlement") or {}
    pv = _prov(p, "settlement")
    out = [_fm(section="settlement", as_of=pv.get("as_of"), coverage=pv.get("coverage"),
               volatility=pv.get("volatility"),
               sources="/entities/{e}/currency-accounts · /entities/{e}/payout-settings/{id}",
               redaction="bank account numbers and bank codes are redacted by policy"),
           "", "# Settlement", "",
           "currencies: " + (", ".join(st.get("settlement_currencies") or []) or "—"), "",
           "## Currency accounts", "",
           _tbl(["Currency account", "Currency", "Status"],
                [[f"`{a.get('currency_account_id')}`", a.get("currency"), a.get("status")]
                 for a in st.get("currency_accounts", [])])]
    for pi in st.get("payout_instructions", []):
        i = pi.get("instrument") or {}
        sch = pi.get("schedule") or {}
        out += [f"## Payout instruction — {pi.get('name') or pi.get('instruction_id')}", "",
                f"instrument: {i.get('instrument_type','?')} in {i.get('currency','?')} · "
                f"holder {i.get('account_holder','?')} · bank {i.get('bank_name','?')}",
                f"redacted: {', '.join(i.get('redacted_fields') or []) or 'none'}"]
        for k, val in sch.items():
            if isinstance(val, list): val = ", ".join(str(x) for x in val)
            out.append(f"  {k}: {val}")
        if sch.get("cron_schedule"):
            tzk = next((k for k in sch if "timezone" in k.lower()), None)
            if tzk:
                out.append(f"  → cron runs in {sch[tzk]} (stated on the schedule)")
            else:
                ez = ((p.get("entity_structure") or {}).get("root_timezone"))
                out.append("  → **cron timezone: unknown.** The schedule object carries no timezone field, "
                           f"so the wall-clock time this fires is not determinable from config."
                           + (f" The entity's own timezone is {ez}, but do **not** assume the cron follows it."
                              if ez else ""))
        out.append("")
    return "\n".join(out)

def _sec_schemes(p):
    se = p.get("scheme_enablement") or {}
    cm = p.get("capabilities_matrix") or {}
    holds = ((cm.get("authorization") or {}).get("hold_days_by_scheme")) or {}
    pv = _prov(p, "scheme_enablement")
    return (_fm(section="schemes", as_of=pv.get("as_of"), coverage=pv.get("coverage"),
                volatility=pv.get("volatility"), sources="derived from processors + processing profiles")
            + "\n\n# Schemes & payment methods\n\n## Card schemes\n\n"
            + _tbl(["Scheme", "Enabled", "Auth hold (days)"],
                   [[s.get("scheme"), "✅" if s.get("enabled") else "❌",
                     "/".join(str(x) for x in holds.get(s.get("scheme"), [])) or "—"]
                    for s in se.get("card_schemes", [])])
            + "\n## Alternative payment methods\n\n"
            + _tbl(["APM", "Enabled"],
                   [[a.get("name"), "✅" if a.get("enabled") else "❌"]
                    for a in se.get("alternative_payment_methods", [])]))

def _sec_webhooks(p):
    ri = p.get("reporting_and_integration") or {}
    pv = _prov(p, "reporting_and_integration")
    out = [_fm(section="webhooks", as_of=pv.get("as_of"), coverage=pv.get("coverage"),
               volatility=pv.get("volatility"), scope="client (workflows are account-wide)",
               sources="public API /workflows · /workflows/{id}"),
           "", "# Webhooks & workflows", "",
           "integration: " + (", ".join(ri.get("integration_types") or []) or "—"), ""]
    wfs = ri.get("workflows") or []
    if not wfs:
        out += ["_no workflows retrieved — a secret key (sk) is required to read these_", ""]
    for w in wfs:
        out += [f"### {w.get('name')} — `{w.get('id')}`" + ("  ·  active" if w.get("active") else "  ·  inactive")]
        for u in w.get("endpoints") or []: out.append(f"→ {u}")
        if w.get("scopes"): out.append(f"scoped by {len(w['scopes'])} condition(s): "
                                       + ", ".join(str(s.get('type')) for s in w["scopes"]))
        ev = w.get("events") or []
        out += [f"events ({len(ev)}): " + (", ".join(ev) if ev else "—"), ""]
    if ri.get("reporting_profiles") is not None and not ri.get("reporting_profiles"):
        out += ["## Reporting profiles", "",
                "**not available** — not exposed by the CAT API. Check the Checkout.com Dashboard.", ""]
    return "\n".join(out)

def _sec_glossary(p):
    g = (p.get("glossary") or {}).get("ids") or {}
    pv = _prov(p, "glossary")
    CODES = [("FT / C52 / FD", "funds transfer type on a payout profile — identifies the scheme money-movement product"),
             ("BAI", "Business Application Identifier — Visa's AFT (Account Funding Transaction) indicator on a pay-in profile"),
             ("TTI", "Payment Transaction Type Identifier — Mastercard's AFT indicator; the Mastercard equivalent of a BAI"),
             ("CAIC", "Card Acceptor Identification Code"),
             ("same_as_pc", "this processor inherits the setting from its processing channel"),
             ("complete_processing", "Checkout.com performs both authorization and settlement"),
             ("gws_only", "gateway-services only — Checkout.com routes but does not acquire"),
             ("processor_type: manual", "3DS processor configured manually rather than auto-provisioned")]
    return (_fm(section="glossary", as_of=pv.get("as_of"), coverage=pv.get("coverage"),
                sources="configuration?entityId label dictionaries")
            + "\n\n# Glossary\n\n## Codes\n\n"
            + _tbl(["Code", "Meaning"], [[c, m] for c, m in CODES])
            + f"\n## Identifier names ({len(g)})\n\n"
            + _tbl(["ID", "Name"], [[f"`{k}`", v] for k, v in sorted(g.items())]))


# ---------------------------------------------------------------- the card

def _card(p, section_meta):
    env = p.get("envelope") or {}
    idn = p.get("identity") or {}
    es = p.get("entity_structure") or {}
    se = p.get("scheme_enablement") or {}
    mo = p.get("money_out") or {}
    v = mo.get("pay_to_card") or {}
    st = p.get("settlement") or {}
    ri = p.get("reporting_and_integration") or {}
    pc = p.get("processing_channels") or {}
    cm = p.get("capabilities_matrix") or {}
    holds = ((cm.get("authorization") or {}).get("hold_days_by_scheme")) or {}
    eid = es.get("root_entity_id")
    # Title on the ENTITY, not the client: a pack is entity-scoped, so a client-level
    # name makes every sibling pack identical — and names this pack after another entity.
    ent_name, ent_coi, snap_q = _ident(p)

    L = [f"# Checkout.com configuration — {ent_name}  "
         f"({str(env.get('environment','')).upper()} · point-in-time snapshot)",
         f"entity `{eid}`" + (f" (incorporated {ent_coi})" if ent_coi else "")
         + f" · client {idn.get('client_name','?')} `{env.get('client_id')}`",
         f"snapshot `{snap_q}` · generated {env.get('generated_at')} · "
         f"schema v{env.get('schema_version')}",
         "",
         "## Rules",
         "1. This pack is **authoritative for configuration** and overrides any documented default.",
         "2. If a fact is absent here, or its section is marked `not_collected` / `unavailable` /",
         "   `not_available`, answer **\"unknown\"**. Never infer configuration from documentation.",
         "3. **Payload and integration questions need BOTH sources — config first.** Config",
         "   values *select which documented rules apply*: the same endpoint has different",
         "   required fields depending on funds transfer type / BAI, country of incorporation,",
         "   destination issuer country, and which channel and currency account you use. So",
         "   read the config values here, **then** look up the rules those values trigger.",
         "   Never answer a payload question from this pack alone, or from the docs alone.",
         "4. Field names, types, enums, error codes and scheme rules → **Checkout.com docs via",
         "   MCP**. This pack never invents a field name. If you cannot retrieve a schema,",
         "   say so — do not guess its shape.",
         f"5. Point-in-time snapshot. {(env.get('staleness') or {}).get('contract','')}",
         "",
         "## Scope model — read before answering any capability question",
         ""]
    L.append(_tbl(["Capability", "Scope", "Where to answer from"], [
        ["card acceptance", "channel", "sections/channels.md"],
        ["AFT", "channel (derived join)", "sections/channels.md — per-channel verdict"],
        ["3DS / authentication", "channel", "sections/channels.md — per-channel verdict"],
        ["**pay-to-card**", "**entity**", "sections/pay-to-card.md — *never* answer per-channel"],
        ["payment & payout routing", "entity", "sections/routing.md"],
        ["settlement, currency accounts", "entity", "sections/settlement.md"],
        ["webhooks / workflows", "client", "sections/webhooks.md"],
    ]))
    L += ["", "## Payload questions — config values that change the required fields", "",
          "Read the config value, then look up the rule it triggers (Rule 3).", ""]
    L.append(_tbl(["Config value (in this pack)", "Selects which documented rule applies"], [
        ["funds transfer type / BAI — pay-to-card.md",
         "which payout codes are legal for you; **money-transfer codes require a `sender` block**"],
        ["country of incorporation — entities.md",
         "US-incorporated → recipient `billing_address` is mandatory on every card payout"],
        ["destination corridors — pay-to-card.md",
         "issuer country AR·BD·CL·CO·EG·IN·MX·SA → `instruction.purpose` becomes mandatory"],
        ["processing channels — channels.md",
         "`processing_channel_id` is **required** on card payouts — **any** Active channel on the "
         "entity is valid; channels are not pay-in/payout scoped for pay-to-card"],
        ["currency accounts — settlement.md",
         "`source.id` must be a real `ca_*`; funding vs payout currency decides whether FX applies"],
        ["MCC — channels.md / pay-to-card.md",
         "MCC is **not** a field on a payout request; it comes from the profile the payout routes to"],
    ]))
    L += _test_cards_block("the Checkout.com docs MCP server", sandbox=_mcp_name(p)[1])
    L += ["## Can / cannot", ""]
    L.append("- accept: " + (", ".join(s.get("scheme") for s in se.get("card_schemes", [])) or "—")
             + " · APMs: " + (", ".join(a.get("name") for a in se.get("alternative_payment_methods", [])) or "—"))
    if v.get("enabled"):
        L.append(f"- pay-to-card: ✅ {', '.join(v.get('enabled_schemes') or [])} "
                 f"· FT {', '.join(v.get('ft_types') or [])} · destinations {_geo(v.get('destination_summary'))}")
    else:
        L.append("- pay-to-card: ❌ no Active payout profiles for this entity")
    if holds:
        L.append("- auth hold: " + " · ".join(f"{k} {'/'.join(str(x) for x in val)}d" for k, val in holds.items()))
    L.append("- settlement currencies: " + (", ".join(st.get("settlement_currencies") or []) or "—"))
    L.append(f"- entity timezone: {es.get('root_timezone') or '**unknown** — never assume UTC'}"
             " (qualifies wall-clock answers; not necessarily the payout cron's tz — see settlement.md)")
    tds = [c.get("name") for c in pc.get("channels", []) if (c.get("three_ds") or {}).get("enabled")]
    L.append(f"- 3DS configured on: {', '.join(tds) if tds else 'no channels'}")
    L.append(f"- channels {len(pc.get('channels', []))}"
             f" · profiles {len((p.get('processing_profiles') or {}).get('profiles', []))}"
             f" · workflows {len(ri.get('workflows') or [])}")
    ents = [f"{e.get('name')} (`{e.get('entity_id')}`, {e.get('country_of_incorporation')})"
            for e in es.get("entities", []) if e.get("entity_id") != eid]
    if ents: L.append("- sibling entities: " + " · ".join(ents))

    L += ["", "## What this snapshot does NOT know", ""]
    rows = []
    for k, val in (env.get("not_available") or {}).items():
        if isinstance(val, dict):
            rows.append([k.replace("_", " "), val.get("state", "not_available"), val.get("reason", "")])
        else:
            rows.append([k.replace("_", " "), "not_available", val])
    for sec, cov in (env.get("coverage_summary") or {}).items():
        if cov not in ("complete",):
            rows.append([sec.replace("_", " "), cov, (_prov(p, sec) or {}).get("notes", "")])
    L.append(_tbl(["Topic", "State", "Note"], rows) if rows
             else "_all collected sections are complete_\n")

    L += ["## Where to look", ""]
    L.append(_tbl(["Question about", "Read"], [
        ["a `pc_*` id · channel schemes, MIDs, features, services", "sections/channels.md"],
        ["**AFT** on a specific channel · BAI", "sections/channels.md"],
        ["**3DS** / protocol versions", "sections/channels.md"],
        ["SCA exemptions · auth hold · quasi-cash · a `pp_*` id", "sections/payin-profiles.md"],
        ["**pay-to-card** · funds transfer types · payout BIN/CAIC · corridors", "sections/pay-to-card.md"],
        ["**routing rules** · an `rt_*` id · where revenue/fees land", "sections/routing.md"],
        ["settlement · currency accounts · a `ca_*` id · payout schedule", "sections/settlement.md"],
        ["**webhooks** · workflows · events · reporting profiles", "sections/webhooks.md"],
        ["scheme / APM enablement", "sections/schemes.md"],
        ["**building a payload** · required fields · \"is my request right?\"",
         "config first: pay-to-card.md + channels.md + settlement.md + entities.md → **then** docs via MCP"],
        ["what an ID or a code means", "glossary.md"],
        ["entity structure · a `ent_*` id", "sections/entities.md"],
    ]))
    L += ["## Section index", "",
          _tbl(["File", "Coverage", "Volatility", "~tokens"],
               [[m["path"], m["coverage"], m.get("volatility", "—"), m["tokens"]] for m in section_meta])]
    return "\n".join(L)


def _readme(p, meta):
    env = p.get("envelope") or {}
    ent_name, ent_coi, snap_q = _ident(p)
    return f"""# Merchant configuration context pack — {ent_name}

Entity `{(p.get('entity_structure') or {}).get('root_entity_id')}`\
{f' (incorporated {ent_coi})' if ent_coi else ''} · \
client {(p.get('identity') or {}).get('client_name','?')} `{env.get('client_id')}`

Snapshot `{snap_q}` · generated {env.get('generated_at')} ·
environment {env.get('environment')} · ~{meta['total_tokens']} tokens total.

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
"""


# --------------------------------------------------- paste-as-project-instructions
#
# A DIFFERENT delivery from render_llm_bundle. That produces a card + section files for a
# session that can read files on demand. This produces ONE self-contained document to
# paste into a Claude project's instructions, where there is no filesystem — so there is
# deliberately no routing table, no section index and no lookup map: nothing to route to.
#
# Scoped to four questions:
#   1. general overview of how the entity is configured
#   2. AFT configuration
#   3. pay-to-card configuration
#   4. payload validation against config + Checkout docs
# Anything those four don't need is left out (webhooks, routing rules, the glossary).

def _nofm(s, demote=1, drop_title=False):
    """Prepare a standalone section for inclusion in one document.

    Strips the YAML front matter (meaningless when pasted) and demotes every heading by
    `demote` levels, so a section written as its own file with an H1 nests correctly under
    the document title instead of producing a second top-level heading.

    drop_title removes the section's own top heading — used where this document already
    supplies one, so the two don't appear back to back.
    """
    s = s.lstrip()
    if s.startswith("---"):
        end = s.find("\n---", 3)
        if end != -1:
            s = s[end + 4:]
    if drop_title:
        lines = s.strip().splitlines()
        for i, line in enumerate(lines):
            if line.startswith("#"):
                s = "\n".join(lines[i + 1:])
                break
    if demote:
        out, fence = [], False
        for line in s.strip().splitlines():
            if line.lstrip().startswith("```"):
                fence = not fence
            elif not fence and line.startswith("#"):
                line = "#" * demote + line
            out.append(line)
        s = "\n".join(out)
    return s.strip()


def _promote(s, levels=1):
    """Inverse of _nofm's demote: lift every heading by `levels`.

    A summary renderer writes H2 because it is nested under the pasted document's H1. The
    same content as its own file wants an H1 title, matching the _sec_* convention. Fence
    aware for the same reason _nofm is: a `#` inside a code block is not a heading.
    """
    out, fence = [], False
    for line in s.strip().splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
        elif not fence and line.startswith("#" * (levels + 1)):
            line = line[levels:]
        out.append(line)
    return "\n".join(out).strip()


def _aft_summary(p):
    """AFT: which channel, the AFT code (BAI or TTI) and its category, and what the profile permits."""
    chans = (p.get("processing_channels") or {}).get("channels", [])
    profs = {x.get("profile_id"): x for x in
             (p.get("processing_profiles") or {}).get("profiles", [])}
    out = ["## AFT (Account Funding Transactions)", "",
           "**A pay-in processing profile carrying an AFT code is AFT-enabled — that is what "
           "enables AFT.** A channel is AFT-enabled when one of its processors resolves to "
           "such a profile (joined on acquirer + scheme + MCC); AFT is not a field on the "
           "channel itself. " + AFT_INDICATOR_NOTE, ""]
    aftp = [x for x in (p.get("processing_profiles") or {}).get("profiles", [])
            if x.get("aft_enabled")]
    if aftp:
        arows = []
        for x in aftp:
            code, _ind = _aft_code(x.get("aft"))
            c = _classify_ft(code)
            arows.append([x.get("name") or f"`{x.get('profile_id')}`",
                          x.get("scheme") or "—",
                          _aft_cell(x.get("aft")),
                          (f"**{c['category_label']}** — {c['description']}" if c
                           else "not classified here — the code is real config; only its category is absent from this document's table"),
                          ", ".join(x.get("currencies") or []) or "not stated",
                          ", ".join(x.get("merchant_category_codes") or []) or "—",
                          x.get("acquiring_bin") or "—",
                          x.get("card_acceptor_country_code") or "—",
                          ("✅ required" if x.get("enable_recipient_details_submission")
                           else "not required" if x.get("enable_recipient_details_submission") is False
                           else "unknown"),
                          ("may be omitted" if (x.get("aft") or {}).get("is_skip_recipient_name_enabled")
                           else "required" if (x.get("aft") or {}).get("is_skip_recipient_name_enabled") is False
                           else "unknown"),
                          x.get("status") or "—"])
        out += ["**AFT-enabled pay-in profiles**", "",
                _tbl(["Profile", "Scheme", "AFT code", "Category", "Currencies", "MCC", "BIN",
                      "Acceptor country", "Recipient details", "Recipient name",
                      "Status"], arows), ""]

    live = [ch for ch in chans if (ch.get("aft") or {}).get("enabled") is True]
    if not live:
        unknown = [ch for ch in chans if (ch.get("aft") or {}).get("enabled") is None]
        out += [("**Not enabled on any channel.**" if not unknown else
                 f"**Not determinable** on {len(unknown)} channel(s) — the profile join did "
                 "not resolve. Treat as unknown, never as a no."), ""]
        return "\n".join(out)

    rows = []
    for ch in live:
        a = ch.get("aft") or {}
        # one row per matching profile: a channel can be AFT-enabled for Visa (BAI) and
        # Mastercard (TTI) through two different profiles — never collapse them into one
        for m in (a.get("matches") or [a]):
            pr = profs.get(m.get("profile_id")) or {}
            ft, _ind = _aft_code(m)
            cls = _classify_ft(ft)
            rows.append([
                f"{ch.get('name')} `{ch.get('processing_channel_id')}`",
                m.get("profile_name") or m.get("profile_id") or "—",
                m.get("scheme") or pr.get("scheme") or "—",
                _aft_cell(m),
                (f"**{cls['category_label']}** — {cls['description']}" if cls
                 else "not classified here — the code is real config; only its category is absent from this document's table"),
                ", ".join(pr.get("currencies") or []) or "not stated on the profile",
                (f"{m.get('authorization_validity_period')}d"
                 if m.get("authorization_validity_period") is not None else "—"),
            ])
    out.append(_tbl(["Channel", "Via profile", "Scheme", "AFT code", "Category", "Currencies allowed",
                     "Auth hold"], rows))
    out += ["**There are no corridor country lists on a pay-in AFT profile.** Verified "
            "across every profile on this client: `origination_countries` and "
            "`destination_countries` appear only on *payout* profiles (see Pay-to-card). "
            "What a pay-in AFT profile does carry is the acceptor's own country and the two "
            "recipient controls above. AFT destination/recipient **countries** are therefore "
            "**unknown** from config, not unrestricted. The category column comes from the Checkout.com card payouts "
            "documentation's funds-transfer-type table, not from CAT; a money transfer requires a `sender` block on the "
            "request. Codes outside that table (for example Mastercard AFT TTIs such as `P71`) are shown "
            "unclassified — that is a gap in the table, not a configuration problem.", ""]
    return "\n".join(out)


def _channels_table(p):
    """One row per channel: name, id, scheme, currencies, profiles, 3DS, AFT, MCC."""
    chans = (p.get("processing_channels") or {}).get("channels", [])
    rows = []
    for ch in chans:
        a = ch.get("aft") or {}
        tds = ch.get("three_ds") or {}
        # currencies and profiles both live on the processors, not the channel
        curs = sorted({c for pr in (ch.get("processors") or [])
                       for c in (pr.get("processing_currencies") or [])})
        cur = (", ".join(curs) if len(curs) <= 6
               else f"{len(curs)} incl. {', '.join(curs[:4])}")
        profs = []
        for pr in ch.get("processors") or []:
            nm = pr.get("profile_name")
            if nm and nm not in profs:
                profs.append(nm)
        rows.append([ch.get("name") or "—",
                     f"`{ch.get('processing_channel_id')}`",
                     ", ".join(ch.get("schemes_enabled") or []) or "—",
                     cur or "—",
                     ", ".join(profs) or "none matched",
                     "✅" if tds.get("enabled") else "❌",
                     "✅" if a.get("enabled") is True else
                     ("❌" if a.get("enabled") is False else "unknown"),
                     ", ".join(str(m) for m in (ch.get("mccs") or [])) or "—"])
    out = ["## Processing channels", ""]
    out.append(_tbl(["Name", "Processing channel ID", "Schemes", "Currencies",
                     "Processing profiles", "3DS", "AFT", "MCC"], rows)
               if rows else "_no channels_\n")
    out.append("Currencies and profiles are per-processor; a channel's values are the union "
               "across its processors. \"none matched\" means the processor is configured "
               "directly against an acquirer rather than through a profile.\n")
    return "\n".join(out)


def _p2c_summary(p):
    """Q3: pay-to-card, stated at entity level with corridors and FT codes."""
    mo = p.get("money_out") or {}
    v = mo.get("pay_to_card") or {}
    fx = mo.get("forex") or {}
    out = ["## Pay-to-card", "",
           "**Scope: entity-level.** Declared by processing profiles with "
           "`processing_type=payout` and `status=Active`. Processing channels carry no "
           "pay-to-card capability — never answer this per channel.", "",
           "**A payout profile is not bound to a processing channel.** If an Active payout "
           "profile exists on this entity it can be used with **any** of the entity's "
           "processing channels. The acquirer + scheme + MCC join that resolves a channel "
           "to a profile applies to **pay-in AFT only** — do not apply it here. In "
           "particular, a channel MCC that differs from a payout profile's MCC is **not** a "
           "mismatch and does not make the payout unroutable: the payout profile supplies "
           "the MCC, the channel does not have to match it. A card payout still requires a "
           "`processing_channel_id` in the request, but that field selects a channel, not "
           "the payout profile.", ""]
    if not v.get("enabled"):
        out += ["**Not enabled** — no Active payout processing profiles exist for this "
                "entity.", ""]
        return "\n".join(out)
    orig, dest = v.get("origination_summary") or {}, v.get("destination_summary") or {}
    rows = [["Schemes", ", ".join(v.get("enabled_schemes") or []) or "—"],
            ["Funds transfer types", ", ".join(v.get("ft_types") or []) or "—"],
            ["Supported MCCs", ", ".join(str(m) for m in (v.get("supported_mccs") or [])) or "—"],
            ["Origination countries", _geo(orig, v.get("origination_countries"))],
            ["Destination countries", _geo(dest, v.get("destination_countries"))],
            ["Currencies", _cur(v.get("currency_summary")) if v.get("currency_summary")
             else "not stated on the payout profiles"],
            # forex lives on money_out, NOT on pay_to_card. Reading it from the wrong
            # place made this table say "unknown" while the detail block below said
            # "enabled" — a self-contradiction inside one document.
            ["Forex", _verdict(
                {"enabled": fx["pay_to_card_forex_enabled"]} if "pay_to_card_forex_enabled" in fx else fx,
                lambda _: "✅ enabled", lambda _: "❌ not configured")]]
    out += [_tbl(["", ""], rows), ""]
    payouts = [x for x in (p.get("processing_profiles") or {}).get("profiles", [])
               if x.get("type") == "payout"]
    if payouts:
        prows = []
        for x in payouts:
            ft = x.get("funds_transfer_type")
            cls = _classify_ft(ft)
            prows.append([x.get("name") or f"`{x.get('profile_id')}`",
                          x.get("scheme") or "—",
                          f"`{ft}`" if ft else "—",
                          (f"**{cls['category_label']}** — {cls['description']}" if cls
                           else "unknown — code not recognised"),
                          "✅ yes" if cls and cls["requires_sender"] else
                          ("no" if cls else "unknown"),
                          x.get("acquiring_bin") or "—",
                          x.get("card_acceptor_identification_code") or "—",
                          ", ".join(x.get("merchant_category_codes") or []) or "—",
                          ", ".join(x.get("origination_countries") or []) or "—",
                          ", ".join(x.get("destination_countries") or []) or "—",
                          x.get("acceptance_mode") or "—",
                          x.get("checkout_legal_entity_code") or "—",
                          x.get("status") or "—"])
        out += ["**Payout profiles (the pay-to-card processors)**", "",
                _tbl(["Profile", "Scheme", "FT type", "Category", "`sender` required",
                      "BIN", "CAIC", "MCC", "Origination", "Destination", "Acceptance",
                      "Legal entity", "Status"], prows),
                "Origination and destination are **per profile** — the section summary above "
                "is the union across profiles, which can hide a profile with a narrower "
                "corridor.",
                "Category comes from the Checkout.com card payouts documentation "
                "(\"Funds transfer types\"), not from CAT — CAT reports only the code. "
                "A **money transfer** requires a `sender` block on the payout request; the "
                "other categories do not require one on that basis.", ""]
    return "\n".join(out)


def _ca_roles(p):
    """ca_* -> (name, roles). Currency accounts carry no name of their own in CAT; the
    routing rules do, and they also reveal what each account is FOR. Joining them turns an
    opaque id list into something answerable."""
    out = {}
    rt = p.get("routing") or {}
    for key in ("payment_routing_rules", "payout_routing_rules"):
        for r in rt.get(key) or []:
            for fld, role in (("revenue_currency_account", "revenue"),
                              ("fees_currency_account", "fees"),
                              ("source_identifier", "payout source")):
                cid = r.get(fld + "_id") if fld != "source_identifier" else r.get(fld)
                if not cid:
                    continue
                nm = r.get(fld + "_name") if fld != "source_identifier" else None
                e = out.setdefault(cid, {"name": None, "roles": set()})
                e["roles"].add(role)
                if nm and not e["name"]:
                    e["name"] = nm
    # payout instructions also draw on accounts
    for pi in (p.get("settlement") or {}).get("payout_instructions", []):
        for cid in (pi.get("schedule") or {}).get("currency_account_ids") or []:
            out.setdefault(cid, {"name": None, "roles": set()})["roles"].add("settlement")
    return out


def _settlement_summary(p):
    """Settlement as tables, consistent with Routing: accounts, then instructions."""
    st = p.get("settlement") or {}
    eid = (p.get("entity_structure") or {}).get("root_entity_id")
    roles = _ca_roles(p)
    # /entities/{eid}/currency-accounts IS entity-scoped: every account it returns belongs
    # to that entity. Do not filter — an account can legitimately exist without any routing
    # rule referencing it yet (e.g. a Chargebacks account), and dropping it would hide real
    # configuration. The record carries no entity_id field, so ownership is implied by the
    # endpoint, not stated on the row.
    accounts = st.get("currency_accounts", [])
    out = ["## Currency accounts", "",
           f"**Scope: this entity.** Currency accounts, routing rules and payout schedules "
           f"below are all read from `{eid}`'s own endpoints and belong to it. (Webhooks "
           "and workflows are client-level and shared with sibling entities.)", "",
           _tbl(["", ""], [["Settlement currencies",
                            ", ".join(sorted({a.get("currency") for a in accounts
                                              if a.get("currency")})) or "—"],
                           ["Currency accounts", str(len(accounts))],
                           ["Payout schedules", str(len(st.get("payout_instructions") or []))]]),
           ]
    rows = []
    for a in accounts:
        cid = a.get("currency_account_id")
        r = roles.get(cid) or {}
        rows.append([f"`{cid}`", a.get("name") or r.get("name") or "—",
                     a.get("currency"), a.get("status"),
                     ", ".join(sorted(r.get("roles") or [])) or "—"])
    out.append(_tbl(["Account", "Name", "Currency", "Status", "Used for"], rows))
    out.append("`Used for` is derived by joining this entity's routing rules and payout "
               "instructions. A blank means no rule or instruction in this snapshot "
               "references the account — it still belongs to this entity, it is simply not "
               "routed to yet.\n")

    out += ["## Payout schedules", ""]
    srows2 = []
    for pi in st.get("payout_instructions", []):
        sch = pi.get("schedule") or {}
        cas = sch.get("currency_account_ids") or []
        names = {a.get("currency_account_id"): a.get("name") for a in accounts}
        srows2.append([
            pi.get("name") or f"`{pi.get('instruction_id')}`",
            sch.get("threshold_amount"),
            sch.get("balance_minimum"),
            sch.get("settlement_type") or "—",
            (pi.get("frequency_derived") or "not stated")
            + (f" · cron `{sch['cron_schedule']}`" if sch.get("cron_schedule") else ""),
            ", ".join(f"{names.get(c) or '?'} `{c}`" for c in cas) or "—",
            (pi.get("date_created") or "unknown")[:19],
        ])
    out.append(_tbl(["Name", "Threshold amount", "Balance minimum", "Scheduler type",
                     "Frequency", "Currency account linked", "Date created"], srows2))
    out += ["`Frequency` is **derived** from the cron by this pack — CAT publishes no "
            "frequency field, and the cron carries no timezone, so the wall-clock time it "
            "fires is unknown. `Threshold amount` and `Balance minimum` are raw numbers "
            "with no currency or minor/major-unit indicator on the record.", "",
            "## Payout instrument", ""]
    irows, srows = [], []
    for pi in st.get("payout_instructions", []):
        i, sch = pi.get("instrument") or {}, pi.get("schedule") or {}
        irows.append([pi.get("name") or f"`{pi.get('instruction_id')}`",
                      sch.get("instruction_state") or "—",
                      i.get("instrument_type") or "—", i.get("currency") or "—",
                      i.get("account_holder") or "—",
                      i.get("bank_name") or "—",
                      ", ".join(i.get("redacted_fields") or []) or "none"])
        srows.append([pi.get("name") or f"`{pi.get('instruction_id')}`",
                      f"`{sch.get('cron_schedule')}`" if sch.get("cron_schedule") else "—",
                      sch.get("threshold_amount"), sch.get("balance_minimum"),
                      sch.get("settlement_type") or "—",
                      "✅" if sch.get("carry_forward_enabled") else "❌"])
    out.append(_tbl(["Instruction", "State", "Instrument", "Currency", "Holder", "Bank",
                     "Redacted"], irows))
    return "\n".join(out)


def _routing_summary(p):
    """Q: routing rules — what they match, and where revenue and fees land."""
    rt = p.get("routing") or {}
    eid = (p.get("entity_structure") or {}).get("root_entity_id")
    out = ["## Routing", "",
           f"**Scope: this entity.** Read from `/entities/{eid}/…-routing-rules`. Every "
           "currency account named below appears in the Settlement → Currency accounts "
           "table with its id, so the two can be cross-referenced.", ""]
    for key, title in (("payment_routing_rules", "Payment routing"),
                       ("payout_routing_rules", "Payout routing")):
        rules = rt.get(key) or []
        out += [f"### {title}", ""]
        if not rules:
            out += ["_none_", ""]
            continue
        rows = []
        for r in rules:
            c = r.get("conditions") or {}
            ev = ("all event types" if c.get("allow_any_event_type")
                  else (", ".join(r.get("event_types") or []) or "specific event types "
                        "(not listed on the record)"))
            if c and all(c.values()):
                match = "**all traffic** — every condition unrestricted"
            elif c:
                narrow = [k.replace("allow_any_", "").replace("_", " ")
                          for k, val in c.items() if not val]
                match = "restricted by " + ", ".join(narrow)
            else:
                match = r.get("source_identifier") and f"source `{r['source_identifier']}`" or "—"
            def acct(pfx):
                cid = r.get(pfx + "_id")
                nm = r.get(pfx + "_name")
                if not cid and not nm:
                    return "—"
                return (f"{nm} `{cid}`" if nm and cid else (nm or f"`{cid}`"))
            rows.append([f"`{r.get('rule_id')}`", r.get("status") or "—", match, ev,
                         acct("revenue_currency_account"), acct("fees_currency_account")])
        out.append(_tbl(["Rule", "Status", "Matches", "Events covered",
                         "Revenue → account", "Fees → account"], rows))
    out.append("Routing rules carry no name in CAT, so they are identified by id and "
               "described by what they match. `event_types` is one of the conditions: an "
               "unrestricted rule matches every event type.\n")
    return "\n".join(out)


def _webhooks_summary(p):
    """Q: webhooks — workflows, the events on each, and the endpoints they hit."""
    ri = p.get("reporting_and_integration") or {}
    wf = ri.get("workflows") or []
    subs = ri.get("webhook_subscriptions") or []
    eps = ri.get("webhook_endpoints") or []
    out = ["## Webhooks and workflows", "",
           "**Scope: client-level.** Workflows belong to the client, not this entity, so "
           "they may fire for sibling entities too.", ""]
    if wf:
        out.append(_tbl(["Workflow", "Id", "Active", "Events"],
                        [[w.get("name") or "—", f"`{w.get('id')}`",
                          "✅" if w.get("active") else "❌",
                          (", ".join(w.get("events") or [])[:300] or "—")] for w in wf]))
    else:
        out += ["_no workflows_", ""]
    if eps:
        out += [f"**Endpoints ({len(eps)})**", ""] + [f"- `{u}`" for u in eps] + [""]
    if subs:
        out += [f"**All subscribed events ({len(subs)})**", "",
                ", ".join(f"`{e}`" for e in sorted(subs)), ""]
    return "\n".join(out)


def _reporting_summary(p):
    """Reporting profiles — entity-level, from merlin's reporting-profiles-config-api.

    Verified entity-scoped: three entities returned three different profile sets. Not a
    CAT endpoint, so it can fail independently — say which case applies rather than
    rendering an empty table that reads like "none configured".
    """
    ri = p.get("reporting_and_integration") or {}
    profiles = ri.get("reporting_profiles") or []
    cov = ri.get("reporting_profiles_coverage")
    eid = (p.get("entity_structure") or {}).get("root_entity_id")
    out = ["## Reporting profiles", "",
           f"**Scope: this entity.** Each entity has its own reporting profile setup; these "
           f"belong to `{eid}`. Read from the reporting-profiles-config-api, a separate "
           "internal service to CAT.", ""]
    if cov == "unavailable":
        out += ["**unavailable** — that service could not be reached or authorised when this "
                "snapshot was taken. Answer **unknown** for reporting profiles and point to "
                "the Checkout.com Dashboard. Do **not** infer them from anything else.", ""]
        return "\n".join(out)
    if not profiles:
        out += ["**None configured.** The service responded and returned no profiles for "
                "this entity — this is a real negative, not a gap.", ""]
        return "\n".join(out)
    on = sum(1 for r in profiles if r.get("enabled") is True)
    out.append(_tbl(["Enabled", "Name", "Report type", "Created", "Profile id"],
                    [["✅" if r.get("enabled") else ("❌" if r.get("enabled") is False
                                                    else "unknown"),
                      r.get("name") or "—", r.get("report_type") or "—",
                      (r.get("date_created") or "—")[:10],
                      f"`{r.get('profile_id')}`"] for r in profiles]))
    out.append(f"{on} of {len(profiles)} enabled. A disabled profile exists but does not "
               "produce reports.\n")
    return "\n".join(out)


def _rtau_section(p):
    """Real Time Account Updater — its own value-added service, configured per scheme."""
    r = (p.get("risk_and_auth") or {}).get("real_time_account_updater") or {}
    out = ["## Real Time Account Updater (RTAU)", ""]
    if not r:
        out += ["**unavailable** — the RTAU configuration service could not be reached when "
                "this snapshot was taken. Answer **unknown**.", ""]
        return out

    out += ["**Scope: client-level**, inherited by every entity including this one. "
            "**Configured per scheme** — there is no single on/off switch, so \"is RTAU on\" "
            "has to be answered scheme by scheme.", "",
            _tbl(["", ""], [
                ["Billed entity", (f"{r.get('billed_entity_name')} "
                                   f"`{r.get('billed_entity_id')}`")
                                  if r.get("billed_entity_id") else "unknown"],
                ["MCC", r.get("mcc_label") or r.get("mcc") or "unknown"],
                ["Schemes with something active",
                 ", ".join(r.get("active_schemes_derived") or []) or "none"],
            ]),
            "The active-schemes row is **derived** by this pack from the switches below, not "
            "a field CAT provides.", ""]

    for sec in r.get("schemes") or []:
        out += [f"### {sec.get('scheme')}", ""]
        switches = [s for s in sec.get("settings") or [] if s.get("is_switch")]
        others = [s for s in sec.get("settings") or [] if not s.get("is_switch")]
        if switches:
            out.append(_tbl(["Setting", "Enabled"],
                            [[s.get("label") or f"`{s.get('name')}`",
                              "✅ yes" if s.get("value") is True else
                              ("❌ no" if s.get("value") is False else "unknown")]
                             for s in switches]))
        if others:
            rows = []
            for s in others:
                v = s.get("value")
                lbl = s.get("label") or f"`{s.get('name')}`"
                # a registration status with no value is NOT "not registered" — it is unknown
                if v in (None, ""):
                    v = ("**unknown** — not published on the configuration"
                         if "status" in lbl.lower() else "not set")
                rows.append([lbl, v])
            out.append(_tbl(["Field", "Value"], rows))
        out.append("")
    out += ["Registration statuses are blank on this configuration for every scheme. Blank "
            "means the status is **not published here** — it does not mean not registered. "
            "Check the Dashboard if registration state matters.", ""]
    return out


def _vas_summary(p):
    """Value-added services, plus network tokens read from nt-portal."""
    ri = p.get("reporting_and_integration") or {}
    ra = p.get("risk_and_auth") or {}
    chans = (p.get("processing_channels") or {}).get("channels", [])
    svcs = sorted({s for ch in chans for s in (ch.get("services") or [])})
    ia = ra.get("intelligent_acceptance") or {}
    nt0 = ra.get("network_tokens") or {}

    def _v(x, y="✅ enabled", n="❌ not enabled"):
        return y if x is True else (n if x is False else "unknown")

    # An index of which services are on. Intelligent Acceptance and Network Tokens are
    # separate services with substantial config of their own, so each gets its own section
    # below rather than being folded in here.
    rtau = (ra.get("real_time_account_updater") or {})
    rtau_active = rtau.get("active_schemes_derived") or []
    rows = [["Intelligent acceptance", _v(ia.get("enabled")), "client-level · own section below"],
            ["Network tokens", _v(nt0.get("allowed")), "client-level · own section below"],
            ["Real Time Account Updater",
             ("✅ enabled on " + ", ".join(rtau_active)) if rtau_active
             else ("❌ no scheme active" if rtau else "unknown"),
             "client-level · per scheme · own section below"]]
    for s in svcs:
        rows.append([s, "✅ enabled", "on this entity's processing channels"])
    for t in (ri.get("integration_types") or []):
        rows.append([t, "✅ enabled", "integration type"])
    for t in (ra.get("fraud_tooling") or []):
        rows.append([t, "✅ enabled", "risk / fraud"])
    out = ["## Value-added services", "",
           "Which services are switched on. Each service is configured separately — the two "
           "with substantial configuration have their own sections after this.", "",
           _tbl(["Service", "State", "Scope / note"], rows)]

    # ---- Intelligent Acceptance — a service in its own right, client-level ----
    out += ["## Intelligent acceptance", ""]
    if not ia:
        out += ["**unavailable** — the Intelligent Acceptance service could not be reached "
                "when this snapshot was taken. Answer **unknown**.", ""]
    else:
        def _yn(v, y="✅ yes", n="❌ no"):
            return y if v is True else (n if v is False else "unknown")
        addons = ia.get("addons") or []
        avail = ia.get("addons_available") or []
        # High level first — this is what a "give me an overview" answer should use.
        out += ["**Scope: client-level**, inherited by every entity including this one.", "",
                _tbl(["", ""], [
                    ["Enabled", _yn(ia.get("enabled"))],
                    ["Strategy", (f"**{ia.get('strategy_label')}** "
                                  f"(`{ia.get('strategy')}`)")
                                 if ia.get("strategy") else "unknown"],
                    ["Addons enabled", _yn(ia.get("addons_enabled"))
                     + (f" — {len(addons)} of {len(avail) or '?'} selected" if addons else "")],
                    ["Transactions processed by IA",
                     (f"{ia.get('optimized_ratio')}%" if ia.get("optimized_ratio")
                      else "unknown")],
                ]),
                "Everything below is detail — use it for a deep dive on Intelligent "
                "Acceptance, not for a high-level overview.", ""]

        if ia.get("strategy_description"):
            out += [f"**What the {ia.get('strategy_label')} strategy does**", "",
                    "> " + str(ia["strategy_description"]).replace("\n", "\n> "), ""]

        if addons:
            out += [f"**Addons enabled — {len(addons)} of {len(avail) or '?'}**", "",
                    _tbl(["Addon", "What it does"],
                         [[a.get("label") or f"`{a.get('value')}`",
                           a.get("description") or "—"] for a in addons]),
                    ""]
        elif ia.get("addons_enabled"):
            out += ["Addons are switched on but none are selected.", ""]
        else:
            out += ["No addons enabled.", ""]

        # What is available but off — a TAM's next question after "what's on".
        off = [a for a in avail
               if a.get("value") not in {x.get("value") for x in addons}]
        if off:
            out += [f"**Optional addons available but not enabled — {len(off)}**", "",
                    ", ".join(f"{a.get('label')} (`{a.get('value')}`)" for a in off), "",
                    "These are selectable under this strategy and are currently off. "
                    "Off is a real negative here, not an unknown.", ""]

        out += ["The configuration form carries a separate addon set for each strategy; only "
                f"the active strategy's (`{ia.get('strategy')}`) is reported — the others are "
                "dormant UI state, not configuration in force.", ""]

    # ---- Real Time Account Updater — a separate service again, client-level ----
    out += _rtau_section(p)

    # ---- Network Tokens — a separate service, also client-level ----
    out += ["## Network tokens", ""]
    nt = ra.get("network_tokens") or {}
    if not nt:
        out += ["**unavailable** — the network-token configuration service could not be "
                "reached when this snapshot was taken. Answer **unknown**; do not infer "
                "network token settings from anything else.", ""]
        return "\n".join(out)

    def yn(v, y="✅ yes", n="❌ no"):
        return y if v is True else (n if v is False else "unknown")
    out += [f"**Scope: client-level.** These settings belong to the client and are "
            f"**inherited by every entity**, including this one — they are not configured "
            f"per entity.", "",
            _tbl(["", ""], [
                ["Network tokens allowed", yn(nt.get("allowed"))],
                ["Default billed entity",
                 (f"{nt.get('default_billed_entity_name')} "
                  f"`{nt.get('default_billed_entity_id')}`")
                 if nt.get("default_billed_entity_id") else "unknown"],
                ["Provisioning enabled", yn(nt.get("provisioning_enabled"))],
                ["Provisioning mode",
                 (f"**{nt.get('provisioning_mode')}** (`{nt.get('provisioning_mode_raw')}`)"
                  if nt.get("provisioning_mode") else "unknown")],
            ])]
    schemes = nt.get("schemes") or []
    if schemes:
        out += ["**Scheme onboarding**", "",
                _tbl(["Scheme", "Transactions enabled", "Onboarded", "TRID"],
                     [[s.get("scheme"), yn(s.get("transactions_enabled")),
                       s.get("onboarded_on") or "unknown",
                       f"`{s.get('trid')}`" if s.get("trid") else "—"]
                      for s in schemes]),
                "Onboarding date and TRID are only published as free text on the "
                "configuration form, not as structured fields — they are parsed from it.", ""]
    # A disabled master switch alongside active provisioning is a real state, not an error.
    # Surface it rather than resolving it, so an answer does not pick a side.
    if nt.get("allowed") is False and (nt.get("provisioning_enabled") is True
                                       or any(s.get("transactions_enabled")
                                              for s in schemes)):
        out += ["⚠️ **Note the combination.** Network tokens are **not allowed** at client "
                "level, yet provisioning is enabled and schemes are onboarded with "
                "transactions enabled. The master switch governs whether Checkout-managed "
                "network tokens are used at all, so the scheme-level readiness below it "
                "does not imply tokens are in use. If the answer matters, verify in the "
                "Dashboard rather than reasoning from one field.", ""]
    return "\n".join(out)


                                                    # noqa: E301
# Section renderers are shared with the two-tier bundle, where sections really are files
# and "see pay-to-card.md" is correct. Pasted as project instructions there is no
# filesystem, and those references make the agent go hunting for files — listing
# directories, looking for merchant-context/ — before answering anything. Rewrite them to
# point within this document instead.
_FILE_REFS = (
    ("→ see pay-to-card.md", "→ see the **Pay-to-card** section below"),
    ("see settlement.md, whose", "see the **Settlement** section, whose"),
    ("see channels.md", "see the **Processing channels** section"),
    ("see payin-profiles.md", "see the **Pay-in processing profiles** section"),
    ("see routing.md", "see the **Routing** section"),
    ("see webhooks.md", "see the **Webhooks and workflows** section"),
    ("see entities.md", "see the **Entity structure** section"),
    ("see glossary.md", "see the ids inline in this document"),
)


def _delink(text):
    for old, new in _FILE_REFS:
        text = text.replace(old, new)
    # Anything left ending in .md would still invite a file read.
    return re.sub(r"\bsections/([\w-]+)\.md\b", r"the \1 section", text)


def _entity_structure(p):
    """Entity tree for the pasted document.

    Differs from the bundle's version in two ways that matter for a self-contained
    snapshot: the subject entity is marked explicitly, and sibling rows are labelled as
    orientation only. Without that, an answer can drift into reasoning from a sibling's
    configuration — which is a different entity with different capabilities.
    """
    es = p.get("entity_structure") or {}
    eid = es.get("root_entity_id")
    rows = []
    for e in es.get("entities", []):
        me = e.get("entity_id") == eid
        caps = e.get("capabilities") or {}
        rows.append([
            ("**" + str(e.get("name")) + "**" if me else e.get("name")),
            f"`{e.get('entity_id')}`",
            "**← this entity**" if me else "sibling",
            e.get("country_of_incorporation"), e.get("status"),
            e.get("timezone") or "unknown",
            "✅" if caps.get("payments") else ("❌" if caps else "—"),
            "✅" if caps.get("payouts") else ("❌" if caps else "—")])
    out = ["## Entity structure", "",
           _tbl(["Entity", "ID", "", "Incorp.", "Status", "Timezone", "Payments", "Payouts"],
                rows),
           "Sibling rows are listed for orientation only. **Every answer in this document "
           "is about the marked entity.** Sibling entities have their own channels, "
           "profiles, corridors and capabilities, none of which are captured here — never "
           "use a sibling's row to infer anything about this entity, and if asked about a "
           "sibling, say that it needs its own snapshot.", ""]
    return "\n".join(out)


def _overview(p):
    """Q1 lands here: everything needed for 'how is my entity configured'."""
    env = p.get("envelope") or {}
    idn = p.get("identity") or {}
    es = p.get("entity_structure") or {}
    se = p.get("scheme_enablement") or {}
    st = p.get("settlement") or {}
    pc = p.get("processing_channels") or {}
    pp = p.get("processing_profiles") or {}
    cm = p.get("capabilities_matrix") or {}
    v = (p.get("money_out") or {}).get("pay_to_card") or {}
    holds = ((cm.get("authorization") or {}).get("hold_days_by_scheme")) or {}
    ent_name, ent_coi, _ = _ident(p)

    eid = es.get("root_entity_id")
    this = next((e for e in es.get("entities", []) if e.get("entity_id") == eid), {})
    caps = this.get("capabilities") or {}
    # entity-level AFT rollup: AFT is a per-channel verdict, so "does this entity do AFT"
    # is true if any channel resolves to yes. Unknown if none resolve either way.
    aft_flags = [(ch.get("aft") or {}).get("enabled")
                 for ch in (pc.get("channels") or [])]
    if any(f is True for f in aft_flags):
        aft = "AFT ✅"
    elif aft_flags and all(f is False for f in aft_flags):
        aft = "AFT ❌"
    else:
        aft = "AFT unknown"
    status = " · ".join([
        this.get("status") or "unknown",
        "payments " + ("✅" if caps.get("payments") else "❌" if caps else "—"),
        "payouts " + ("✅" if caps.get("payouts") else "❌" if caps else "—"),
        aft])
    # GET /entities/{id} returns BOTH a principal and a registered address. They are often
    # identical but can differ, so each gets its own row — never collapsed or inferred
    # from the other.
    def _addr(a):
        return ", ".join(str(a[k]) for k in
                         ("line1", "line2", "city", "state", "postcode", "country_iso3_code")
                         if a.get(k))
    reg = this.get("registered_business_address") or {}
    pri = this.get("principal_business_address") or {}
    reg_s, pri_s = _addr(reg), _addr(pri)

    # name / doing_business_as / display_name are three separate fields and can all differ;
    # show the alternatives only when they add something.
    alts = [v for v in (this.get("doing_business_as"), this.get("display_name"))
            if v and v != ent_name]
    name_cell = f"{ent_name} `{eid}`"
    if alts:
        name_cell += " · also known as " + " / ".join(dict.fromkeys(alts))

    rows = [
        ["Client", f"{idn.get('client_name','?')} `{env.get('client_id')}`"],
        ["Entity", name_cell],
        ["Date created", this.get("date_created") or "unknown"],
        ["Status", status],
        ["Legal entity", this.get("cko_legal_entity")
         or ", ".join(this.get("cko_legal_entities") or []) or "unknown"],
        ["Business model", ", ".join(this.get("business_models") or []) or "unknown"],
        ["Principal address", pri_s or "not recorded"],
        ["Registered address", reg_s or "not recorded"],
        ["Processing URLs", ", ".join(f"`{u}`" for u in (this.get("processing_urls") or []))
         or "none recorded"],
        ["Timezone", es.get("root_timezone") or "**unknown** — never assume UTC"],
        ["Card schemes accepted", ", ".join(s.get("scheme") for s in se.get("card_schemes", [])) or "—"],
        ["APMs", ", ".join(a.get("name") for a in se.get("alternative_payment_methods", [])) or "—"],
        ["Processing channels", str(len(pc.get("channels", [])))],
        ["Processing profiles", str(len((pp or {}).get("profiles", [])))],
        ["Settlement currencies",
         ", ".join(sorted({a.get("currency") for a in (st.get("currency_accounts") or [])
                           if a.get("currency")})) or "—"],
        ["Auth hold by scheme",
         " · ".join(f"{k} {'/'.join(str(x) for x in val)}d" for k, val in holds.items()) or "—"],
        ["Pay-to-card",
         (f"✅ {', '.join(v.get('enabled_schemes') or [])} · FT {', '.join(v.get('ft_types') or [])}"
          if v.get("enabled") else "❌ no Active payout profiles for this entity")],
    ]
    out = ["## Overview", "", _tbl(["", ""], rows)]
    gaps = cm.get("notable_gaps") or []
    if gaps:
        out += ["**Notable gaps**", ""] + [f"- {g}" for g in gaps] + [""]
    return "\n".join(out)


def _mcp_name(p):
    """Docs MCP server the reading session should use; sandbox and production index
    different API surfaces, so the environment decides."""
    env = p.get("envelope") or {}
    sandbox = str(env.get("environment", "")).lower() == "sandbox"
    return ("checkout-mcp-sandbox" if sandbox else "checkout-mcp"), sandbox


# The pasted document is assembled from four blocks so the same blocks can be recombined
# for the multi-entity client document (render_client_document) without a second renderer:
#
#   _pi_rules        entity-scoped rules of engagement + the overview answer-format rule
#   _pi_sections     the entity's configuration, Overview through Schemes (per entity)
#   _pi_validation   "Validating a payload" + test cards — entity-independent guidance
#   _pi_not_covered  "What this does not cover" — derived per entity, never asserted
#
# render_project_instructions concatenates all four; its output is unchanged by the split.

def _pi_rules(p):
    env = p.get("envelope") or {}
    es = p.get("entity_structure") or {}
    mcp, sandbox = _mcp_name(p)
    return [
         "## How to use this",
         "",
         "1. **This document is authoritative for this merchant's configuration** and "
         "overrides any documented default. If it says a capability is off, it is off.",
         "2. **If a fact is not here, answer \"unknown\".** Do not infer configuration from "
         "documentation, and do not fill gaps with typical or default values. The "
         "*What this does not cover* section at the end lists known blind spots.",
         "3. **Payload questions need BOTH this document and the Checkout docs, config "
         "first.** Config values *select which documented rules apply* — see *Validating a "
         "payload* below. Never answer a payload question from config alone or docs alone.",
         f"4. **Field names, types, enums and error codes come from the Checkout.com docs "
         f"via the `{mcp}` MCP server** — not from this document, and not from memory. "
         + ("This is a sandbox snapshot, so use the sandbox MCP server, not production. "
            if sandbox else "")
         + "If you cannot retrieve a schema, say so rather than guessing its shape.",
         "5. **State the snapshot date** on any answer that depends on configuration, and "
         "suggest regenerating if the answer matters and the snapshot is old.",
         "6. **This is one entity at one point in time, and it stands alone.** It covers "
         f"only `{es.get('root_entity_id')}` as of the snapshot above. Do not blend in "
         "configuration from a sibling entity, an earlier snapshot, a previous "
         "conversation, or live API calls made elsewhere. If something here conflicts with "
         "anything you saw before, this document wins; if it is silent, the answer is "
         "\"unknown\" — not whatever was true previously.",
         "7. **This document is complete in itself. There are no companion files.** Do not "
         "list directories, look for a `merchant-context/` folder, read `CLAUDE.md`, or "
         "search the filesystem for configuration — none of it exists. Everything known "
         "about this merchant's configuration is in the text below. The only external "
         f"lookup you should make is to the `{mcp}` MCP server for API documentation.",

         "## How to answer a general overview question\n"
         "\n"
         "When asked anything of the form *\"give me an overview of my configuration\"*, "
         "*\"summarise my entity's setup\"*, *\"how am I configured\"* — however it is "
         "phrased — answer by **reproducing the tables below, as tables, in this order**:\n"
         "\n"
         "1. **Overview**\n"
         "2. **Processing channels** — the summary table only, not the per-channel detail "
         "blocks beneath it\n"
         "3. **AFT** — both tables\n"
         "4. **Pay-to-card** — the summary table and the payout profiles table\n"
         "5. **Currency accounts**\n"
         "6. **Payout schedules**\n"
         "7. **Routing** — both tables\n"
         "8. **Value-added services**, then **Intelligent acceptance**, **Real Time Account "
         "Updater**, **Network tokens**\n"
         "\n"
         "That is the order these sections appear in below, so you can work straight down the "
         "document. **Skip** *Pay-in processing profiles*, *Payout instrument*, *Webhooks and "
         "workflows*, *Reporting profiles*, *Schemes & payment methods* and *Validating a "
         "payload* — they are detail for specific questions, not part of a general overview.\n"
         "\n"
         "Rules for that answer:\n"
         "\n"
         "- **Reproduce the tables. Do not paraphrase them into prose.** The tables are the "
         "answer; a wall of sentences is not.\n"
         "- **Do not invent tables, groupings or scope-model summaries of your own.** If a "
         "fact is not in a table here, leave it out.\n"
         "- **Never mention another entity.** This document covers one entity. Do not list "
         "siblings, compare against them, or describe the client's other entities — even to "
         "say they are out of scope.\n"
         "- Keep prose to a few short lines: the snapshot date, and at most two or three "
         "observations that are genuinely derived (for example a scheme enabled for "
         "acceptance but with no AFT profile, or a payout profile with a narrower corridor "
         "than the summary implies). Put those **after** the tables, not before.\n"
         "- Do not add closing offers, next-step menus, or restatements of what the tables "
         "already say.\n"
         "\n"
         "For a question about one area only (AFT, pay-to-card, settlement, a named "
         "channel), reproduce just that area's tables and skip the rest.",
         ""]


def _pi_sections(p):
    """The entity's configuration, in overview-answer order. Same for both documents."""
    return [
         _overview(p),
         # summary table first, then the per-channel detail underneath it
         _channels_table(p),
         _nofm(_sec_channels(p, lambda i: str(i) if i else "—"), demote=1, drop_title=True),
         "",
         _aft_summary(p),
         _nofm(_sec_payin(p)),
         "",
         _p2c_summary(p),
         _settlement_summary(p),      # Currency accounts · Payout schedules · Payout instrument
         _routing_summary(p),
         _vas_summary(p),             # VAS index · Intelligent acceptance · RTAU · Network tokens
         # not part of a general overview answer — see the answer-format rules
         _webhooks_summary(p),
         _reporting_summary(p),
         _nofm(_sec_schemes(p)),
         ""]


def _pi_validation(p):
    """Config-selects-rule table and test cards. Entity-independent, so the client
    document renders it once rather than once per entity."""
    return [
         "## Validating a payload",
         "",
         "Read the config value first, then look up the documented rule it triggers. Each "
         "row below is a value in this document that changes what the API requires.",
         "",
         _tbl(["Config value (in this document)", "Selects which documented rule applies"], [
             ["funds transfer type / BAI — see AFT and Pay-to-card",
              "which payout codes are legal for this merchant; **money-transfer codes "
              "require a `sender` block**"],
             ["country of incorporation — see the registered business address in Overview",
              "US-incorporated → recipient `billing_address` is mandatory on every card payout"],
             ["destination corridors — see Pay-to-card",
              "issuer country AR·BD·CL·CO·EG·IN·MX·SA → `instruction.purpose` becomes mandatory"],
             ["processing channels — see Processing channels",
              "`processing_channel_id` is **required** on card payouts. **Any** Active "
              "channel on this entity is valid — channels are not pay-in or payout scoped "
              "for pay-to-card, and the channel does not select the payout profile"],
             ["currency accounts — see Settlement",
              "`source.id` must be a real `ca_*`; funding vs payout currency decides whether "
              "FX applies"],
             ["MCC — see Processing channels / Pay-to-card",
              "MCC is **not** a field on a payout request; it comes from the profile the "
              "payout routes to"],
         ]),
         "When validating, check the values against this document **and** retrieve the "
         "request schema from the docs for the required-field list. Report which specific "
         "values are wrong for this merchant, not just whether the shape is valid.",
         ""] + _test_cards_block(f"the `{_mcp_name(p)[0]}` MCP server", sandbox=_mcp_name(p)[1])


def _pi_not_covered(p):
    env = p.get("envelope") or {}
    L = ["## What this does not cover", ""]

    rows = []
    for k, val in (env.get("not_available") or {}).items():
        if isinstance(val, dict):
            rows.append([k.replace("_", " "), val.get("state", "not_available"),
                         val.get("reason", "")])
        else:
            rows.append([k.replace("_", " "), "not_available", str(val)])
    for sec, cov in (env.get("coverage_summary") or {}).items():
        if cov != "complete":
            rows.append([sec.replace("_", " "), cov, (_prov(p, sec) or {}).get("notes", "")])
    # These rows are DERIVED, never asserted. Hardcoding them told the reader to answer
    # "unknown" for facts this document prints a few sections earlier: provisioning mode is
    # read from nt-portal, and the FT category is stated for all 14 codes via FT_CATEGORIES.
    # The closing line below turns any row here into an "answer unknown" instruction, so a
    # false row is worse than a missing one.
    if not ((p.get("risk_and_auth") or {}).get("network_tokens") or {}).get("provisioning_mode"):
        rows.append(["network token provisioning mode", "not_available",
                     "CAT exposes only a form definition and nt-portal did not return a "
                     "current value"])
    rows += [["glossary of ids", "excluded",
              "omitted to keep this document small; ids are inline throughout"]]
    # envelope.not_available already contributes rows (reporting profiles, velocity limits,
    # pricing, bank details); dedupe by topic so nothing is listed twice with two wordings.
    seen, deduped = set(), []
    for r in rows:
        key = str(r[0]).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    L.append(_tbl(["Topic", "State", "Note"], deduped))
    L.append("Anything marked `not_available`, `unavailable`, `not_collected` or `excluded` "
             "means **answer \"unknown\"** — it does not mean \"no\".")
    return L


def render_project_instructions(p):
    """profile dict -> one self-contained markdown document for project instructions."""
    env = p.get("envelope") or {}
    es = p.get("entity_structure") or {}
    ent_name, ent_coi, snap = _ident(p)

    L = [f"# Checkout.com configuration — {ent_name}",
         "",
         f"Entity `{es.get('root_entity_id')}`"
         + (f", incorporated {ent_coi}" if ent_coi else "")
         + f" · environment **{env.get('environment')}**",
         f"Snapshot `{snap}` taken {env.get('generated_at')}. Point-in-time: "
         "configuration may have changed since.",
         ""]
    L += _pi_rules(p)
    L += _pi_sections(p)
    L += _pi_validation(p)
    L += _pi_not_covered(p)
    return _delink("\n".join(L)) + "\n"


# ------------------------------------------------------- multi-entity client document
#
# One client (CLI) holds several legal entities (ENT). This document keeps that hierarchy:
# a client-level header and rules, then each selected entity as its own self-contained
# section rendered by exactly the same functions as the single-entity document, demoted one
# heading level so it nests under the client. The per-entity content is byte-identical
# apart from heading depth — one renderer per fact, so the two documents cannot disagree.
#
# What changes versus the single-entity document is the framing only: the "stands alone,
# never mention another entity" rules are replaced by a resolve-the-entity-first rule,
# because here the reader legitimately holds several entities at once.

def _entity_row(p):
    """Identity row for the client's entity table, read from the entity's own profile."""
    es = p.get("entity_structure") or {}
    eid = es.get("root_entity_id")
    this = next((e for e in es.get("entities", []) if e.get("entity_id") == eid), {})
    caps = this.get("capabilities") or {}
    pc = p.get("processing_channels") or {}
    pp = p.get("processing_profiles") or {}
    return [f"**{this.get('name') or '?'}**", f"`{eid}`",
            this.get("country_of_incorporation") or "unknown",
            this.get("status") or "unknown",
            this.get("timezone") or es.get("root_timezone") or "unknown",
            "✅" if caps.get("payments") else ("❌" if caps else "—"),
            "✅" if caps.get("payouts") else ("❌" if caps else "—"),
            str(len(pc.get("channels", []))), str(len(pp.get("profiles", [])))]


def render_client_document(profiles):
    """list of profile dicts (same client) -> one markdown document, client at the top,
    each entity beneath it as its own section. Order follows the list given."""
    profiles = [p for p in profiles if p]
    if not profiles:
        return ""
    first = profiles[0]
    env = first.get("envelope") or {}
    idn = first.get("identity") or {}
    mcp, sandbox = _mcp_name(first)
    cid = env.get("client_id")
    client_name = idn.get("client_name", "?")

    included_ids = [(p.get("entity_structure") or {}).get("root_entity_id") for p in profiles]
    # Entities known to exist under the client but not selected for this document. Read
    # from the entity tree CAT returns, so this is derived, not asserted.
    all_ents = (first.get("entity_structure") or {}).get("entities", [])
    excluded = [e for e in all_ents if e.get("entity_id") not in included_ids]
    n = len(profiles)
    # One fetch stamps every entity with the same snapshot; profiles from different runs
    # are still accepted, so state the spread honestly rather than picking one.
    snaps = sorted({(p.get("envelope") or {}).get("generated_at") for p in profiles} - {None})
    taken = snaps[0] if len(snaps) == 1 else f"between {snaps[0]} and {snaps[-1]}"
    snap_ids = sorted({(p.get("envelope") or {}).get("snapshot_id") for p in profiles} - {None})
    snap_lbl = ("Snapshot " if len(snap_ids) == 1 else "Snapshots ") + \
               ", ".join(f"`{s}`" for s in snap_ids)

    def _ent_label(p):
        es = p.get("entity_structure") or {}
        eid = es.get("root_entity_id")
        this = next((e for e in es.get("entities", []) if e.get("entity_id") == eid), {})
        return this.get("name") or "?", eid

    L = [f"# Checkout.com configuration — {client_name} (client `{cid}`)",
         "",
         f"Client `{cid}` · environment **{env.get('environment')}** · "
         f"{n} {'entity' if n == 1 else 'entities'} in this document",
         f"{snap_lbl} taken {taken}. Point-in-time: "
         "configuration may have changed since.",
         "",
         "## Hierarchy",
         "",
         "A **client** (`cli_…`) is the top of the hierarchy. Beneath it sit **legal "
         "entities** (`ent_…`), and each entity owns its own processing channels, "
         "processing profiles, currency accounts, payout schedules, routing rules and "
         "reporting profiles. A small set of services is configured **at the client** and "
         "inherited by every entity: Intelligent Acceptance, Network Tokens, Real Time "
         "Account Updater, and webhooks/workflows. Each entity section below prints those "
         "as read for that entity.",
         "",
         "### Entities in this document",
         "",
         _tbl(["Entity", "ID", "Incorp.", "Status", "Timezone", "Payments", "Payouts",
               "Channels", "Profiles"],
              [_entity_row(p) for p in profiles]),
         ]
    if excluded:
        L += ["### Entities under this client NOT in this document", "",
              _tbl(["Entity", "ID", "Incorp.", "Status"],
                   [[e.get("name"), f"`{e.get('entity_id')}`",
                     e.get("country_of_incorporation"), e.get("status")] for e in excluded]),
              "These exist under the client but were not included. If asked about one, say "
              "it needs its own snapshot — do not infer anything about it from the entities "
              "that are included.", ""]
    L += [
         "## How to use this",
         "",
         "1. **This document is authoritative for this client's configuration** and "
         "overrides any documented default. If it says a capability is off, it is off.",
         "2. **If a fact is not here, answer \"unknown\".** Do not infer configuration from "
         "documentation, and do not fill gaps with typical or default values. Each entity "
         "section ends with its own *What this does not cover* table of known blind spots.",
         "3. **Payload questions need BOTH this document and the Checkout docs, config "
         "first.** Config values *select which documented rules apply* — see *Validating a "
         "payload* below. Never answer a payload question from config alone or docs alone.",
         f"4. **Field names, types, enums and error codes come from the Checkout.com docs "
         f"via the `{mcp}` MCP server** — not from this document, and not from memory. "
         + ("This is a sandbox snapshot, so use the sandbox MCP server, not production. "
            if sandbox else "")
         + "If you cannot retrieve a schema, say so rather than guessing its shape.",
         "5. **State the snapshot date** on any answer that depends on configuration, and "
         "suggest regenerating if the answer matters and the snapshot is old.",
         "6. **Resolve the entity before answering.** This document covers one client and "
         f"{n} of its entities, each in its own section headed `## Entity: <name> "
         "(<ent_…>)`.",
         "   - If the question names an entity — by name, by `ent_…` id, or by a channel, "
         "profile, currency account or routing rule id that appears in only one entity's "
         "section — answer **from that entity's section only**. Never carry a value from "
         "another entity's section into the answer, and do not mention the other entities "
         "except to say the answer is scoped to the one asked about.",
         "   - If the question names **no** entity (\"how am I configured\", \"summarise my "
         "config in general\"): for client-level services (Intelligent Acceptance, Network "
         "Tokens, RTAU, webhooks/workflows) answer once and say they apply across the "
         "client; for everything else answer **for each entity in turn, kept separate**. "
         "Never merge two entities' values into one fact — do not union their corridors, "
         "currencies, schemes or channels.",
         "   - If it is unclear which entity is meant and the answer differs between them, "
         "give the answer per entity rather than choosing one.",
         "7. **This document is complete in itself. There are no companion files.** Do not "
         "list directories, look for a `merchant-context/` folder, read `CLAUDE.md`, or "
         "search the filesystem for configuration — none of it exists. Everything known "
         "about this client's configuration is in the text below. The only external "
         f"lookup you should make is to the `{mcp}` MCP server for API documentation.",
         "",
         "## How to answer a general overview question",
         "",
         "**For a named entity** (*\"summarise my config on <entity>\"*, *\"how is "
         "<ent_…> configured\"*): answer by **reproducing that entity's tables, as tables, "
         "in this order**, taking every table from that entity's section:",
         "",
         "1. **Overview**",
         "2. **Processing channels** — the summary table only, not the per-channel detail "
         "blocks beneath it",
         "3. **AFT** — both tables",
         "4. **Pay-to-card** — the summary table and the payout profiles table",
         "5. **Currency accounts**",
         "6. **Payout schedules**",
         "7. **Routing** — both tables",
         "8. **Value-added services**, then **Intelligent acceptance**, **Real Time Account "
         "Updater**, **Network tokens**",
         "",
         "That is the order the sections appear within each entity, so you can work straight "
         "down that entity's section. **Skip** *Pay-in processing profiles*, *Payout "
         "instrument*, *Webhooks and workflows*, *Reporting profiles* and *Schemes & payment "
         "methods* — they are detail for specific questions, not part of a general overview.",
         "",
         "**For the client in general** (*\"summarise my config\"*, *\"give me an overview\"* "
         "with no entity named): reproduce the *Entities in this document* table above, then "
         "for each entity in document order, a heading with its name and id followed by its "
         "**Overview** table. Then the **Value-added services** index table once, noting it is "
         "client-level. Offer the full per-entity overview (the eight table groups above) "
         "for any entity on request rather than printing it for all of them unasked.",
         "",
         "Rules for either answer:",
         "",
         "- **Reproduce the tables. Do not paraphrase them into prose.** The tables are the "
         "answer; a wall of sentences is not.",
         "- **Do not invent tables, groupings or scope-model summaries of your own,** and do "
         "not build a combined table across entities. If a fact is not in a table here, "
         "leave it out.",
         "- Keep prose to a few short lines: the snapshot date, and at most two or three "
         "observations that are genuinely derived (for example a scheme enabled for "
         "acceptance but with no AFT profile, or a payout profile with a narrower corridor "
         "than the summary implies). Put those **after** the tables, not before.",
         "- Do not add closing offers, next-step menus, or restatements of what the tables "
         "already say.",
         "",
         "For a question about one area only (AFT, pay-to-card, settlement, a named "
         "channel), reproduce just that area's tables for the entity in question and skip "
         "the rest.",
         ""]
    L += _pi_validation(first)

    for p in profiles:
        name, eid = _ent_label(p)
        es = p.get("entity_structure") or {}
        this = next((e for e in es.get("entities", []) if e.get("entity_id") == eid), {})
        coi = this.get("country_of_incorporation")
        penv = p.get("envelope") or {}
        body = "\n".join(_pi_sections(p) + _pi_not_covered(p))
        L += ["", "---", "",
              f"<!-- ===== ENTITY {eid} BEGIN ===== -->",
              f"## Entity: {name} (`{eid}`)",
              "",
              f"Entity `{eid}`" + (f", incorporated {coi}" if coi else "")
              + f" · snapshot taken {penv.get('generated_at')}. Everything under this "
              "heading, down to the next `## Entity:` heading, is about this entity only.",
              "",
              _nofm(body, demote=1),
              "",
              f"<!-- ===== ENTITY {eid} END ===== -->"]
    return _delink("\n".join(L)) + "\n"


# ---------------------------------------------------------------- entry point

# ---------------------------------------------- section files promoted from the paste doc
#
# These four sections used to exist ONLY in project-instructions.md. `sections/` was
# therefore not a superset of the pasted document, so any consumer of the two-tier pack had
# to read both variants and merge them — and the two could disagree on a fact, making the
# merge a correctness risk rather than a formatting chore.
#
# Nothing was missing from the data; only the file set was short. The renderers below are
# the same ones the pasted document uses, so the two can never drift. _promote and _fm
# supply the section-file form (H1 title, front matter) that _nofm strips on the way in.

def _sec_overview(p):
    pv = _prov(p, "identity")
    return (_fm(section="overview", as_of=pv.get("as_of"), coverage=pv.get("coverage"),
                volatility=pv.get("volatility"), scope="entity",
                sources="/clients/{c} · /entities/{id} · /configuration/breadcrumb")
            + "\n\n" + _promote(_overview(p)))


def _sec_aft(p):
    pv = _prov(p, "processing_profiles")
    return (_fm(section="aft", as_of=pv.get("as_of"), coverage=pv.get("coverage"),
                volatility=pv.get("volatility"),
                scope="channel (derived — a pay-in profile carrying an AFT code, BAI or TTI, is what enables it)",
                sources="/entities/{e}/processing-channels · "
                        "/entities/{e}/processing-profiles · /processing-profiles/v2/{id}",
                not_covered="destination/recipient countries (not on a pay-in AFT profile)")
            + "\n\n" + _promote(_aft_summary(p)))


def _sec_vas(p):
    pv = _prov(p, "risk_and_auth")
    return (_fm(section="value-added-services", as_of=pv.get("as_of"),
                coverage=pv.get("coverage"), volatility=pv.get("volatility"),
                scope="client (inherited by every entity)",
                sources="nt-portal (network tokens) · pp-tenet-int (intelligent "
                        "acceptance) · rtau")
            + "\n\n" + _promote(_vas_summary(p)))


def _sec_reporting_profiles(p):
    pv = _prov(p, "reporting_and_integration")
    return (_fm(section="reporting-profiles", as_of=pv.get("as_of"),
                coverage=pv.get("coverage"), volatility=pv.get("volatility"),
                scope="entity",
                sources="merlin reporting-profiles-config-api")
            + "\n\n" + _promote(_reporting_summary(p)))


def render_llm_bundle(p):
    """profile dict -> {"files": {path: markdown}, "lookup": {...}, "meta": {...}}"""
    G = (p.get("glossary") or {}).get("ids") or {}
    def nm(i):
        if not i: return "—"
        return f"{G[i]}" if i in G else str(i)

    # Ordered as an overview answer should use them, so the INDEX section index reads in
    # the same order the answer-format rule specifies.
    sections = {
        "sections/overview.md":       _sec_overview(p),
        "sections/entities.md":       _sec_entities(p),
        "sections/channels.md":       _sec_channels(p, nm),
        "sections/aft.md":            _sec_aft(p),
        "sections/payin-profiles.md": _sec_payin(p),
        "sections/pay-to-card.md":    _sec_p2c(p),
        "sections/routing.md":        _sec_routing(p, nm),
        "sections/settlement.md":     _sec_settlement(p),
        "sections/value-added-services.md": _sec_vas(p),
        "sections/reporting-profiles.md":   _sec_reporting_profiles(p),
        "sections/schemes.md":        _sec_schemes(p),
        "sections/webhooks.md":       _sec_webhooks(p),
        "glossary.md":                _sec_glossary(p),
    }
    # The primary artifact for the paste-into-project-instructions workflow. Kept out of
    # `sections` so it is not counted as a routable section of the two-tier pack.
    project_instructions = render_project_instructions(p)
    SEC_OF = {"sections/overview.md": "identity",
              "sections/entities.md": "entity_structure", "sections/channels.md": "processing_channels",
              "sections/aft.md": "processing_profiles",
              "sections/payin-profiles.md": "processing_profiles", "sections/pay-to-card.md": "money_out",
              "sections/routing.md": "routing", "sections/settlement.md": "settlement",
              "sections/value-added-services.md": "risk_and_auth",
              "sections/reporting-profiles.md": "reporting_and_integration",
              "sections/schemes.md": "scheme_enablement", "sections/webhooks.md": "reporting_and_integration",
              "glossary.md": "glossary"}
    section_meta = []
    for path in sections:
        pv = _prov(p, SEC_OF[path])
        section_meta.append({"path": path, "coverage": pv.get("coverage", "unknown"),
                             "volatility": pv.get("volatility"), "tokens": est_tokens(sections[path])})

    # id -> file. `grep <id>` is the primary mechanism; this is the direct index.
    lookup = {}
    for ch in (p.get("processing_channels") or {}).get("channels", []):
        if ch.get("processing_channel_id"): lookup[ch["processing_channel_id"]] = "sections/channels.md"
    for pr in (p.get("processing_profiles") or {}).get("profiles", []):
        if pr.get("profile_id"):
            lookup[pr["profile_id"]] = ("sections/pay-to-card.md" if pr.get("type") == "payout"
                                        else "sections/payin-profiles.md")
    for e in (p.get("entity_structure") or {}).get("entities", []):
        if e.get("entity_id"): lookup[e["entity_id"]] = "sections/entities.md"
    for a in (p.get("settlement") or {}).get("currency_accounts", []):
        if a.get("currency_account_id"): lookup[a["currency_account_id"]] = "sections/settlement.md"
    for k in ("payment_routing_rules", "payout_routing_rules"):
        for r in (p.get("routing") or {}).get(k, []):
            if r.get("rule_id"): lookup[r["rule_id"]] = "sections/routing.md"
    for w in ((p.get("reporting_and_integration") or {}).get("workflows") or []):
        if w.get("id"): lookup[w["id"]] = "sections/webhooks.md"

    index = _card(p, section_meta)
    meta = {"snapshot_id": (p.get("envelope") or {}).get("snapshot_id"),
            "entity_id": (p.get("entity_structure") or {}).get("root_entity_id"),
            "index_tokens": est_tokens(index),
            "total_tokens": est_tokens(index) + sum(m["tokens"] for m in section_meta),
            "project_instructions_tokens": est_tokens(project_instructions),
            "sections": sorted(section_meta, key=lambda m: m["path"])}
    files = {"project-instructions.md": project_instructions,
             "INDEX.md": index, "README.md": _readme(p, meta), "lookup.json": None}
    files.update(sections)
    return {"files": {k: v for k, v in files.items() if v is not None},
            "lookup": dict(sorted(lookup.items())), "meta": meta}
