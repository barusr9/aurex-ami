"""Type one message into the real chat UI (headless Chrome, DevTools protocol), wait for
Ami's reply or a timeout, and screenshot the conversation.
Usage: python screenshot_chat.py <port> <out.png> "<message>" [max_wait_s=30]
Prints the elapsed time and whether a reply arrived (or the UI is still on 'thinking…')."""
import base64, json, subprocess, sys, tempfile, time, urllib.request
import websocket

PORT, OUT, MSG = sys.argv[1], sys.argv[2], sys.argv[3]
MAX_WAIT = float(sys.argv[4]) if len(sys.argv) > 4 else 30
BASE = f"http://127.0.0.1:{PORT}"

req = urllib.request.Request(BASE + "/login", data=json.dumps({"email": "demo1@cofy.ai", "password": "demo123"}).encode(),
                             headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req) as r:
    token = next(v.split(";")[0].split("=", 1)[1] for k, v in r.headers.items() if k == "Set-Cookie" and v.startswith("auth_token="))

prof = tempfile.mkdtemp()
chrome = subprocess.Popen(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--headless=new", "--disable-gpu",
                           "--remote-debugging-port=9333", "--remote-allow-origins=http://127.0.0.1:9333", f"--user-data-dir={prof}", "--hide-scrollbars", "about:blank"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(50):
        try:
            tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9333/json")); break
        except Exception:
            time.sleep(0.2)
    ws = websocket.create_connection(next(t for t in tabs if t["type"] == "page")["webSocketDebuggerUrl"], timeout=60, origin="http://127.0.0.1:9333")
    n = [0]
    def cdp(method, **params):
        n[0] += 1; ws.send(json.dumps({"id": n[0], "method": method, "params": params}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == n[0]: return m.get("result", {})
    def js(expr):
        return cdp("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)["result"].get("value")
    cdp("Network.enable")
    cdp("Network.setCookie", name="auth_token", value=token, url=BASE + "/", httpOnly=True, secure=True, sameSite="Strict")
    cdp("Emulation.setDeviceMetricsOverride", width=1100, height=800, deviceScaleFactor=1, mobile=False)
    cdp("Page.enable"); cdp("Page.navigate", url=BASE + "/")
    time.sleep(2.5)                                           # greeting + /state restore
    before = js("document.querySelectorAll('#chat .bubble').length") or 0
    js(f"document.getElementById('box').value = {json.dumps(MSG)}; document.querySelector('form').requestSubmit(); true")
    t0 = time.time(); state = "no reply (still 'thinking…')"
    while time.time() - t0 < MAX_WAIT:
        last = js("(function(){const b=document.querySelectorAll('#chat .bubble');return b.length?b[b.length-1].innerText:''})()") or ""
        if js("document.querySelectorAll('#chat .bubble').length") >= before + 2 and "thinking" not in last.lower():
            state = "reply received"; break
        time.sleep(0.5)
    elapsed = time.time() - t0
    js("window.scrollTo(0, document.body.scrollHeight); true"); time.sleep(0.5)
    h = js("document.documentElement.scrollHeight")
    cdp("Emulation.setDeviceMetricsOverride", width=1100, height=min(int(h), 2000), deviceScaleFactor=1, mobile=False)
    time.sleep(0.5)
    png = cdp("Page.captureScreenshot", format="png", captureBeyondViewport=True)["data"]
    open(OUT, "wb").write(base64.b64decode(png))
    last = js("(function(){const b=document.querySelectorAll('#chat .bubble');return b.length?b[b.length-1].innerText:''})()") or ""
    print(f"saved {OUT}  {state} after {elapsed:.1f}s  last bubble: {last[:200]!r}")
finally:
    chrome.terminate()
