"""Summarize eval result files the way READOUT.md does: frozen-20 vs complaint cases.
usage: eval_summary.py label=file.json [label=file.json ...]"""
import json, sys
def pct(v, p):
    v = sorted(v); return v[min(len(v)-1, int(round(p/100*len(v)+0.5))-1)] if v else 0
rows = {}
for arg in sys.argv[1:]:
    label, path = arg.split("=", 1); d = json.load(open(path))
    for grp, sel in (("frozen20", lambda r: not r["case"].startswith("complaint")), ("complaint10", lambda r: r["case"].startswith("complaint"))):
        g = [r for r in d if sel(r)]
        if not g: continue
        o = [r["outcomes"][0] for r in g]
        ms = [x["ms"] for x in o if x["ms"] < 120000]          # READOUT excludes the 14-min hang the same way
        rows[(label, grp)] = dict(passed=f"{sum(r['passed'] for r in g)}/{len(g)}", cost_c=100*sum(x["cost"] for x in o)/len(o),
            p50=pct(ms, 50), p95=pct(ms, 95), calls=sum(x["llm_calls"] for x in o), tokens=sum(x.get("tokens") or 0 for x in o),
            failed=[r["case"] for r in g if not r["passed"]])
for (label, grp), m in rows.items():
    print(f"{label:<14} {grp:<12} passed={m['passed']:<6} cost/case={m['cost_c']:.2f}¢  p50={m['p50']:>6}ms  p95={m['p95']:>6}ms  calls={m['calls']:>3}  tokens={m['tokens']:>7,}  failed={m['failed']}")
