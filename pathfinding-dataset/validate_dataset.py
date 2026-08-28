"""
Final upload-readiness check: verify every line matches the platform's reference
schema (from the pasted agentcore_gateway_tools example) field-by-field.
"""
import json

REQUIRED_TOP = {"data_source", "prompt", "ability", "reward_model", "extra_info", "tools"}
REQUIRED_GT = {"tool_call_id", "type", "function", "output"}


def check_file(fn):
    n = 0
    errs = []
    starts_seen = set()
    strategies = set()
    for i, line in enumerate(open(fn), 1):
        try:
            d = json.loads(line)
        except Exception as e:
            errs.append(f"line {i}: bad JSON: {e}")
            continue
        n += 1
        # top-level
        missing = REQUIRED_TOP - set(d.keys())
        if missing:
            errs.append(f"line {i}: missing top keys {missing}")
        if d.get("data_source") != "agentcore_gateway_tools":
            errs.append(f"line {i}: data_source={d.get('data_source')!r}")
        if d.get("ability") != "tool_use":
            errs.append(f"line {i}: ability={d.get('ability')!r}")
        # prompt
        p = d.get("prompt", [])
        if [m.get("role") for m in p] != ["system", "user"]:
            errs.append(f"line {i}: prompt roles {[m.get('role') for m in p]}")
        if "{column}{row}" not in p[1]["content"]:
            errs.append(f"line {i}: user missing coord spec")
        # reward_model
        rm = d.get("reward_model", {})
        if rm.get("style") != "rule":
            errs.append(f"line {i}: reward style {rm.get('style')!r}")
        gt_raw = rm.get("ground_truth")
        if not isinstance(gt_raw, str):
            errs.append(f"line {i}: ground_truth not a string")
            continue
        gt = json.loads(gt_raw)
        if set(gt.keys()) < REQUIRED_GT:
            errs.append(f"line {i}: gt missing {REQUIRED_GT - set(gt.keys())}")
        if gt.get("type") != "function":
            errs.append(f"line {i}: gt.type {gt.get('type')!r}")
        fn_obj = gt.get("function", {})
        if fn_obj.get("name") != "pathfinding_lambda":
            errs.append(f"line {i}: gt fn name {fn_obj.get('name')!r}")
        # arguments must be a JSON string, parseable, with the 3 keys
        args = fn_obj.get("arguments")
        if not isinstance(args, str):
            errs.append(f"line {i}: gt arguments not a string")
        else:
            a = json.loads(args)
            if set(a.keys()) != {"game_map", "start_pos", "strategy"}:
                errs.append(f"line {i}: args keys {set(a.keys())}")
            strategies.add(a.get("strategy"))
            starts_seen.add(tuple(a.get("start_pos", [])))
            # start_pos must point at a 'start' cell (or (0,0) fallback)
            gm = a["game_map"]
            sr, sc = a["start_pos"]
            if not (0 <= sr < len(gm) and 0 <= sc < len(gm[0])):
                errs.append(f"line {i}: start_pos out of bounds")
        # output body must be JSON string with a path
        out = gt.get("output", {})
        body = out.get("body")
        if not isinstance(body, str):
            errs.append(f"line {i}: output.body not a string")
        else:
            b = json.loads(body)
            if "path" not in b or not isinstance(b["path"], list):
                errs.append(f"line {i}: output body missing path list")
            for mv in b.get("path", []):
                if mv not in ("up", "down", "left", "right"):
                    errs.append(f"line {i}: bad move {mv!r}")
                    break
        # tools
        t = d.get("tools", [])
        if not t or t[0].get("function", {}).get("name") != "pathfinding_lambda":
            errs.append(f"line {i}: tools bad")
    return n, errs, strategies


for fn in ["train.jsonl", "validation.jsonl", "dataset.jsonl"]:
    n, errs, strategies = check_file(fn)
    status = "PASS" if not errs else f"FAIL ({len(errs)} issues)"
    print(f"{fn:20s} lines={n:4d} strategies={sorted(strategies)}  -> {status}")
    for e in errs[:10]:
        print("   ", e)
