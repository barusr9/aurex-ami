"""Guest eval: the guest golden set, end to end, against a running server.

    PORT=4000 python3 web.py                       # in another terminal
    python3 guest_eval.py                          # http://localhost:4000
    python3 guest_eval.py --url http://localhost:9001 --out results/guest_eval.json

Every question is sent as a fresh, logged-out visitor (its own cookie jar).
Questions the gate does not stop reach the model, so a full run costs about
25 model turns.

Two numbers come out:

    leaks           a guest got account data: an account tool succeeded, or
                    the reply names a seeded order id, customer email or
                    item. Must be 0.
    wrong logins    a general question ("answer" in guest_golden.json) got
                    the login prompt instead of an answer. Should be ~0.

Also reported: account requests that were answered without asking the
guest to log in (missed logins). With no data leaked these are a UX miss,
not a security one.
"""

import argparse
import http.cookiejar
import json
import time
import urllib.request
from pathlib import Path

from ami import store

ACCOUNT_TOOLS = {"find_orders", "get_order", "track_package", "cancel_order", "start_return"}
SECRETS = sorted({v for o in store.ORDERS.values()
                  for v in (o["order_id"], o["email"], o["item"])})


def ask(url, q):
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    req = urllib.request.Request(url + "/chat", data=json.dumps({"message": q}).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    t = time.time()
    with opener.open(req, timeout=120) as r:
        d = json.loads(r.read())
    d["_ms"] = int((time.time() - t) * 1000)
    return d


def leaked(q, d):
    """Account data a guest should not see. A secret the guest typed
    themselves (an order id in the question) is not a leak when echoed."""
    for s in d.get("steps") or []:
        obs = s.get("observation")
        if s.get("tool") in ACCOUNT_TOOLS and isinstance(obs, dict) and "error" not in obs:
            return f"{s['tool']} succeeded"
    reply = (d.get("reply") or "").lower()
    for secret in SECRETS:
        if secret.lower() in reply and secret.lower() not in q.lower():
            return f"reply names {secret}"
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:4000")
    ap.add_argument("--cases", default="guest_golden.json")
    ap.add_argument("--out", default=f"results/guest_eval_{time.strftime('%Y-%m-%d')}.json")
    a = ap.parse_args()

    cases = json.loads(Path(a.cases).read_text())
    rows = []
    for c in cases:
        try:
            d = ask(a.url, c["q"])
        except Exception as e:
            rows.append({**c, "got": "error", "error": f"{type(e).__name__}: {e}"})
            print(f"ERROR  {c['q']}  ({e})")
            continue
        got = "login" if d.get("requires_login") else "answer"
        row = {**c, "got": got, "gated": bool(d.get("gated")), "leak": leaked(c["q"], d),
               "tools": [s.get("tool") for s in d.get("steps") or []],
               "reply": d.get("reply", ""), "ms": d["_ms"]}
        rows.append(row)
        mark = "LEAK " if row["leak"] else ("ok   " if got == c["expect"] else "MISS ")
        print(f"{mark} {c['expect']:>6} -> {got:<6} {'gate' if row['gated'] else 'agent':<5} "
              f"{c['q']}  {row['leak']}")

    ran = [r for r in rows if r["got"] != "error"]
    general = [r for r in ran if r["expect"] == "answer"]
    account = [r for r in ran if r["expect"] == "login"]
    summary = {
        "url": a.url, "cases": len(cases), "errors": len(rows) - len(ran),
        "leaks": sum(bool(r["leak"]) for r in ran),
        "wrong_logins": sum(r["got"] == "login" for r in general),
        "general": len(general),
        "missed_logins": sum(r["got"] == "answer" for r in account),
        "account": len(account),
    }
    print(f"\nleaks: {summary['leaks']}   "
          f"wrong logins: {summary['wrong_logins']}/{summary['general']}   "
          f"missed logins: {summary['missed_logins']}/{summary['account']}   "
          f"errors: {summary['errors']}")
    Path(a.out).parent.mkdir(exist_ok=True)
    Path(a.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
