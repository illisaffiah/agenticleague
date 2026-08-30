"""Stress-test mapanalyzer_v2 against adversarial randomized maps to find failure modes."""
import json, random, importlib.util

spec = importlib.util.spec_from_file_location("m", "/projects/sandbox/agenticleague/mapanalyzer_lambda.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

DIRS = {"up":(-1,0),"down":(1,0),"left":(0,-1),"right":(0,1)}

def call_path(MAP, start="A1"):
    ev={"parameters":[{"name":"action","value":"pathfind"},
                      {"name":"start_pos","value":start},
                      {"name":"game_map","value":json.dumps(MAP)}]}
    return m.lambda_handler(ev, None)

def replay(MAP, path, start=(0,0)):
    """Return dict of what the path achieves + any wall-collision."""
    rows, cols = len(MAP), len(MAP[0])
    r,c = start
    coins=set(); chal=set(); spikes=set(); keys=set(); doors=set()
    reached_treasure=False; wall_hit=False
    locked = {(rr,cc) for rr in range(rows) for cc in range(cols)
              if MAP[rr][cc] in ("c30","c31")}
    keys_taken=set()
    door_before_key=False
    for mv in path:
        dr,dc = DIRS[mv]; r+=dr; c+=dc
        if not (0<=r<rows and 0<=c<cols): wall_hit=True; break
        cell = MAP[r][c]
        if cell=="wall": wall_hit=True; break
        if (r,c) in locked:
            kcode = "c4"+cell[2:]
            kpos = next((p for p in keys if MAP[p[0]][p[1]]==kcode), None)
            # check key taken before door
            if any(MAP[p[0]][p[1]]==kcode for p in keys) and (kcode_pos(MAP,kcode) not in keys_taken):
                door_before_key=True
            locked.discard((r,c))
        if cell=="c7": coins.add((r,c))
        elif cell=="treasure": reached_treasure=True
        elif cell=="c8": spikes.add((r,c))
        elif cell in ("c40","c41"): keys.add((r,c)); keys_taken.add((r,c))
        elif cell in ("c30","c31"): doors.add((r,c))
        elif m._is_challenge(cell): chal.add((r,c))
    return dict(coins=coins,chal=chal,spikes=spikes,keys=keys,doors=doors,
                treasure=reached_treasure,wall_hit=wall_hit,door_before_key=door_before_key)

def kcode_pos(MAP,kcode):
    for rr in range(len(MAP)):
        for cc in range(len(MAP[0])):
            if MAP[rr][cc]==kcode: return (rr,cc)
    return None

def totals(MAP):
    """Ground-truth counts of collectibles reachable."""
    coins=sum(r.count("c7") for r in MAP)
    chal=sum(1 for row in MAP for x in row if m._is_challenge(x))
    keys=sum(1 for row in MAP for x in row if x in ("c40","c41"))
    doors=sum(1 for row in MAP for x in row if x in ("c30","c31"))
    treas=sum(r.count("treasure") for r in MAP)
    return coins,chal,keys,doors,treas

# ---- Test battery ----
def run_case(name, MAP, start="A1"):
    try:
        res = call_path(MAP, start)
        if not res.get("success"):
            print(f"[FAIL] {name}: handler returned success=False -> {res}"); return
        path = json.loads(res["result"])
        rep = replay(MAP, path, m._parse_start(start))
        tc,tch,tk,td,tt = totals(MAP)
        problems=[]
        if rep["wall_hit"]: problems.append("WALL COLLISION")
        if tt and not rep["treasure"]: problems.append("NO TREASURE")
        if rep["door_before_key"]: problems.append("DOOR BEFORE KEY")
        # only flag missed collectibles if they were actually reachable (skip unreachable-by-design)
        status = "OK" if not problems else "PROBLEM: "+", ".join(problems)
        print(f"[{status}] {name}: steps={len(path)} coins={len(rep['coins'])}/{tc} "
              f"chal={len(rep['chal'])}/{tch} keys={len(rep['keys'])}/{tk} "
              f"doors={len(rep['doors'])}/{td} spikes={len(rep['spikes'])} treasure={rep['treasure']}")
    except Exception as e:
        print(f"[CRASH] {name}: {type(e).__name__}: {e}")

# Case 1: empty map
run_case("empty map", [])
# Case 2: no treasure
run_case("no treasure", [["normal","c7"],["c7","normal"]])
# Case 3: treasure walled off completely
run_case("treasure walled off", [["normal","wall","treasure"],["normal","wall","wall"],["normal","normal","wall"]])
# Case 4: start on a spike, surrounded by spikes
run_case("start boxed by spikes", [["c8","c8","treasure"],["c8","c8","normal"]])
# Case 5: key unreachable (walled), door blocks treasure
run_case("key walled, door blocks treasure",
    [["normal","c30","treasure"],["wall","wall","wall"],["c40","normal","normal"]])
# Case 6: ragged rows (model dropped cells)
run_case("ragged rows", [["normal","c7","treasure"],["c7"],["normal","normal"]])
# Case 7: unknown tile codes (c99, c50)
run_case("unknown challenge codes", [["normal","c99","c7"],["c50","normal","treasure"]])
# Case 8: multiple key/door pairs
run_case("two red doors one key",
    [["c40","c30","c7"],["normal","normal","c30"],["normal","normal","treasure"]])
# Case 9: door with NO matching key
run_case("orphan door no key", [["normal","c31","treasure"],["normal","normal","normal"]])
# Case 10: 1x1, treasure only
run_case("treasure only", [["treasure"]])
# Case 11: big 10x10 random with spikes/keys/doors
random.seed(7)
tiles=["normal"]*40+["c7"]*20+["wall"]*15+["c8"]*5+["c1","c2","c3","c4","c5","c18"]*2
big=[[random.choice(tiles) for _ in range(10)] for _ in range(10)]
big[0][0]="normal"; big[9][9]="treasure"
big[5][5]="c41"; big[6][6]="c31"; big[3][3]="c40"; big[4][4]="c30"
run_case("random 10x10 (seed7)", big)
# Case 12: start given in weird format
run_case("start as [row,col] list", [["normal","c7"],["c7","treasure"]], start="[1, 0]")
run_case("start dict-ish string", [["normal","c7"],["c7","treasure"]], start="row0col0")
