"""Capture the /logs dashboard (behind login) with headless Chrome via the DevTools protocol.
Usage: python screenshot_logs.py <port> <out.png> [path] [clip_height]"""
import base64, json, subprocess, sys, tempfile, time, urllib.request
import websocket

PORT, OUT = sys.argv[1], sys.argv[2]
PATH = sys.argv[3] if len(sys.argv) > 3 else "/logs"
CLIP = int(sys.argv[4]) if len(sys.argv) > 4 else 0       # 0 = full page
BASE = f"http://127.0.0.1:{PORT}"

# 1. log in over HTTP and take the auth cookie the server sets
req = urllib.request.Request(BASE + "/login", data=json.dumps({"email": "demo1@cofy.ai", "password": "demo123"}).encode(),
                             headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req) as r:
    token = next(v.split(";")[0].split("=", 1)[1] for k, v in r.headers.items() if k == "Set-Cookie" and v.startswith("auth_token="))

# 2. headless Chrome with remote debugging
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
    ws = websocket.create_connection(next(t for t in tabs if t["type"] == "page")["webSocketDebuggerUrl"], timeout=30, origin="http://127.0.0.1:9333")
    n = [0]
    def cdp(method, **params):
        n[0] += 1; ws.send(json.dumps({"id": n[0], "method": method, "params": params}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == n[0]: return m.get("result", {})
    cdp("Network.enable")
    cdp("Network.setCookie", name="auth_token", value=token, url=BASE + "/", httpOnly=True, secure=True, sameSite="Strict")
    cdp("Emulation.setDeviceMetricsOverride", width=1400, height=1000, deviceScaleFactor=1, mobile=False)
    cdp("Page.enable"); cdp("Page.navigate", url=BASE + PATH)
    time.sleep(4)                                    # let the page fetch /logs.json and render
    h = cdp("Runtime.evaluate", expression="document.documentElement.scrollHeight", returnByValue=True)["result"]["value"]
    cdp("Emulation.setDeviceMetricsOverride", width=1400, height=min(int(h), 3000), deviceScaleFactor=1, mobile=False)
    time.sleep(1)
    title = cdp("Runtime.evaluate", expression="document.title + ' | ' + location.pathname", returnByValue=True)["result"]["value"]
    shot = {"clip": {"x": 0, "y": 0, "width": 1400, "height": CLIP, "scale": 1}} if CLIP else {}
    png = cdp("Page.captureScreenshot", format="png", captureBeyondViewport=True, **shot)["data"]
    open(OUT, "wb").write(base64.b64decode(png))
    print(f"saved {OUT}  page={title!r}  height={h}px")
finally:
    chrome.terminate()
