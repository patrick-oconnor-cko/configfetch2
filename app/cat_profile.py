#!/usr/bin/env python3
"""
CAT merchant-profile pipeline as an importable library.

  fetch_all(base_url, token, client_id, entity_id) -> responses dict (in memory)
  normalize(responses)                             -> schema-valid profile dict
  render_md(profile) / render_llms(profile)        -> strings
  enrich_public_api(profile, sk, pub_base)         -> adds webhooks (best effort)

Domain rule: pay-to-card processors are processing profiles with processing_type=payout.
Sections whose source errored are stamped coverage:"unknown" (never fabricated).
"""
import json, re, urllib.request, urllib.error, datetime

# ---------- constants ----------
ISO3 = {"GBR":"GB","USA":"US","FRA":"FR","ITA":"IT","CYP":"CY","ARE":"AE","DEU":"DE","ESP":"ES","NLD":"NL","IRL":"IE","SAU":"SA"}
try:  # full ISO 3166-1 alpha-3 -> alpha-2 when available
    import pycountry
    ISO3 = {**ISO3, **{c.alpha_3: c.alpha_2 for c in pycountry.countries}}
except Exception:
    pass
CARD = {"visa","mastercard","amex","discover","diners","jcb","cartes_bancaires","unionpay"}
SCHEME = {"VISA":"visa","MASTERCARD":"mastercard","AMEX":"amex","AMERICAN EXPRESS":"amex","DISCOVER":"discover",
          "DINERS":"diners","JCB":"jcb","CARTES BANCAIRES":"cartes_bancaires","UNIONPAY":"unionpay"}

# Reporting profiles live on a DIFFERENT service to CAT (merlin), on an internal host.
# The CAT bearer token is accepted. Verified entity-scoped across three entities: each
# returns a different profile set. Unreachable off the corporate network — a failure here
# must degrade this one section to `unavailable`, never break the whole fetch.
REPORTING_BASE = "https://merlin-alb.sbox.internal/reporting-profiles-config-api"

# Network token configuration. CLIENT-level, inherited by every entity. A third service,
# again on an internal host, again accepting the CAT bearer token. Unlike CAT's own
# /clients/{id}/network-tokens (a form DEFINITION with every value null) this one returns
# populated values, so it is the only readable source of the actual settings.
NT_BASE = "https://nt-portal.sbox.checkout.internal/vault-nt-portal"

# Intelligent Acceptance. CLIENT-level, inherited by every entity. Fourth internal
# service, same CAT bearer token.
IA_BASE = "https://pp-tenet-int.sbox.internal/tenet-config-controller/cat-api"

# Real Time Account Updater — a fifth, entirely separate value-added service. Client-level.
# Quirk: this service returns 415 on a GET unless Content-Type: application/json is sent,
# even though a GET has no body.
RTAU_BASE = "https://rtau.sbox.checkout.internal/vault-rtau-portal"
RTAU_HEADERS = {"Content-Type": "application/json"}

# RTAU is configured per scheme, and the field names are opaque. Group them the way the
# form does, and carry the form's own labels so nothing has to be inferred from a slug.
RTAU_SCHEME_SECTIONS = ("Mastercard", "Visa", "American Express", "Batch Account Updater")


def parse_rtau_config(d):
    """Flatten the RTAU form, preserving its per-scheme grouping.

    Parsed per section rather than into one flat name->field map because the same field
    name appears in more than one section (`schemes.scheme_merchant_id` is under both
    Mastercard and Visa) and a flat map would silently collapse them.

    There is no master on/off switch: RTAU enablement is per scheme. Any "RTAU enabled"
    summary is therefore DERIVED, and marked as such.
    """
    top, sections = {}, []
    for f in ((d or {}).get("schema") or {}).get("form_fields") or []:
        sec = f.get("form_section")
        if sec:
            fields = []
            for sf in sec.get("form_fields") or []:
                if not sf.get("name") or sf.get("form_section"):
                    continue
                fields.append(drop_empty({
                    "name": sf.get("name"), "label": sf.get("label"),
                    "value": sf.get("value"),
                    "is_switch": sf.get("display_style") == "switchButton",
                }))
            if fields:
                sections.append({"scheme": sec.get("label"), "settings": fields})
        elif f.get("name"):
            top[f["name"]] = f

    def val(n): return (top.get(n) or {}).get("value")
    def opt_label(n, v):
        return next((o.get("label") for o in (top.get(n) or {}).get("options") or []
                     if o.get("value") == v), v)

    # derived only — see docstring
    active = [s["scheme"] for s in sections
              if any(x.get("is_switch") and x.get("value") is True for x in s["settings"])]
    return drop_empty({
        "scope": "client",
        "billed_entity_id": val("billed_entity"),
        "billed_entity_name": opt_label("billed_entity", val("billed_entity")),
        "mcc": val("mcc"),
        "mcc_label": opt_label("mcc", val("mcc")),
        "schemes": sections,
        "active_schemes_derived": active,
    })


def _addon_detail(blob, label):
    """Pull one addon's full description out of the bullet list.

    The form publishes every available addon's description as one plainText blob of
    "• <Label>: <description>" lines. Matching on the option label recovers the full prose
    for an enabled addon instead of settling for its short label. Falls back to the label
    if no bullet matches, so a wording change upstream degrades rather than blanks.
    """
    if not blob or not label:
        return label
    for line in str(blob).split("•"):
        line = line.strip()
        if line.lower().startswith(str(label).lower()):
            _, sep, rest = line.partition(":")
            return rest.strip() if sep and rest.strip() else line
    return label


def parse_ia_config(d):
    """Flatten the Intelligent Acceptance form.

    The form carries a field FAMILY per strategy — description_<s>, addons_enabled_<s>,
    addons_<s>, addons_description_<s> — for all four strategies at once. Only the active
    strategy's family is live; the rest are dormant UI state. Reading them all would
    present dormant config as if it applied.
    """
    fields = {}
    def walk(fs):
        for f in fs or []:
            if f.get("form_section"):          # TRUTHY: some forms set this to null on
                walk(f["form_section"].get("form_fields"))   # every ordinary field
            elif f.get("name"):
                fields[f["name"]] = f
    walk(((d or {}).get("schema") or {}).get("form_fields"))

    def val(n): return (fields.get(n) or {}).get("value")
    def opts(n): return (fields.get(n) or {}).get("options") or []
    def opt_label(n, v):
        return next((o.get("label") for o in opts(n) if o.get("value") == v), v)

    def static_text(n):
        """Content of a plainText display field.

        For an INPUT control, `default_value` is a fallback and must never be reported as
        configuration (see NT's default_provision_mode). For a `plainText` field there is
        no user input at all — `value` is always null and `default_value` IS the copy. So
        read default_value only when the field is genuinely display-only.
        """
        f = fields.get(n) or {}
        if f.get("display_style") != "plainText":
            return f.get("value")
        return f.get("value") or f.get("default_value")

    strat = val("strategy")
    # addon values are opaque slugs; the form's own option labels are the descriptions
    sel = val(f"addons_{strat}") or []
    available = opts(f"addons_{strat}")
    return drop_empty({
        "scope": "client",
        "enabled": val("intelligent_acceptance_enabled"),
        "strategy": strat,
        "strategy_label": opt_label("strategy", strat),
        "strategy_description": static_text(f"description_{strat}"),
        "strategies_available": [o.get("label") for o in opts("strategy")],
        "addons_enabled": val(f"addons_enabled_{strat}"),
        "addons_description": static_text(f"addons_description_{strat}"),
        "addons": [{"value": v, "label": opt_label(f"addons_{strat}", v),
                    "description": _addon_detail(
                        static_text(f"addons_description_{strat}"),
                        opt_label(f"addons_{strat}", v))}
                   for v in sel],
        # everything selectable under the active strategy, so a deep dive can show what is
        # available but switched off — not just what is on
        "addons_available": [{"value": o.get("value"), "label": o.get("label")}
                             for o in available],
        "addons_available_count": len(available),
        "optimized_ratio": val("optimized_ratio"),
    })


def parse_nt_config(d):
    """Flatten the nt-portal form model into the facts that matter.

    The form nests fields inside form_sections, and the per-scheme onboarding detail is
    only present as a human-readable `label` on a plainText field — there is no structured
    date or TRID. Parse what can be parsed and keep the original label verbatim so nothing
    is lost or silently misread.
    """
    fields = {}
    def walk(fs):
        for f in fs or []:
            if f.get("form_section"):          # TRUTHY: some forms set this to null on
                walk(f["form_section"].get("form_fields"))   # every ordinary field
            elif f.get("name"):
                fields[f["name"]] = f
    walk(((d or {}).get("schema") or {}).get("form_fields"))

    def val(n): return (fields.get(n) or {}).get("value")
    def label_of(n): return (fields.get(n) or {}).get("label")

    def opt_label(n, v):
        for o in (fields.get(n) or {}).get("options") or []:
            if o.get("value") == v: return o.get("label")
        return v

    schemes = []
    for sch, key in (("visa", "visa"), ("mastercard", "mastercard")):
        raw = label_of(f"scheme_configuration.{key}_status")
        enabled = val(f"scheme_configuration.enabled_{key}")
        if raw is None and enabled is None:
            continue
        m = re.search(r"[Oo]nboarded to \S+ on (.+?)(?:,|$)", raw or "")
        trid = re.search(r"TRID:\s*(\S+?)(?:,|$)", raw or "")
        schemes.append(drop_empty({
            "scheme": sch,
            "transactions_enabled": enabled,
            "onboarded_on": m.group(1).strip() if m else None,
            "trid": trid.group(1).strip() if trid else None,
            "aft_enabled": True if raw and "AFT enabled" in raw else None,
            "nt_updates_enabled": True if raw and "NT updates enabled" in raw else None,
            "raw_status": raw,
        }))

    prov_state = val("provisioning_state")
    mode = val("default_provision_mode")
    return drop_empty({
        "scope": "client",
        "allowed": val("nt_state"),
        "default_billed_entity_id": val("default_entity_id"),
        "default_billed_entity_name": opt_label("default_entity_id", val("default_entity_id")),
        "provisioning_enabled": (True if prov_state == "active" else
                                 False if prov_state == "inactive" else None),
        "provisioning_state_raw": prov_state,
        "provisioning_mode": opt_label("default_provision_mode", mode),
        "provisioning_mode_raw": mode,
        "schemes": schemes,
    })

