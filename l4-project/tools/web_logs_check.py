"""Phase 4 item F: drive the real web app over HTTP and check /logs.json for nulls.
Also checks the answer cache end-to-end (same general question from a NEW browser session).
Usage (web.py already running on PORT): python web_logs_check.py 9011"""
import json, sys, time, urllib.request, http.cookiejar
BASE = f"http://127.0.0.1:{sys.argv[1] if len(sys.argv) > 1 else 9011}"

def browser():
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    def call(path, body=None):
        req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        with op.open(req, timeout=180) as r:
            raw = r.read().decode(); return json.loads(raw) if raw.strip().startswith("{") else raw
    call("/state"); call("/login", {"email": "demo1@cofy.ai", "password": "demo123"})
    # The auth cookie is `Secure`: browsers still send it to localhost, Python's
    # cookiejar only over https. Relax it in this test client only.
    for c in jar:
        c.secure = False
    return call

def chat(call, text):
    t = time.time(); r = call("/chat", {"message": text})
    print(f"  {time.time()-t:6.2f}s  steps={len(r.get('steps', []))}  {text!r} -> {r.get('reply','')[:90]!r}")
    return r

print("browser A"); a = browser(); chat(a, "What is your return policy?")
print("browser B (new session, same question -> expect cache hit: 0 steps, ~ms)"); b = browser(); chat(b, "What is your return policy?")
print("browser A (account question -> never cached)"); chat(a, "What's the status of order 111-2222222-2222222?")

logs = a("/logs.json"); s = logs["stats"]
print("\n/logs.json stats:"); print("  " + json.dumps(s)[:600])
nulls = [k for k, v in s.items() if v is None]
print(f"  null stats fields: {nulls or 'none'}")
for kind in ("turn", "llm", "tool", "cache"):
    ev = [e for e in logs["events"] if e["kind"] == kind]
    if not ev: print(f"  {kind:<5} events: none"); continue
    keys = {"turn": ["ms", "steps", "cost"], "llm": ["ms", "tokens_in", "tokens_out", "cost", "served_by"],
            "tool": ["tool", "ms", "ok"], "cache": ["result"]}[kind]
    missing = sorted({k for e in ev for k in keys if e.get(k) is None})
    print(f"  {kind:<5} events: {len(ev):>3}  sample={ {k: ev[0].get(k) for k in keys} }  null fields: {missing or 'none'}")
