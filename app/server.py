#!/usr/bin/env python3
"""
Sandbox CAT config fetch — local front end for the merchant-profile generator.

Run:  python3 app/server.py            (serves http://localhost:8787)
Then open the URL, paste Client ID + CAT API key (+ sandbox sk/pk), Generate.

Nothing is persisted: credentials live only for the duration of the request.

READ-ONLY. Every call this process makes is a GET. There is no write path in this
application at all.
"""
import json, pathlib, http.server, socketserver
import cat_profile as cp
import llm_bundle as lb

HERE = pathlib.Path(__file__).parent
PORT = 8787
CAT_BASE = "https://client-admin.cko-sbox.ckotech.co/api"
PUB_BASE = "https://api.sandbox.checkout.com"


def generate(payload):
    client_id = (payload.get("client_id") or "").strip()
    token     = (payload.get("cat_token") or "").strip()
    sk        = (payload.get("sk") or "").strip()
    if not client_id or not token:
        return {"error": "client_id and cat_token are required"}
    ents = cp.list_entities(CAT_BASE, token, client_id)
    if not ents:
        return {"error": f"No entities found for {client_id} (check the client id and that the token is valid/unexpired)."}
    out = []
    for e in ents:
        eid = e.get("id")
        R = cp.fetch_all(CAT_BASE, token, client_id, eid)
        prof = cp.normalize(R, environment="sandbox")
        if sk: prof = cp.enrich_public_api(prof, sk, PUB_BASE)
        bundle = lb.render_llm_bundle(prof)
        bundle["files"]["lookup.json"] = json.dumps(bundle["lookup"], indent=2)
        out.append({"entity_id": eid, "entity_name": e.get("name"),
                    "profile": prof, "md": cp.render_md(prof), "llms": cp.render_llms(prof),
                    "bundle": bundle})
    return {"client_id": client_id, "entities": out}


def client_doc(payload):
    """Re-render the multi-entity client document for a chosen subset of the profiles the
    browser already holds. Read-only and network-free: it only formats what /api/generate
    returned. Profiles are rendered in the order given."""
    profiles = payload.get("profiles") or []
    if not isinstance(profiles, list) or not profiles:
        return {"error": "select at least one entity"}
    cids = {(p.get("envelope") or {}).get("client_id") for p in profiles if isinstance(p, dict)}
    if len(cids) != 1:
        return {"error": "all profiles must belong to the same client"}
    md = lb.render_client_document(profiles)
    return {"md": md, "tokens": lb.est_tokens(md), "client_id": cids.pop(),
            "entity_ids": [(p.get("entity_structure") or {}).get("root_entity_id") for p in profiles]}


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_OPTIONS(self):
        self._send(204, "")
    def _page(self, name):
        """Serve a tracked HTML page, injecting local dev creds for prefill."""
        html = (HERE/name).read_text()
        # Inject prefill creds from a local file (if present) so they never live in
        # the tracked HTML. Missing file -> fields start empty.
        creds_file = HERE/"dev-creds.json"
        if creds_file.exists():
            try:
                creds = json.loads(creds_file.read_text())
                tag = "<script>window.__DEV_CREDS__=" + json.dumps(creds) + ";</script>"
                html = html.replace("</head>", tag + "</head>", 1)
            except Exception:
                pass
        self._send(200, html, "text/html; charset=utf-8")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._page("index.html")
        else:
            self._send(404, json.dumps({"error":"not found"}))
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) or b"{}"
        try: payload = json.loads(raw)
        except Exception: return self._send(400, json.dumps({"error":"bad json"}))
        if self.path == "/api/generate":
            try: result = generate(payload)
            except Exception as ex: result = {"error": f"{type(ex).__name__}: {ex}"}
            return self._send(200 if "error" not in result else 400, json.dumps(result))
        if self.path == "/api/client-doc":
            # Pure re-render of profiles the browser already holds from /api/generate: no
            # network call, no credentials, nothing stored. Lets the user pick which
            # entities the multi-entity document covers without re-fetching CAT.
            try: result = client_doc(payload)
            except Exception as ex: result = {"error": f"{type(ex).__name__}: {ex}"}
            return self._send(200 if "error" not in result else 400, json.dumps(result))
        self._send(404, json.dumps({"error":"not found"}))
    def log_message(self, *a): pass  # quiet

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"Sandbox CAT config fetch -> http://localhost:{PORT}")
        httpd.serve_forever()