# Funds transfer type -> category. Source: Checkout.com docs, "Funds transfer types" on
# Payments > Request payouts > Card payouts. Visa calls the code a Business Application
# Identifier (BAI) / Visa Direct code; Mastercard calls it a Transaction Type Identifier /
# Mastercard Send code.
#
# NOTE it is a THREE-way classification, not money-send vs not: online gambling is its own
# category. Only `money_transfer` is what the docs mean by a money transfer, and that is the
# category whose payout requests require a `sender` block.
#
# Not derivable from config — CAT reports the code, never its category. Kept here so the
# generated pack can state the category instead of telling the reader to go look it up.
FT_CATEGORIES = {
    # Visa (BAI / Visa Direct)
    "AA": ("money_transfer",     "Account-to-account",                  "visa"),
    "FT": ("money_transfer",     "Funds transfer",                      "visa"),
    "LA": ("money_transfer",     "Cross-border money transfer",         "visa"),
    "PP": ("money_transfer",     "Peer-to-peer (P2P) money transfer",   "visa"),
    "WT": ("money_transfer",     "Staged digital wallet transfer",      "visa"),
    "FD": ("non_money_transfer", "Funds disbursement",                  "visa"),
    "LO": ("non_money_transfer", "Loyalty payments",                    "visa"),
    "PD": ("non_money_transfer", "Payroll and pension disbursements",   "visa"),
    "OG": ("online_gambling",    "Online gambling",                     "visa"),
    # Mastercard (Transaction Type Identifier / Mastercard Send)
    "C07": ("money_transfer",     "Person-to-person transfer",  "mastercard"),
    "C52": ("money_transfer",     "Transfer to own account",    "mastercard"),
    "C55": ("non_money_transfer", "Business disbursement",      "mastercard"),
    "C65": ("non_money_transfer", "Business-to-business transfer", "mastercard"),
    "C04": ("online_gambling",    "Gaming repay",               "mastercard"),
}
FT_CATEGORY_LABEL = {"money_transfer": "money transfer",
                     "non_money_transfer": "non-money transfer",
                     "online_gambling": "online gambling"}


_CRON_DOW = {"0":"Sun","1":"Mon","2":"Tue","3":"Wed","4":"Thu","5":"Fri","6":"Sat","7":"Sun"}

def cron_frequency(cron):
    """Plain-English frequency from a cron expression. DERIVED — CAT has no such field.

    Deliberately conservative: only patterns that are unambiguous are described, anything
    else returns None so the renderer says "not stated" rather than guessing.
    """
    if not cron or len(str(cron).split()) != 5:
        return None
    mi, hh, dom, mon, dow = str(cron).split()
    if not (mi.isdigit() and hh.isdigit()):
        return None
    at = f"{int(hh):02d}:{int(mi):02d}"
    if dom == "*" and mon == "*":
        if dow == "*":
            return f"daily at {at}"
        if dow == "1-5":
            return f"weekdays (Mon–Fri) at {at}"
        if "-" in dow or "," in dow:
            parts = dow.replace("-", ",").split(",")
            names = [_CRON_DOW.get(p) for p in parts]
            if all(names):
                return f"{'–'.join(names) if '-' in dow else ', '.join(names)} at {at}"
            return None
        if dow in _CRON_DOW:
            return f"weekly on {_CRON_DOW[dow]} at {at}"
    if dow == "*" and mon == "*" and dom.isdigit():
        return f"monthly on day {int(dom)} at {at}"
    return None


def classify_ft(code):
    """Category for a funds transfer type / BAI code, or None if the code is unrecognised.

    An unrecognised code must stay unknown — never default it to a category.
    """
    if not code:
        return None
    hit = FT_CATEGORIES.get(str(code).strip().upper())
    if not hit:
        return None
    cat, desc, sch = hit
    return {"code": str(code).strip().upper(), "category": cat,
            "category_label": FT_CATEGORY_LABEL[cat], "description": desc,
            "scheme": sch,
            # only money transfers require a sender block, per the card payouts docs
            "requires_sender": cat == "money_transfer"}


def _now(): return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_reporting_table(d):
    """merlin returns a UI table model, not a resource list:
        {schema: {table: {headers, rows: [{id, columns: [{name, value}]}]},
                  pagination: {total, skip, limit}}}
    Flatten each row's columns into a dict keyed by header name.
    """
    sch = (d or {}).get("schema") or {}
    rows = ((sch.get("table") or {}).get("rows")) or []
    out = []
    for r in rows:
        cols = {c.get("name"): c.get("value") for c in (r.get("columns") or [])}
        out.append(drop_empty({
            "profile_id": r.get("id") or cols.get("ID"),
            "name": cols.get("Name"),
            "report_type": cols.get("Report Type"),
            "enabled": True if cols.get("Enabled") == "Yes" else
                       (False if cols.get("Enabled") == "No" else None),
            "date_created": cols.get("Date Created"),
        }))
    return out, (sch.get("pagination") or {})
def iso2(c):
    if not c: return None
    c=c.upper(); return ISO3.get(c, c if len(c)==2 else c)
def scheme(s):
    s=(s or "").strip(); return SCHEME.get(s.upper(), s.lower() if s else "other")
def valid_mcc(m): return bool(re.match(r"^\d{4}$", str(m or "")))
def drop_empty(d): return {k:v for k,v in d.items() if v not in (None, [], {}, "")}

# Near-global lists (249 countries, ~155 currencies) bloat the LLM pack for almost
# no information. Keep the full list in JSON; renderers use these summaries.
GEO_PROBE=("US","GB","AE","FR","SA","DE","IN","BR","CN","JP")
MAJOR_CUR=("USD","EUR","GBP","AED","SAR","JPY","AUD","CAD","CHF","SEK")
def geo_summary(codes):
    c=sorted({x for x in (codes or []) if x})
    return {"count":len(c),"is_global":len(c)>=240,
            "includes":[x for x in GEO_PROBE if x in c],
            "excludes":[x for x in GEO_PROBE if x not in c]}
def cur_summary(codes):
    c=sorted({x for x in (codes or []) if x})
    return {"count":len(c),
            "majors_present":[x for x in MAJOR_CUR if x in c],
            "majors_absent":[x for x in MAJOR_CUR if x not in c]}
def hal(d, key=None):
    if not isinstance(d, dict): return []
    emb = d.get("_embedded") or {}
    if key and isinstance(emb.get(key), list): return emb[key]
    for v in emb.values():
        if isinstance(v, list): return v
    for k in ("routes","processing_profiles","data","items","entities"):
        if isinstance(d.get(k), list): return d[k]
    return []

