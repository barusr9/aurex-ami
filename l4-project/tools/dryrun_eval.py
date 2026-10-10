# Offline dry-run of evals.run_case with a scripted model (0 tokens)
import sys, types, warnings; warnings.filterwarnings("ignore")
sys.path[:0] = [".", "tests"]   # run from bhargava-code/
import evals
from ami import planner
from fakes import Reply, tool_call
oid = "112-3333333-3333333"
CASE = next(c for c in evals.CASES if c["name"] == "cancel after confirmation")
script = iter([
    Reply(tool_calls=[tool_call("cancel_order", order_id=oid, thought="t")]), Reply(content="Confirm cancel? (yes/no)"),
    Reply(tool_calls=[tool_call("cancel_order", order_id=oid, confirmed="yes", thought="t")]), Reply(content="Cancelled - $149.99 refunded."),
])
planner.complete = lambda messages, tools=None, model=None, **k: types.SimpleNamespace(
    choices=[types.SimpleNamespace(message=next(script))])
r = evals.run_case(CASE, "react")
print("case     :", CASE["name"]); print("turns    :", CASE["turns"])
print("called   :", r["called"]); print("executed :", r["executed"])
print("store    :", oid, "->", r["store"][oid]); print("reply    :", r["reply"])
print("fails    :", evals.score(CASE, r))
