#!/usr/bin/env python3
"""
Generate full merchant profiles (JSON + .md + llms.txt) from the CAT API — one per
entity under a client, using the full-breadth engine (all channels, all profiles,
per-entity detail).

Live fetch (default):
  BASE_URL=... TOKEN=... CLIENT_ID=cli_... [ENTITY_ID=ent_...] python3 cat-api/generate_profile.py

  - ENTITY_ID set   -> just that entity
  - ENTITY_ID unset -> every entity under the client

Offline (rebuild from a previously saved responses dir):
  python3 cat-api/generate_profile.py --offline cat-api/responses

Output: samples/<entity_id>/{merchant-profile.json,merchant-profile.md,llms.txt}
"""
import os, sys, json, glob, pathlib

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "app"))
import cat_profile as cp
from jsonschema import Draft202012Validator

SCHEMA = json.load(open(ROOT / "schema" / "merchant-profile.schema.json"))

def write_profile(prof, sk=None):
    if sk: prof = cp.enrich_public_api(prof, sk)
    errs = sorted(Draft202012Validator(SCHEMA).iter_errors(prof), key=lambda e: list(e.path))
    slug = (prof["envelope"].get("client_id") or "profile")
    eid  = prof["entity_structure"].get("root_entity_id") or slug
    out = ROOT / "samples" / eid
    out.mkdir(parents=True, exist_ok=True)
    (out / "merchant-profile.json").write_text(json.dumps(prof, indent=2))
    (out / "merchant-profile.md").write_text(cp.render_md(prof))
    (out / "llms.txt").write_text(cp.render_llms(prof))
    status = "VALID" if not errs else f"{len(errs)} SCHEMA ERRORS"
    print(f"  -> {out}  [{status}]")
    for e in errs[:8]: print("     !", list(e.path), e.message[:80])
    return not errs

def offline(resp_dir):
    """Rebuild R dict from a saved responses dir (best-effort; may be partial)."""
    d = pathlib.Path(resp_dir)
    def L(slug):
        f = d / f"{slug}.json"
        if not f.exists(): return None
        try: x = json.load(open(f))
        except: return None
        return None if (isinstance(x, dict) and "_error" in x) else x
    R = {"client": L("s1_client"), "entity": L("s2_entity"),
         "entities": cp.hal(L("s2_entities"), "entities"),
         "entity_details": [x for x in [L("s2_entity"), L("s2_entity_MEA")] if x],
         "breadcrumb": L("s2_breadcrumb"), "services": L("s2_services"),
         "processing_channels": cp.hal(L("s3_processing_channels"), "processing_channels"),
         "channel_details": [x for x in [L("s3_processing_channel_detail")] if x],
         "profile_details": [json.load(open(f)) for f in sorted(glob.glob(str(d/"ppdetail_*.json")))],
         "apm_pricing_raw": L("s4_apm_pricing"), "payout_routes_raw": L("s5_payout_routes_v2"),
         "forex_p2c": L("s5_forex_p2c"), "currency_accounts_raw": L("s6_currency_accounts"),
         "risk_client": L("s8_risk_client"), "net_tokens": L("s8_network_tokens"),
         "payment_routing_raw": L("r_payment_routing"), "payout_routing_raw": L("r_payout_routing")}
    prof = cp.normalize(R)
    # Cached profile details may be v1 responses, which lack the v2-only AFT /
    # funds-transfer-type / corridor / auth-hold fields. Never let a degraded pack
    # be mistaken for a real snapshot.
    v2 = any((p.get("funds_transfer_type") or p.get("aft") or
              p.get("authorization_validity_period") is not None)
             for p in prof.get("processing_profiles", {}).get("profiles", []))
    if not v2:
        print("  !! DEGRADED: cached profile details are v1 — AFT, FT types, corridors and\n"
              "     auth holds are absent. This pack is NOT snapshot-quality; regenerate live.")
    write_profile(prof)

def live():
    base = os.environ["BASE_URL"].rstrip("/"); token = os.environ["TOKEN"]
    cid = os.environ["CLIENT_ID"]; eid = os.environ.get("ENTITY_ID"); sk = os.environ.get("SK")
    ents = ([{"id": eid}] if eid else cp.list_entities(base, token, cid))
    if not ents: sys.exit("No entities found (check client id / token).")
    ok_all = True
    for e in ents:
        print(f"entity {e.get('id')} ({e.get('name','')}) — fetching full breadth…")
        R = cp.fetch_all(base, token, cid, e["id"])
        st = R.get("_status", {})
        got = sum(1 for v in st.values() if v == 200)
        print(f"  {got}/{len(st)} endpoints 200 | channels={len(R.get('channel_details',[]))} profiles={len(R.get('profile_details',[]))}")
        ok_all &= write_profile(cp.normalize(R), sk)
    sys.exit(0 if ok_all else 1)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--offline":
        offline(sys.argv[2] if len(sys.argv) > 2 else "cat-api/responses")
    else:
        live()