# ---------- fetch ----------
def _get(base, token, path, timeout=30, extra_headers=None):
    h = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    h.update(extra_headers or {})
    req = urllib.request.Request(base+path, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8","replace"))
    except urllib.error.HTTPError as e:
        return e.code, {"_error": e.read().decode("utf-8","replace")[:400]}
    except Exception as e:
        return None, {"_error": str(e)}

def list_entities(base, token, client_id):
    st, d = _get(base, token, f"/clients/{client_id}/entities")
    return hal(d, "entities")

def fetch_all(base, token, client_id, entity_id):
    """Fetch everything needed to build ONE entity's profile. Returns a responses dict."""
    R = {"_status": {}}
    def g(key, path):
        st, obj = _get(base, token, path); R["_status"][key]=st
        R[key]=obj; return obj
    g("client", f"/clients/{client_id}")
    R["entities"] = list_entities(base, token, client_id)
    # per-entity detail for a correct entity tree (country/type/status)
    R["entity_details"] = []
    for e in R["entities"]:
        if e.get("id"):
            st, d = _get(base, token, f"/entities/{e['id']}")
            if "_error" not in d: R["entity_details"].append(d)
    g("entity", f"/entities/{entity_id}")
    g("breadcrumb", f"/configuration/breadcrumb?entityId={entity_id}")
    g("services", f"/entities/{entity_id}/services")
    pcs = hal(g("processing_channels_raw", f"/entities/{entity_id}/processing-channels"), "processing_channels")
    profs = hal(g("processing_profiles_raw", f"/entities/{entity_id}/processing-profiles"), "processing_profiles")
    g("apm_pricing_raw", f"/entities/{entity_id}/apm-pricing-profiles")
    g("payout_routes_raw", f"/entities/{entity_id}/payout-routes/v2")
    g("forex_p2c", f"/entities/{entity_id}/forex-pay-to-card")
    g("currency_accounts_raw", f"/entities/{entity_id}/currency-accounts")
    g("risk_entity", f"/entities/{entity_id}/risk-settings")
    pay_rules = hal(g("payment_routing_raw", f"/entities/{entity_id}/payment-routing-rules?limit=25&skip=0"))
    payout_rules = hal(g("payout_routing_raw", f"/entities/{entity_id}/payout-routing-rules?limit=25&skip=0"))
    g("risk_client", f"/clients/{client_id}/risk-settings")
    g("net_tokens", f"/clients/{client_id}/network-tokens")
    # sessions channels carry the 3DS layer (protocol_versions per scheme processor)
    sess = hal(g("sessions_channels_raw", f"/entities/{entity_id}/sessions-processing-channels?limit=25&skip=0"),
               "sessions_processing_channels")
    payout_settings = hal(g("payout_settings_raw", f"/entities/{entity_id}/payout-settings?limit=25&skip=0"),
                          "payout_settings")
    # entity-scoped label dictionaries (id -> human name) for glossing opaque IDs
    g("gloss_payment_routing", f"/payment-routing-rules/configuration?entityId={entity_id}")
    g("gloss_payout_routing", f"/payout-routing-rules/configuration?entityId={entity_id}")
    g("gloss_processors_profiles", f"/entities/{entity_id}/processors/configuration/profiles")

    # Network tokens — client-level, on nt-portal. CAT's own /network-tokens endpoint is a
    # form DEFINITION with null values, so it cannot answer any of this.
    try:
        st, d = _get(NT_BASE, token, f"/cat/configurations/{client_id}")
        R["_status"]["nt_config"] = st
        R["nt_config"] = parse_nt_config(d) if st == 200 else {}
    except Exception as e:
        R["_status"]["nt_config"] = None
        R["nt_config"] = {}

    # Intelligent Acceptance — client-level, fourth internal service.
    try:
        st, d = _get(IA_BASE, token, f"/clients/{client_id}/form")
        R["_status"]["ia_config"] = st
        R["ia_config"] = parse_ia_config(d) if st == 200 else {}
    except Exception:
        R["_status"]["ia_config"] = None
        R["ia_config"] = {}

    # Real Time Account Updater — fifth service, client-level. Needs Content-Type on a GET.
    try:
        st, d = _get(RTAU_BASE, token, f"/cat/configurations/{client_id}/form",
                     extra_headers=RTAU_HEADERS)
        R["_status"]["rtau_config"] = st
        R["rtau_config"] = parse_rtau_config(d) if st == 200 else {}
    except Exception:
        R["_status"]["rtau_config"] = None
        R["rtau_config"] = {}

    # Reporting profiles — different service, different host. Paged; follow it if needed.
    # Wrapped so an unreachable internal host degrades this section only.
    R["reporting_profiles"] = []
    try:
        skip, guard = 0, 0
        while guard < 10:
            st, d = _get(REPORTING_BASE, token,
                         f"/reporting-profiles/table/{entity_id}?skip={skip}")
            R["_status"]["reporting_profiles"] = st
            if st != 200:
                break
            page, pg = parse_reporting_table(d)
            R["reporting_profiles"].extend(page)
            total, limit = pg.get("total") or 0, pg.get("limit") or 0
            skip += (limit or len(page) or 1)
            guard += 1
            if not page or skip >= total:
                break
    except Exception as e:
        R["_status"]["reporting_profiles"] = None
        R["reporting_profiles_error"] = str(e)

    # chained: ALL channel details + ALL profile details (fetch breadth)
    R["channel_details"] = []
    for c in pcs:
        if c.get("id"):
            st, d = _get(base, token, f"/processing-channels/{c['id']}")
            if "_error" not in d: R["channel_details"].append(d)
    R["profile_details"] = []
    for pr in profs:
        if pr.get("id"):
            st, d = _get(base, token, f"/processing-profiles/v2/{pr['id']}")  # v2 carries pay-to-card corridors
            if "_error" not in d: R["profile_details"].append(d)
    # chained: routing-rule detail (list gives CA *names*, detail adds allow_any_payment_method)
    R["payment_rule_details"], R["payout_rule_details"] = [], []
    for r in pay_rules:
        if r.get("id"):
            st, d = _get(base, token, f"/payment-routing-rules/{r['id']}")
            if "_error" not in d: R["payment_rule_details"].append(d)
    for r in payout_rules:
        if r.get("id"):
            st, d = _get(base, token, f"/payout-routing-rules/{r['id']}")
            if "_error" not in d: R["payout_rule_details"].append(d)
    # chained: sessions-channel detail (3DS) + payout-settings detail (instrument/schedule)
    R["sessions_channel_details"] = []
    for s in sess:
        if s.get("id"):
            st, d = _get(base, token, f"/sessions-processing-channels/{s['id']}")
            if "_error" not in d: R["sessions_channel_details"].append(d)
    R["payout_settings_details"] = []
    for ps in payout_settings:
        if ps.get("id"):
            st, d = _get(base, token, f"/entities/{entity_id}/payout-settings/{ps['id']}")
            if "_error" not in d: R["payout_settings_details"].append(d)
    R["processing_channels"] = pcs
    return R

# ---------- normalize ----------
def _clean(o):
    return None if (isinstance(o, dict) and "_error" in o) else o

def normalize(R, environment="sandbox"):
    NOW=_now()
    # Six-state coverage machine. The critical distinction is `empty` (fetched fine,
    # nothing configured — a real negative an LLM may assert) vs `not_collected` /
    # `unavailable` (we don't know — an LLM must say "unknown").
    STATUS=R.get("_status") or {}
    def state_for(deps, has_data):
        if not deps: return "complete" if has_data else "empty"
        codes=[STATUS.get(k) for k in deps]
        if all(c is None for c in codes): return "not_collected"
        ok=[c for c in codes if c==200]
        if not ok: return "unavailable"
        if not has_data: return "empty"
        # some sources answered and some did not -> the section is incomplete, not complete
        return "complete" if len(ok)==len(codes) else "partial"
    def prov(ok, source="cat_internal_api", coverage=None, notes=None):
        p={"as_of":NOW,"source":source,"coverage":coverage or ("complete" if ok else "unknown")}
        if notes:p["notes"]=notes
        return p
    client=_clean(R.get("client")) or {}
    entity=_clean(R.get("entity")) or {}
    entities=R.get("entities") or []
    breadcrumb=_clean(R.get("breadcrumb")) or {}
    services=_clean(R.get("services")) or {}
    pcs=R.get("processing_channels") or []
    chan_details=R.get("channel_details") or []
    apm_pricing=hal(_clean(R.get("apm_pricing_raw")))
    payout_routes=(_clean(R.get("payout_routes_raw")) or {}).get("routes",[]) if _clean(R.get("payout_routes_raw")) else []
    forex_p2c=_clean(R.get("forex_p2c"))
    curr_accts=hal(_clean(R.get("currency_accounts_raw")),"currency_accounts")
    risk_client=_clean(R.get("risk_client")) or {}
    net_tokens=_clean(R.get("net_tokens"))
    # Routing: merge list + detail. The LIST carries the human-readable
    # *_currency_account_name fields; the DETAIL adds allow_any_payment_method and
    # entity_id. Neither alone is complete, so merge without clobbering names.
    def merge_rules(lst, details):
        by_id={d.get("id"):d for d in (details or []) if isinstance(d,dict)}
        out=[]
        for r in lst:
            m=dict(r)
            m.update({k:v for k,v in (by_id.get(r.get("id")) or {}).items() if v is not None})
            out.append(m)
        return out
    pay_routing=merge_rules(hal(_clean(R.get("payment_routing_raw"))), R.get("payment_rule_details"))
    payout_routing=merge_rules(hal(_clean(R.get("payout_routing_raw"))), R.get("payout_rule_details"))
    sess_ok=_clean(R.get("sessions_channels_raw")) is not None
    sess_by_id={d.get("id"):d for d in (R.get("sessions_channel_details") or []) if isinstance(d,dict)}

    profiles=[]
    for d in R.get("profile_details",[]):
        bs=(d.get("business_settings") or [{}])
        cs=d.get("custom_settings") or {}
        aft=cs.get("aft") or {}
        profiles.append({"id":d.get("id"),"name":d.get("processing_profile_name"),
            "type":d.get("processing_type"),"status":d.get("status"),
            "schemes":[scheme(s) for s in (d.get("schemes") or [])],
            "acquirer_key":d.get("acquirer_key"),"processor_key":d.get("processor_key"),
            "acquiring_bin":(str(d.get("acquiring_bin")) if d.get("acquiring_bin") is not None else None),
            "mcc":(bs[0].get("merchant_category_code") if bs else None),
            # every MCC the profile covers, and the currencies it permits — both were
            # being dropped, so "currencies allowed" rendered as "not stated"
            "mccs":sorted({str(b.get("merchant_category_code")) for b in bs
                           if b.get("merchant_category_code") is not None}),
            "currencies":[c for c in (d.get("currencies") or []) if c],
            "caic":(bs[0].get("card_acceptor_identification_code") if bs else None),
            "business_model":d.get("business_model"),
            "ft_type":cs.get("funds_transfer_type"),
            "aft_bai":aft.get("business_application_identifier"),
            "aft_override":aft.get("override_aft_processing"),
            "aft_skip_recipient_name":aft.get("is_skip_recipient_name_enabled"),
            "authorization_validity_period":cs.get("authorization_validity_period"),
            "is_quasi_cash":cs.get("is_quasi_cash"),
            "me_2_me":cs.get("me_2_me_settings"),
            "sca_exemptions":d.get("sca_exemptions_settings"),
            "acceptance_mode":d.get("acceptance_mode"),
            "checkout_legal_entity_code":d.get("checkout_legal_entity_code"),
            "caic":(bs[0].get("card_acceptor_identification_code") if bs else None),
            "acceptor_country":iso2(d.get("card_acceptor_country_code")),
            # AFT recipient controls — these are the only recipient-related settings on a
            # pay-in AFT profile. There are NO corridor country lists on a pay-in profile.
            "recipient_details":cs.get("enable_recipient_details_submission"),
            "origination_countries":sorted({iso2(c) for c in (cs.get("origination_countries") or []) if iso2(c)}),
            "destination_countries":sorted({iso2(c) for c in (cs.get("destination_countries") or []) if iso2(c)})})
    payin=[p for p in profiles if p["type"]=="payin"]
    payout=[p for p in profiles if p["type"]=="payout"]
    active_payout=[p for p in payout if (p.get("status") or "").lower()=="active"]
    # The v2 profile endpoint carries AFT / funds-transfer-type / corridor / auth-hold
    # fields; v1 does not. Without v2 we must report "unknown", never a false negative.
    v2_fidelity=any(p.get("aft_bai") or p.get("ft_type") or p.get("destination_countries")
                    or p.get("authorization_validity_period") is not None for p in profiles)

    cid=client.get("id") or entity.get("client_id"); eid=entity.get("id")
    det_by_id={d.get("id"):d for d in chan_details}
    all_procs=[pr for d in chan_details for pr in (d.get("processors") or [])]

    env={"schema_version":"0.1.0","profile_id":f"prof_{cid}","client_id":cid,
         "snapshot_id":"snap_"+NOW.replace("-","").replace(":","")[:13],
         "generated_at":NOW,"environment":environment,"generator_version":"0.3.0",
         "staleness":{"type":"point_in_time",
            "contract":"Configuration may have changed since generated_at. State the "
                       "snapshot date on config-sensitive answers, and recommend "
                       "regenerating for high-volatility sections."},
         "coverage_summary":{}}

    mccs=sorted({p["mcc"] for p in payin if valid_mcc(p["mcc"])} |
                {str(x["merchant_category_code"]) for x in all_procs if valid_mcc(x.get("merchant_category_code"))})
    identity=drop_empty({"client_name":client.get("name") or entity.get("name"),"legal_name":entity.get("name"),
        "account_type":"platform_payfac" if entity.get("onboards_merchants") else "full",
        "business_model":entity.get("doing_business_as"),"mccs":mccs,
        "operating_regions":[iso2((entity.get("principal_business_address") or {}).get("country_iso3_code"))],
        "go_live_date":(entity.get("date_created") or "")[:10] or None})
    identity["provenance"]=prov(bool(client))

    def caps(): return {"payments":bool(pcs) or bool(payin),"payouts":bool(payout) or bool(payout_routes)}
    # prefer full per-entity detail (has address/type); fall back to list items
    ent_source = R.get("entity_details") or entities or [entity]
    ent_list=[drop_empty({"entity_id":e.get("id"),"name":e.get("name"),"parent_entity_id":e.get("parent_id"),
        "type":{"Legal":"company","Natural":"individual","Individual":"individual"}.get(e.get("type"),"company"),
        "country_of_incorporation":iso2((e.get("principal_business_address") or {}).get("country_iso3_code")),
        "status":(e.get("status") or "").lower() or "unknown",
        # IANA tz from /entities/{id}. Qualifies every wall-clock answer (payout runs,
        # report cut-offs). Absent -> omitted, never defaulted to UTC.
        "timezone":e.get("timezone"),
        "region":e.get("region"),
        "date_created":e.get("date_created"),
        "doing_business_as":e.get("doing_business_as"),
        "display_name":e.get("display_name"),
        # NOT write-only: /entities/{id} does return these. An earlier assessment had them
        # down as uncapturable, which was wrong.
        "processing_urls":e.get("processing_urls") or [],
        # Which Checkout legal entity the merchant contracts with — drives which scheme
        # rules and legal terms apply.
        "cko_legal_entity":e.get("default_cko_legal_entity"),
        "cko_legal_entities":e.get("cko_legal_entities") or [],
        "business_models":e.get("business_models") or [],
        "registered_business_address":drop_empty(e.get("registered_business_address") or {}),
        "principal_business_address":drop_empty(e.get("principal_business_address") or {}),
        "capabilities":caps() if e.get("id")==eid else {}}) for e in ent_source]
    entity_structure=drop_empty({"provenance":prov(bool(entities)),"root_entity_id":breadcrumb.get("entity_id") or eid,
        "root_entity":breadcrumb.get("client_name") or client.get("name"),
        "root_timezone":next((x.get("timezone") for x in ent_list if x.get("entity_id")==eid), None),
        "entities":ent_list})

    # Join a channel processor to an entity processing profile.
    # Key: processor.acquirer_id == profile.acquirer_key, disambiguated by scheme + MCC
    # (acquirer_key alone is ambiguous: cko_visa_gb carries the AFT payin profile at
    #  MCC 0742 and two payout profiles at 6012/4722).
    def match_profile(acq, sch, mcc):
        sch=(sch or "").lower(); mcc=str(mcc) if mcc is not None else None
        exact=[p for p in profiles if p.get("acquirer_key")==acq
               and sch in p["schemes"] and str(p.get("mcc"))==mcc]
        if exact: return exact[0], "exact"
        loose=[p for p in profiles if p.get("acquirer_key")==acq and sch in p["schemes"]]
        if len(loose)==1: return loose[0], "acquirer+scheme"
        return None, None

    FEAT_KEYS=("authorizations","captures","refunds","voids","full_card_api","moto","unreferenced_refunds")
    channels=[]
    for c in pcs:
        det=det_by_id.get(c.get("id"),{}); procs=det.get("processors",[])
        feats=det.get("features") or {}
        proc_rows=[]; aft_hits=[]
        for p in procs:
            mp,how=match_profile(p.get("acquirer_id"),p.get("scheme"),p.get("merchant_category_code"))
            if mp and mp.get("type")=="payin" and mp.get("aft_bai"): aft_hits.append((mp,how))
            curs=sorted({cur for cur in (p.get("processing_currencies") or [])})
            proc_rows.append(drop_empty({
                "processor_id":p.get("id"),"name":p.get("name"),"scheme":scheme(p.get("scheme")),
                "acquirer_id":p.get("acquirer_id"),"acquirer_name":p.get("acquirer_name"),
                "merchant_category_code":(str(p["merchant_category_code"]) if valid_mcc(p.get("merchant_category_code")) else None),
                "processing_currencies":curs,
                "processing_currencies_summary":cur_summary(curs) if curs else None,
                "mode":p.get("mode"),"authorizations":p.get("authorizations"),"captures":p.get("captures"),
                "refunds":p.get("refunds"),"voids":p.get("voids"),"gws_only":p.get("gws_only"),
                "profile_id":(mp or {}).get("id"),"profile_name":(mp or {}).get("name"),
                "profile_type":(mp or {}).get("type"),"profile_match":how}))
        # Pre-computed per-channel verdicts so an LLM never has to join across sections.
        # Tri-state: `enabled` present => known. `enabled` ABSENT => not determinable,
        # and coverage says why. An LLM must never read a missing `enabled` as "no".
        if aft_hits:
            mp,how=aft_hits[0]
            aft_verdict=drop_empty({"enabled":True,"coverage":"complete",
                "profile_id":mp["id"],"profile_name":mp["name"],
                "business_application_identifier":mp.get("aft_bai"),
                "authorization_validity_period":mp.get("authorization_validity_period"),
                "sca_exemptions_settings":mp.get("sca_exemptions"),"match":how})
        elif not v2_fidelity:
            aft_verdict={"coverage":"unavailable",
                "reason":"profile details came from the v1 endpoint; AFT fields (BAI, auth "
                         "hold, SCA exemptions) are absent. Regenerate live to determine."}
        else:
            aft_verdict={"enabled":False,"coverage":"complete",
                "reason":"no AFT-capable payin profile matches this channel's processors"}
        p2c_verdict={"applicable":False,
            "reason":"pay-to-card is entity-scoped — declared by Active payout processing "
                     "profiles; processing channels carry no pay-to-card capability"}
        # 3DS lives on the *sessions* processing channel, which shares the channel's id.
        sd=sess_by_id.get(c.get("id"))
        if sd:
            tds_schemes=[drop_empty({"scheme":scheme(x.get("scheme_id")),
                "acquirer_id":x.get("acquirer_id"),"acquirer_name":x.get("acquirer_name"),
                "merchant_category_code":x.get("merchant_category_code"),
                "protocol_versions":x.get("protocol_versions"),
                "processor_type":x.get("processor_type"),"mode":x.get("mode")})
                for x in (sd.get("processors") or [])]
            three_ds=drop_empty({"enabled":bool(tds_schemes),"coverage":"complete",
                "sessions_channel_id":sd.get("id"),"status":sd.get("status"),
                "schemes":tds_schemes})
        elif sess_ok:
            three_ds={"enabled":False,"coverage":"complete",
                "reason":"no sessions processing channel exists for this channel — 3DS not configured"}
        else:
            three_ds={"coverage":"unavailable",
                "reason":"sessions-processing-channels could not be retrieved"}
        svcs=sorted({s.get("type") for s in (det.get("services") or []) if isinstance(s,dict) and s.get("type")})
        channels.append(drop_empty({"processing_channel_id":c.get("id"),"name":c.get("name"),"entity_id":eid,
            "status":det.get("status") or ("active" if det else "unknown"),
            "business_model_type":det.get("business_model_type"),
            "payment_pricing_profile":det.get("payment_pricing_profile_name"),
            "services":svcs,
            "features":drop_empty({k:feats.get(k) for k in FEAT_KEYS}),
            "schemes_enabled":sorted({scheme(p.get("scheme")) for p in procs}),
            "mids":[drop_empty({"scheme":scheme(p.get("scheme")),"acquiring_bin":p.get("acquirer_id"),
                    "descriptor":p.get("acquirer_name")}) for p in procs],
            "processors":proc_rows,
            "aft":aft_verdict,"pay_to_card":p2c_verdict,"three_ds":three_ds,
            "mccs":sorted({str(p["merchant_category_code"]) for p in procs if valid_mcc(p.get("merchant_category_code"))})}))
    processing_channels={"provenance":prov(bool(pcs)),"channels":channels}

    # entity-level processing profiles (payin + payout), incl. AFT settings (BAI)
    processing_profiles={"provenance":prov(bool(profiles)),
        "profiles":[drop_empty({
            "profile_id":pr["id"],"name":pr["name"],"type":pr["type"],
            "scheme":(pr["schemes"][0] if pr["schemes"] else None),
            "acquirer_key":pr.get("acquirer_key"),"processor_key":pr.get("processor_key"),
            "acquiring_bin":pr.get("acquiring_bin"),"merchant_category_code":pr.get("mcc"),
            # all MCCs the profile covers, its permitted currencies, and its CAIC
            "merchant_category_codes":pr.get("mccs") or [],
            "currencies":pr.get("currencies") or [],
            # corridors live on PAYOUT profiles only; a pay-in AFT profile has none at all
            "origination_countries":pr.get("origination_countries") or [],
            "destination_countries":pr.get("destination_countries") or [],
            # DEFINITIONAL: a pay-in profile carrying a BAI is AFT-enabled. State it rather
            # than leaving the reader to infer it from the presence of the BAI.
            **({"aft_enabled":True} if (pr.get("type")=="payin" and pr.get("aft_bai"))
               else {"aft_enabled":False} if pr.get("type")=="payin" else {}),
            "card_acceptor_identification_code":pr.get("caic"),
            "business_model":pr.get("business_model"),"funds_transfer_type":pr.get("ft_type"),
            "card_acceptor_country_code":pr.get("acceptor_country"),
            "enable_recipient_details_submission":pr.get("recipient_details"),
            "aft":drop_empty({"business_application_identifier":pr.get("aft_bai"),
                "override_aft_processing":pr.get("aft_override"),
                "is_skip_recipient_name_enabled":pr.get("aft_skip_recipient_name")}),
            "authorization_validity_period":pr.get("authorization_validity_period"),
            "is_quasi_cash":pr.get("is_quasi_cash"),
            "me_2_me_settings":pr.get("me_2_me"),
            "sca_exemptions_settings":pr.get("sca_exemptions"),
            "acceptance_mode":pr.get("acceptance_mode"),"status":pr.get("status")}) for pr in profiles]}

    card_schemes=sorted({scheme(p.get("scheme")) for p in all_procs if scheme(p.get("scheme")) in CARD} |
                        {s for p in payin for s in p["schemes"] if s in CARD})
    apms=sorted({s for p in payin for s in p["schemes"] if s not in CARD})
    scheme_enablement={"provenance":prov(bool(profiles) or bool(all_procs)),
        "card_schemes":[{"scheme":s,"enabled":True} for s in card_schemes],
        "alternative_payment_methods":[{"name":a,"enabled":True} for a in apms]}

    p2c_processors=[drop_empty({"profile_id":p["id"],"name":p["name"],
        "scheme":(p["schemes"][0] if p["schemes"] else None),"acquiring_bin":p["acquiring_bin"],
        "merchant_category_code":p["mcc"],"card_acceptor_identification_code":p.get("caic"),
        "funds_transfer_type":p.get("ft_type"),"business_model":p["business_model"],
        "acceptance_mode":p.get("acceptance_mode"),"checkout_legal_entity_code":p.get("checkout_legal_entity_code"),
        "status":p["status"],
        "origination_countries":p.get("origination_countries") or [],
        "destination_countries":p.get("destination_countries") or []}) for p in payout]
    p2c_origin=sorted({c for p in active_payout for c in (p.get("origination_countries") or [])})
    p2c_dest=sorted({c for p in active_payout for c in (p.get("destination_countries") or [])})
    p2c_ft=sorted({p["ft_type"] for p in active_payout if p.get("ft_type")})
    # payout routes: keep the per-corridor scheme/fee_type detail we were collapsing away
    enabled_routes=[r for r in payout_routes if r.get("enabled")]
    route_rows=[drop_empty({"country":iso2(r.get("country")),"currency":r.get("currency"),
        "schemes":[drop_empty({"name":s.get("name"),"fee_type":s.get("fee_type")})
                   for s in (r.get("schemes") or [])]}) for r in enabled_routes]
    money_out={"provenance":prov(bool(payout_routes) or bool(payout)),
        "pay_to_card":drop_empty({"enabled":bool(active_payout),
            "scope":"entity",
            "enabled_schemes":sorted({s for p in active_payout for s in p["schemes"]}),
            "supported_mccs":sorted({p["mcc"] for p in active_payout if p["mcc"]}),
            "ft_types":p2c_ft,"origination_countries":p2c_origin,"destination_countries":p2c_dest,
            "origination_summary":geo_summary(p2c_origin) if p2c_origin else None,
            "destination_summary":geo_summary(p2c_dest) if p2c_dest else None,
            "processors":p2c_processors}),
        "payout_routes":route_rows,
        "payout_routes_summary":{"enabled":len(enabled_routes),"total":len(payout_routes)},
        "payout_destinations":[drop_empty({"type":"bank_account",
            "countries":sorted({iso2(r.get("country")) for r in enabled_routes}),
            "currencies":sorted({r.get("currency") for r in enabled_routes})})]}
    if forex_p2c:
        money_out["forex"]={"pay_to_card_forex_enabled":True,"coverage":"complete"}
    elif STATUS.get("forex_p2c")==404:
        money_out["forex"]={"pay_to_card_forex_enabled":False,"coverage":"empty",
            "reason":"no pay-to-card forex configuration exists for this entity"}
    else:
        money_out["forex"]={"coverage":"unavailable",
            "reason":"forex-pay-to-card could not be retrieved"}

    # Payout instructions carry FULL BANK DETAILS. Never emit account numbers into an
    # LLM context pack — surface existence/type/currency/bank name and list what was
    # redacted, so the omission is explicit rather than silent.
    SENSITIVE=("account_number","iban","bic","swift_code","sort_code","routing_number","bank_code")
    def safe_instrument(pi):
        if not isinstance(pi,dict): return None
        bd=pi.get("bank_details") or {}
        return drop_empty({"instrument_id":pi.get("id"),
            "instrument_type":pi.get("instrument_type"),"currency":pi.get("currency_code"),
            "vault_account_id":pi.get("vault_account_id"),
            "account_holder":(pi.get("account_holder_details") or {}).get("company_name"),
            "bank_name":bd.get("bank_name"),"branch_name":bd.get("branch_name"),
            "account_type":bd.get("account_type"),
            "redacted_fields":[k for k in SENSITIVE if bd.get(k)]})
    payout_instructions=[]
    for ps in (R.get("payout_settings_details") or []):
        if not isinstance(ps,dict): continue
        sch=ps.get("payout_schedule") or {}
        payout_instructions.append(drop_empty({
            "instruction_id":sch.get("id") or ps.get("id"),
            "name":(sch.get("name") or "").strip() or None,
            # date_created was being dropped; it is on the record and worth reporting
            "date_created":sch.get("date_created"),
            "date_modified":sch.get("date_modified"),
            "instrument":safe_instrument(ps.get("payment_instrument")),
            # DERIVED from the cron — CAT publishes no frequency field. Labelled as derived
            # wherever it is rendered.
            "frequency_derived":cron_frequency(sch.get("cron_schedule")),
            "schedule":drop_empty({k:v for k,v in sch.items()
                                   if k not in ("id","name","date_created","date_modified","version")})}))
    settlement={"provenance":prov(bool(curr_accts)),
        "settlement_currencies":sorted({a.get("holding_currency") for a in curr_accts if a.get("holding_currency")}),
        # NO entity_id here. /entities/{eid}/currency-accounts returns accounts that are
        # NOT all owned by that entity (it has returned another merchant's account), and
        # nothing in CAT — not this list, not the per-account GET, not the entity-scoped
        # routing config — states which entity owns one. Stamping `eid` on each row
        # fabricated an ownership fact and made a wrong filter look verified.
        "currency_accounts":[drop_empty({"currency_account_id":a.get("id"),"currency":a.get("holding_currency"),
            "name":a.get("name"),"status":(a.get("status") or "").lower()}) for a in curr_accts]}
    if payout_instructions: settlement["payout_instructions"]=payout_instructions

    # Routing rules: the list response already carries the conditions and the
    # currency-account targets. `enabled` does NOT exist on these objects — the real
    # field is `status` ("Active"). Never fabricate it.
    ALLOW_KEYS=("allow_any_processing_channel","allow_any_merchant_category_code",
                "allow_any_processing_currency","allow_any_event_type","allow_any_card_type",
                "allow_any_region","allow_any_banking_partner","allow_any_payment_method")
    def rule(r):
        conds={k:r[k] for k in ALLOW_KEYS if k in r}
        out={"rule_id":r.get("id"),"name":r.get("name"),"status":r.get("status"),
             "entity_id":r.get("entity_id"),"sub_entity_id":r.get("sub_entity_id"),
             "source_identifier":r.get("source_identifier"),
             "revenue_currency_account_id":r.get("revenue_currency_account_id"),
             "revenue_currency_account_name":r.get("revenue_currency_account_name"),
             "fees_currency_account_id":r.get("fees_currency_account_id"),
             "fees_currency_account_name":r.get("fees_currency_account_name"),
             "date_modified":r.get("date_modified")}
        if conds:
            out["conditions"]=conds
            # pre-computed answer: does this rule restrict anything at all?
            out["unrestricted"]=all(bool(v) for v in conds.values())
        return drop_empty(out)
    routing={"provenance":prov(bool(pay_routing) or bool(payout_routing)),
        "payment_routing_rules":[rule(r) for r in pay_routing],
        "payout_routing_rules":[rule(r) for r in payout_routing]}

    # derived auth-hold (authorization validity) per scheme, from processing profiles
    auth_by_scheme={}
    for pr in profiles:
        d=pr.get("authorization_validity_period")
        if d is not None:
            s=(pr["schemes"][0] if pr["schemes"] else "other")
            auth_by_scheme.setdefault(s,set()).add(d)
    auth_holds={s:sorted(v) for s,v in sorted(auth_by_scheme.items())}

    gaps=[]
    if "amex" not in card_schemes: gaps.append("Amex not enabled for acceptance.")
    if not active_payout: gaps.append("No active pay-to-card (payout) processing profiles found.")
    capabilities_matrix={"provenance":prov(True,source="derived"),
        "accept_payments":{"countries":sorted({iso2((entity.get('principal_business_address') or {}).get('country_iso3_code'))}-{None}),
            "schemes":card_schemes,
            "currencies":sorted({cur for p in all_procs for cur in (p.get("processing_currencies") or [])})[:30]},
        "pay_to_card":drop_empty({"enabled":bool(active_payout),
            "schemes":sorted({s for p in active_payout for s in p["schemes"]}),
            "ft_types":p2c_ft,"origination_countries":p2c_origin,"destination_countries":p2c_dest,
            "supported_mccs":sorted({p["mcc"] for p in active_payout if p["mcc"]})}),
        "notable_gaps":gaps}
    if auth_holds:
        capabilities_matrix["authorization"]={"hold_days_by_scheme":auth_holds}

    # WAS: {"network_tokens": bool(net_tokens)} — net_tokens is the response OBJECT, which
    # always contains schema+endpoints, so bool() was always True. That reported network
    # tokens as enabled for every merchant regardless of configuration. The real value is
    # nt_state from nt-portal.
    nt_cfg = R.get("nt_config") or {}
    risk_and_auth={"provenance":prov(bool(risk_client)),
        # Network Tokens and Intelligent Acceptance are DISTINCT value-added services:
        # separate products, separate services/endpoints, separate configuration. They were
        # previously bundled under one `auth_optimization` object, which presented them as
        # two flags of a single thing. Each stands alone.
        "network_tokens":nt_cfg,
        "intelligent_acceptance":R.get("ia_config") or {},
        # Fifth distinct value-added service. Separate product, separate service.
        "real_time_account_updater":R.get("rtau_config") or {}}
    if risk_client.get("tier"): risk_and_auth["fraud_tooling"]=[f"risk_tier:{risk_client['tier']}"]

    integ=[]
    if (services.get("flow_account") or {}).get("is_enabled"): integ.append("flow")
    integ.append("direct_api")
    rprofiles = R.get("reporting_profiles") or []
    rp_status = (R.get("_status") or {}).get("reporting_profiles")
    reporting_and_integration={"provenance":prov(True,coverage="partial",
        notes="webhooks/workflows come from the public API; reporting profiles from the "
              "merlin reporting-profiles-config-api (separate internal service)"),
        "integration_types":sorted(set(integ)),
        "reporting_profiles":rprofiles,
        # explicit so a renderer can tell "none configured" from "could not read"
        "reporting_profiles_coverage":("complete" if rp_status==200 and rprofiles else
                                       "empty" if rp_status==200 else "unavailable")}

    # Glossary: entity-scoped id -> human name, from the configuration?entityId
    # endpoints. Without this, routing reads "revenue -> ca_xd7v5anhc7kuhgy4qvaasvo3ei".
    def gloss_pairs(obj, keys):
        out={}
        for k in keys:
            for it in ((obj or {}).get(k) or []):
                if isinstance(it,dict) and it.get("value") and it.get("label"):
                    out[str(it["value"])]=it["label"]
        return out
    gl={}
    gl.update(gloss_pairs(_clean(R.get("gloss_payment_routing")),
        ("processing_channels","currency_accounts","event_types","card_types",
         "regions","banking_partners","payment_methods")))
    gl.update(gloss_pairs(_clean(R.get("gloss_payout_routing")), ("currency_accounts",)))
    gl.update(gloss_pairs(_clean(R.get("gloss_processors_profiles")), ("processing_profiles",)))
    glossary={"provenance":prov(bool(gl),
        notes="entity-scoped id->name dictionary from configuration?entityId endpoints"),
        "ids":dict(sorted(gl.items()))}

    profile={"envelope":env,"identity":identity,"entity_structure":entity_structure,
        "processing_channels":processing_channels,"processing_profiles":processing_profiles,
        "scheme_enablement":scheme_enablement,
        "money_out":money_out,"settlement":settlement,"routing":routing,
        "capabilities_matrix":capabilities_matrix,"risk_and_auth":risk_and_auth,
        "reporting_and_integration":reporting_and_integration,"glossary":glossary}
    # ---- Phase 3: coverage state, volatility, determinism ----
    SECTION_DEPS={"identity":["client"],"entity_structure":["entity"],
        "processing_channels":["processing_channels_raw"],
        "processing_profiles":["processing_profiles_raw"],
        "scheme_enablement":["processing_profiles_raw"],
        "money_out":["payout_routes_raw","processing_profiles_raw"],
        "settlement":["currency_accounts_raw","payout_settings_raw"],
        "routing":["payment_routing_raw","payout_routing_raw"],
        "risk_and_auth":["risk_client"],"glossary":["gloss_payment_routing"]}
    # How fast each area drifts — tells an LLM which facts to caveat harder as the
    # snapshot ages.
    VOLATILITY={"identity":"low","entity_structure":"low","settlement":"low","glossary":"low",
        "processing_channels":"medium","processing_profiles":"medium","scheme_enablement":"medium",
        "money_out":"medium","capabilities_matrix":"medium","risk_and_auth":"medium",
        "routing":"high","reporting_and_integration":"high"}
    for sec,body in profile.items():
        if sec=="envelope" or not isinstance(body,dict): continue
        pv=body.get("provenance")
        if not isinstance(pv,dict): continue
        if sec in SECTION_DEPS:
            has=any(bool(v) for k,v in body.items() if k!="provenance")
            pv["coverage"]=state_for(SECTION_DEPS[sec],has)
        if sec in VOLATILITY: pv["volatility"]=VOLATILITY[sec]
    # Snapshots are a series — sort by stable id so two packs diff cleanly even if
    # the API returns collections in a different order.
    processing_channels["channels"].sort(key=lambda c:c.get("processing_channel_id") or "")
    processing_profiles["profiles"].sort(key=lambda p:p.get("profile_id") or "")
    for k in ("payment_routing_rules","payout_routing_rules"):
        routing[k].sort(key=lambda r:r.get("rule_id") or "")
    # Areas CAT does not expose at all — stated explicitly so an LLM never guesses.
    env["not_available"]={
        # reporting profiles ARE readable, from merlin's reporting-profiles-config-api.
        # Only declare them unavailable when that call did not succeed.
        **({} if (R.get("_status") or {}).get("reporting_profiles")==200 else
           {"reporting_profiles":{"state":"unavailable",
            "reason":"reporting-profiles-config-api unreachable or unauthorised "
                     "(internal host; needs corporate network) — check the Dashboard"}}),
        "velocity_limits":{"state":"not_available","reason":"not exposed by the CAT API"},
        # Corridors ARE readable — from payout profile custom_settings, one FT type per
        # profile, so per-FT-type corridors resolve. Only declare them unavailable when no
        # payout profile actually carries any. Asserting the gap unconditionally made the
        # document tell the reader to answer "unknown" about the corridors it had printed.
        **({} if any((x.get("origination_countries") or x.get("destination_countries"))
                     for x in processing_profiles["profiles"] if x.get("type")=="payout") else
           {"pay_to_card_ft_corridors":{"state":"unavailable",
            "reason":"CAT pay-to-card-schemes endpoint returns 503 and no payout profile "
                     "carries origination or destination countries"}}),
        "pricing":{"state":"excluded","reason":"commercially sensitive"},
        "bank_account_numbers":{"state":"redacted","reason":"policy — instrument type, "
                     "currency and bank name are surfaced instead"}}
    env["coverage_summary"]={sec:(profile[sec].get("provenance",{}) or {}).get("coverage","unknown")
        for sec in ["identity","entity_structure","processing_channels","processing_profiles","scheme_enablement",
                    "money_out","settlement","routing","capabilities_matrix","risk_and_auth",
                    "reporting_and_integration","glossary"]}
    return profile

# ---------- public-API enrichment (best effort) ----------
def enrich_public_api(profile, sk, pub_base="https://api.sandbox.checkout.com"):
    """Populate webhook subscriptions from the public Workflows API (sk auth)."""
    if not sk: return profile
    st, d = _get(pub_base, sk, "/workflows")
    if st != 200 or not isinstance(d, dict): return profile
    workflows = d.get("data") or []
    events, endpoints, wf_list = set(), set(), []
    for w in workflows:
        # Keep events/endpoints/scopes PER WORKFLOW. Unioning them across workflows
        # (as this used to) destroys the mapping and makes "summarise my webhook
        # setup" unanswerable.
        rec = {"id": w.get("id"), "name": w.get("name"), "active": w.get("active")}
        sd_st, det = _get(pub_base, sk, f"/workflows/{rec['id']}")
        if sd_st == 200 and isinstance(det, dict):
            wf_events, scopes = set(), []
            for c in det.get("conditions") or []:
                ev = c.get("events")
                if isinstance(ev, dict):
                    for src, evs in ev.items():
                        for e in (evs or []): wf_events.add(f"{src}.{e}")
                elif isinstance(ev, list):
                    for e in ev: wf_events.add(e)
                # non-event conditions scope the workflow (entity / processing_channel)
                if (c.get("type") or "") != "event":
                    sc = drop_empty({k: v for k, v in c.items() if k != "events"})
                    if len(sc) > 1: scopes.append(sc)
            wf_eps = sorted({a["url"] for a in (det.get("actions") or []) if a.get("url")})
            rec.update({"events": sorted(wf_events), "event_count": len(wf_events),
                        "endpoints": wf_eps, "scopes": scopes})
            events |= wf_events; endpoints |= set(wf_eps)
        wf_list.append(drop_empty(rec))
    ri = profile["reporting_and_integration"]
    if wf_list: ri["workflows"] = wf_list
    if events: ri["webhook_subscriptions"] = sorted(events)
    if endpoints: ri["webhook_endpoints"] = sorted(endpoints)
    new_cov = "complete" if events else ri.get("provenance",{}).get("coverage","partial")
    ri["provenance"] = {**ri.get("provenance", {}), "coverage": new_cov, "notes": "webhooks/workflows via public API (sk)"}
    # keep the envelope summary in sync (it was computed before enrichment)
    profile.setdefault("envelope", {}).setdefault("coverage_summary", {})["reporting_and_integration"] = new_cov
    return profile

# ---------- renderers ----------
def render_md(p):
    env,idn=p["envelope"],p.get("identity",{})
    def cov(s):return (p.get(s,{}).get("provenance",{}) or {}).get("coverage","unknown")
    def yn(b):return "✅" if b else "❌"
    m=[f"# Checkout.com Configuration Profile — {idn.get('client_name','?')}",
       f"\n> **Generated:** {env['generated_at']} · **Env:** {env['environment']} · **Client:** `{env.get('client_id','')}`\n"]
    m+=["## 1. Business profile",f"- **Account type:** {idn.get('account_type','?')}"]
    if idn.get("business_model"):m.append(f"- **Doing business as:** {idn['business_model']}")
    if idn.get("mccs"):m.append(f"- **MCCs:** {', '.join(idn['mccs'])}")
    if idn.get("operating_regions"):m.append(f"- **Regions:** {', '.join(x for x in idn['operating_regions'] if x)}")
    es=p.get("entity_structure",{})
    m+=["\n## 2. Entity structure","| Entity | ID | Incorp. | Payments | Payouts | Status |","|---|---|---|---|---|---|"]
    for e in es.get("entities",[]):
        c=e.get("capabilities",{})
        m.append(f"| {e.get('name','')} | `{e.get('entity_id','')}` | {e.get('country_of_incorporation','')} | "
                 f"{yn(c.get('payments')) if c else '—'} | {yn(c.get('payouts')) if c else '—'} | {e.get('status','')} |")
    m.append(f"\n## 3. Processing channels  _(coverage: {cov('processing_channels')})_")
    for ch in p.get("processing_channels",{}).get("channels",[]):
        m.append(f"- **{ch.get('name','')}** (`{ch.get('processing_channel_id','')}`) — {ch.get('status','?')}"
                 + (f" · {ch['business_model_type']}" if ch.get('business_model_type') else "")
                 + (f" · pricing: {ch['payment_pricing_profile']}" if ch.get('payment_pricing_profile') else ""))
        if ch.get("schemes_enabled"):m.append(f"  - Methods: {', '.join(ch['schemes_enabled'])}")
        if ch.get("mccs"):m.append(f"  - MCCs: {', '.join(ch['mccs'])}")
        f=ch.get("features") or {}
        if f:m.append("  - Features: "+", ".join(f"{k}={v}" for k,v in f.items()))
        for pr in ch.get("processors",[]):
            m.append(f"  - proc {pr.get('name','')}: {pr.get('scheme','')} / {pr.get('acquirer_name') or pr.get('acquirer_id','')}, "
                     f"MCC {pr.get('merchant_category_code','—')}, mode {pr.get('mode','—')}, "
                     f"auth={pr.get('authorizations','—')}/cap={pr.get('captures','—')}/ref={pr.get('refunds','—')}/void={pr.get('voids','—')}, "
                     f"currencies: {', '.join(pr.get('processing_currencies',[])) or '—'}")
    pp=p.get("processing_profiles",{})
    if pp.get("profiles"):
        m.append(f"\n## 3b. Processing profiles  _(coverage: {cov('processing_profiles')})_")
        for pr in pp["profiles"]:
            a=pr.get("aft") or {}
            extra=[]
            if pr.get("funds_transfer_type"): extra.append(f"FT {pr['funds_transfer_type']}")
            if a.get("business_application_identifier"): extra.append(f"AFT BAI {a['business_application_identifier']}")
            if pr.get("authorization_validity_period") is not None: extra.append(f"auth {pr['authorization_validity_period']}d")
            if pr.get("is_quasi_cash"): extra.append("quasi-cash")
            sca=pr.get("sca_exemptions_settings") or {}
            en=[k.replace("enable_","") for k,v in sca.items() if v]
            if en: extra.append("SCA: "+", ".join(en))
            m.append(f"- **{pr.get('name','')}** ({pr.get('type','')}): {pr.get('scheme','')} / {pr.get('acquirer_key','')}, "
                     f"BIN {pr.get('acquiring_bin','—')}, MCC {pr.get('merchant_category_code','—')}, {pr.get('status','')}"
                     + (", "+", ".join(extra) if extra else ""))
    se=p.get("scheme_enablement",{})
    m+=["\n## 4. Scheme & payment-method enablement",
        f"- **Card schemes:** {', '.join(s['scheme'] for s in se.get('card_schemes',[])) or '—'}",
        f"- **APMs:** {', '.join(a['name'] for a in se.get('alternative_payment_methods',[])) or '—'}"]
    mo=p.get("money_out",{});p2c=mo.get("pay_to_card",{})
    def geo(codes):
        codes=codes or []
        flags=" ".join(f"{c}={'✅' if c in codes else '❌'}" for c in ("US","GB","AE"))
        return f"{len(codes)} countries ({flags})" if codes else "—"
    m.append(f"\n## 5. Money-out / payouts  _(coverage: {cov('money_out')})_")
    m.append(f"- **Pay-to-card:** {yn(p2c.get('enabled'))} enabled")
    if p2c.get("enabled_schemes"):m.append(f"  - Schemes: {', '.join(p2c['enabled_schemes'])} · FT types: {', '.join(p2c.get('ft_types',[])) or '—'} · MCCs: {', '.join(p2c.get('supported_mccs',[]))}")
    if p2c.get("destination_countries") is not None and p2c.get("enabled"):
        m.append(f"  - Origination: {geo(p2c.get('origination_countries'))}")
        m.append(f"  - Destination: {geo(p2c.get('destination_countries'))}")
    for pr in p2c.get("processors",[]):
        m.append(f"  - {pr.get('name','')}: {pr.get('scheme','')}, FT {pr.get('funds_transfer_type','?')}, BIN {pr.get('acquiring_bin','')}, MCC {pr.get('merchant_category_code','')}, dest {len(pr.get('destination_countries',[]))}, {pr.get('status','')}")
    st=p.get("settlement",{})
    m.append(f"\n## 6. Settlement  _(coverage: {cov('settlement')})_")
    if st.get("settlement_currencies"):m.append(f"- **Currencies:** {', '.join(st['settlement_currencies'])}")
    cm=p.get("capabilities_matrix",{});ap=cm.get("accept_payments",{});cp=cm.get("pay_to_card",{})
    acc_s=", ".join(ap.get("schemes",[])) or "none (card)"
    acc_c=", ".join(ap.get("countries",[])) or "—"
    p2c_line=(f"✅ — {', '.join(cp.get('schemes',[]))}, MCCs {', '.join(cp.get('supported_mccs',[]))}"
              if cp.get("enabled") else "❌ not enabled")
    holds=(cm.get("authorization") or {}).get("hold_days_by_scheme") or {}
    holds_str=", ".join(f"{k} {'/'.join(str(x) for x in v)}d" for k,v in holds.items()) if holds else ""
    m+=["\n## 7. Capabilities matrix (derived)",
        f"- **Accept:** {acc_s} in {acc_c}",
        f"- **Pay-to-card:** {p2c_line}"]
    if holds_str: m.append(f"- **Auth hold (per scheme):** {holds_str}")
    if cm.get("notable_gaps"):
        m.append("- ⚠️ **Gaps:**"); [m.append(f"  - {g}") for g in cm["notable_gaps"]]
    ri=p.get("reporting_and_integration",{})
    m.append(f"\n## 8. Reporting & integration  _(coverage: {cov('reporting_and_integration')})_")
    m.append(f"- **Integration:** {', '.join(ri.get('integration_types',[]))}")
    if ri.get("workflows"): m.append(f"- **Workflows:** {', '.join((w.get('name') or w.get('id','')) for w in ri['workflows'])}")
    if ri.get("webhook_subscriptions"):m.append(f"- **Webhook events:** {', '.join(ri['webhook_subscriptions'][:24])}")
    if ri.get("webhook_endpoints"):m.append(f"- **Webhook endpoints:** {', '.join(ri['webhook_endpoints'][:5])}")
    return "\n".join(m)+"\n"

def render_llms(p):
    env,idn=p["envelope"],p.get("identity",{})
    se=p.get("scheme_enablement",{});mo=p.get("money_out",{});p2c=mo.get("pay_to_card",{});st=p.get("settlement",{});pc=p.get("processing_channels",{})
    es=p.get("entity_structure",{});rt=p.get("routing",{});ra=p.get("risk_and_auth",{})
    L=[f"# Checkout.com setup — {idn.get('client_name','?')} (as of {env['generated_at']}, {env['environment'].upper()})",
       "# Describes THIS merchant's CKO config. Answer against it; if absent and coverage unknown/partial, say so.",
       f"ACCOUNT: {idn.get('account_type','?')}, business_model={idn.get('business_model','-')}, MCCs {', '.join(idn.get('mccs',[]))}. Regions {', '.join(x for x in idn.get('operating_regions',[]) if x)}.",
       f"CARD SCHEMES: {', '.join(s['scheme'] for s in se.get('card_schemes',[]))}. APMs: {', '.join(a['name'] for a in se.get('alternative_payment_methods',[]))}."]
    for e in es.get("entities",[]):
        c=e.get("capabilities") or {}
        L.append(f"ENTITY {e.get('name','')} ({e.get('entity_id','')}): country={e.get('country_of_incorporation','')}, type={e.get('type','')}, "
                 f"payments={c.get('payments') if c else '?'}, payouts={c.get('payouts') if c else '?'}, status={e.get('status','')}")
    # processing channels + per-processor detail
    for ch in pc.get("channels",[]):
        feats=", ".join(f"{k}={v}" for k,v in (ch.get("features") or {}).items())
        L.append(f"CHANNEL {ch.get('name','')} ({ch.get('processing_channel_id','')}): status={ch.get('status','')}, "
                 f"business_model={ch.get('business_model_type','-')}, services={', '.join(ch.get('services',[])) or '-'}, features: {feats or '-'}")
        for pr in ch.get("processors",[]):
            L.append(f"  processor {pr.get('name','')}: scheme={pr.get('scheme','')}, acquirer={pr.get('acquirer_name') or pr.get('acquirer_id','')}, "
                     f"mcc={pr.get('merchant_category_code','-')}, mode={pr.get('mode','-')}, auth={pr.get('authorizations','-')}, "
                     f"cap={pr.get('captures','-')}, ref={pr.get('refunds','-')}, void={pr.get('voids','-')}, gws_only={pr.get('gws_only','-')}, "
                     f"currencies: {', '.join(pr.get('processing_currencies',[])) or '-'}")
        if not ch.get("processors"): L.append("  (no processors)")
    # entity-level processing profiles incl AFT BAI
    for pr in (p.get("processing_profiles",{}).get("profiles",[])):
        a=pr.get("aft") or {}
        sca=pr.get("sca_exemptions_settings") or {}
        en=",".join(k.replace("enable_","") for k,v in sca.items() if v)
        L.append(f"PROFILE {pr.get('name','')} ({pr.get('type','')}): scheme={pr.get('scheme','')}, acquirer={pr.get('acquirer_key','')}, "
                 f"bin={pr.get('acquiring_bin','-')}, mcc={pr.get('merchant_category_code','-')}, "
                 f"ft_type={pr.get('funds_transfer_type','-')}, aft_bai={a.get('business_application_identifier','-')}, "
                 f"auth_validity={pr.get('authorization_validity_period','-')}, quasi_cash={pr.get('is_quasi_cash','-')}, "
                 f"sca_exemptions={en or '-'}, status={pr.get('status','')}")
    L.append(f"PAY-TO-CARD: enabled={p2c.get('enabled')}. schemes={', '.join(p2c.get('enabled_schemes',[]))}. ft_types={', '.join(p2c.get('ft_types',[]))}. mccs={', '.join(p2c.get('supported_mccs',[]))}.")
    if p2c.get("origination_countries"): L.append(f"P2C ORIGINATION ({len(p2c['origination_countries'])}): {', '.join(p2c['origination_countries'])}")
    if p2c.get("destination_countries"): L.append(f"P2C DESTINATION ({len(p2c['destination_countries'])}): {', '.join(p2c['destination_countries'])}")
    for pr in p2c.get("processors",[]):
        L.append(f"  p2c {pr.get('name','')}: {pr.get('scheme','')}, FT {pr.get('funds_transfer_type','?')}, BIN {pr.get('acquiring_bin','')}, MCC {pr.get('merchant_category_code','')}, {pr.get('status','')}")
    holds=(p.get("capabilities_matrix",{}).get("authorization") or {}).get("hold_days_by_scheme") or {}
    if holds: L.append("AUTH HOLD (days per scheme): "+", ".join(f"{k}={'/'.join(str(x) for x in v)}" for k,v in holds.items()))
    dests=mo.get("payout_destinations",[])
    if dests and dests[0].get("countries"): L.append(f"PAYOUT BANK: countries={', '.join(dests[0]['countries'])}, currencies={', '.join(dests[0].get('currencies',[]))}")
    accts="; ".join(f"{a.get('currency')}({a.get('status')})" for a in st.get('currency_accounts',[]))
    L.append(f"SETTLEMENT: currencies {', '.join(st.get('settlement_currencies',[]))}. accounts: {accts or '-'}")
    tds=ra.get("three_ds") or {}
    L.append(f"NETWORK TOKENS: allowed={(ra.get('network_tokens') or {}).get('allowed')}, "
             f"mode={(ra.get('network_tokens') or {}).get('provisioning_mode')}")
    L.append(f"INTELLIGENT ACCEPTANCE: enabled={(ra.get('intelligent_acceptance') or {}).get('enabled')}, "
             f"strategy={(ra.get('intelligent_acceptance') or {}).get('strategy_label')}")
    L.append(f"RISK: fraud_tooling={', '.join(ra.get('fraud_tooling',[])) or '-'}"+(f", 3ds={tds}" if tds else ""))
    prr=rt.get("payment_routing_rules",[]); por=rt.get("payout_routing_rules",[])
    if prr or por:
        L.append(f"ROUTING: payment_rules={len(prr)}, payout_rules={len(por)}")
        for r in prr: L.append(f"  payment-routing {r.get('name','')} ({r.get('rule_id','')}): enabled={r.get('enabled')}")
        for r in por: L.append(f"  payout-routing {r.get('name','')} ({r.get('rule_id','')}): enabled={r.get('enabled')}")
    ri=p.get("reporting_and_integration",{})
    # reporting_profiles used to be a list of strings (always empty). It is now a list of
    # dicts from the reporting-profiles-config-api, so it cannot be str.join'd directly.
    _rp = ri.get("reporting_profiles") or []
    _rp_txt = ", ".join(
        (r.get("name") or r.get("profile_id") or "?") + ("" if r.get("enabled") else " (off)")
        if isinstance(r, dict) else str(r) for r in _rp) or "-"
    L.append(f"INTEGRATION: types={', '.join(ri.get('integration_types',[])) or '-'}, "
             f"reporting_profiles={_rp_txt}")
    if ri.get("workflows"): L.append("WORKFLOWS: "+", ".join(f"{w.get('name')}({'active' if w.get('active') else 'inactive'})" for w in ri['workflows']))
    if ri.get("webhook_subscriptions"): L.append(f"WEBHOOK EVENTS: {', '.join(ri['webhook_subscriptions'])}")
    if ri.get("webhook_endpoints"): L.append("WEBHOOK ENDPOINTS: "+", ".join(ri['webhook_endpoints']))
    L.append("COVERAGE: "+", ".join(f"{k}={v}" for k,v in env.get("coverage_summary",{}).items()))
    if p.get("capabilities_matrix",{}).get("notable_gaps"):
        L.append("GAPS: "+" | ".join(p["capabilities_matrix"]["notable_gaps"]))
    return "\n".join(L)+"\n"
