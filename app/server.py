#!/usr/bin/env python3
"""
Sandbox CAT config fetch — local front end for the merchant-profile generator.

Run:  python3 app/server.py            (serves http://localhost:8787)
Then open the URL, paste Client ID + CAT API key (+ optional sk for webhooks), Generate.

Nothing is persisted: credentials live only for the duration of the request.

READ-ONLY. Every call this process makes is a GET. There is no write path in this
application at all.
"""
import json, pathlib, http.server, socketserver
import cat_profile as cp
import llm_bundle as lb

HERE = pathlib.Path(__file__).parent
PORT = 8787
# Service bases per mode live in cat_profile.ENVIRONMENTS — one table, both modes.


def _check_sk(mode, sk):
    """Refuse a secret key from the other environment. Checkout prefixes sandbox keys with
    sk_sbox_ and production keys with plain sk_, so a mismatch is certain, and a production
    fetch decorated with sandbox webhooks (or vice versa) would be a document about two
    environments at once."""
    if not sk: return None
    is_sbox = sk.startswith("sk_sbox_")
    if mode == "production" and is_sbox:
        return "the secret key is a sandbox key (sk_sbox_…) but Prod mode is selected"
    if mode == "sandbox" and sk.startswith("sk_") and not is_sbox:
        return "the secret key looks like a production key but Sandbox mode is selected"
    return None


def generate(payload, emit=None):
    """Run one fetch. `emit(event)` (optional) receives progress events as the fetch runs:
    start · entities (the list, once known) · entity_start / entity_done · call (one per GET,
    reported from cat_profile._get). The return value is the result or an {"error": ...}."""
    emit = emit or (lambda ev: None)
    mode = (payload.get("mode") or "sandbox").strip().lower()
    if mode == "prod": mode = "production"
    if mode not in cp.ENVIRONMENTS:
        return {"error": f"unknown mode {mode!r}; use sandbox or production"}
    S = cp.ENVIRONMENTS[mode]
    client_id = (payload.get("client_id") or "").strip()
    token     = (payload.get("cat_token") or "").strip()
    sk        = (payload.get("sk") or "").strip()   # optional: unlocks webhooks/workflows only
    if not client_id or not token:
        return {"error": ("Prod mode requires a Client ID and a PROD CAT API token"
                          if mode == "production" else "client_id and cat_token are required")}
    bad = _check_sk(mode, sk)
    if bad:
        return {"error": bad}
    if not S.get("cat"):
        return {"error": f"{mode.capitalize()} mode is not configured: the "
                         f"{cp.SERVICE_LABELS['cat']} base URL for {mode} is not set in "
                         f"cat_profile.ENVIRONMENTS['{mode}']['cat']. Add the verified host "
                         "and restart the server. No request was made."}
    emit({"type": "start", "mode": mode, "client_id": client_id,
          "hosts": {k: v for k, v in S.items() if v}})
    cp.set_progress_hook(lambda c: emit({"type": "call", **c}))
    try:
        st, ents, why = cp.list_entities_diag(S["cat"], token, client_id)
        if why:
            # Name the failure class (no response / 401 / 404 / empty) — a generic "no
            # entities" message has twice sent the user to check the client id when the host
            # or the token was the real problem.
            return {"error": f"[{mode}] {why}", "http_status": st}
        emit({"type": "entities", "total": len(ents),
              "entities": [{"id": e.get("id"), "name": e.get("name")} for e in ents]})
        out = []
        for i, e in enumerate(ents):
            eid = e.get("id")
            emit({"type": "entity_start", "index": i, "entity_id": eid, "name": e.get("name")})
            R = cp.fetch_all(S["cat"], token, client_id, eid, services=S)
            prof = cp.normalize(R, environment=mode)
            if sk and S.get("public"): prof = cp.enrich_public_api(prof, sk, S["public"])
            bundle = lb.render_llm_bundle(prof)
            bundle["files"]["lookup.json"] = json.dumps(bundle["lookup"], indent=2)
            out.append({"entity_id": eid, "entity_name": e.get("name"),
                        "profile": prof, "md": cp.render_md(prof), "llms": cp.render_llms(prof),
                        "bundle": bundle})
            emit({"type": "entity_done", "index": i, "entity_id": eid})
        return {"client_id": client_id, "mode": mode, "entities": out}
    finally:
        cp.set_progress_hook(None)


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
        elif self.path == "/favicon.svg":
            self._send(200, (HERE/"favicon.svg").read_bytes(), "image/svg+xml")
        else:
            self._send(404, json.dumps({"error":"not found"}))
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) or b"{}"
        try: payload = json.loads(raw)
        except Exception: return self._send(400, json.dumps({"error":"bad json"}))
        if self.path == "/api/generate":
            # Streamed as newline-delimited JSON so the page can show progress and each GET as
            # it happens. HTTP/1.0 with no Content-Length: the body ends when the socket closes.
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            def emit(ev):
                self.wfile.write((json.dumps(ev) + "\n").encode("utf-8")); self.wfile.flush()
            try: result = generate(payload, emit)
            except Exception as ex: result = {"error": f"{type(ex).__name__}: {ex}"}
            try: emit({"type": "error" if "error" in result else "result", **result})
            except (BrokenPipeError, ConnectionResetError): pass
            return
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
