"""Corrected stress test: validate the Lambda's OWN output (normalized map)."""
import json, random, importlib.util

spec = importlib.util.spec_from_file_location("m", "/projects/sandbox/agenticleague/mapanalyzer_lambda.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
DIRS = {"up":(-1,0),"down":(1,0),"left":(0,-1),"right":(0,1)}

def run(name, MAP, start="A1"):
    try:
        ev={"parameters":[{"name":"action","value":"pathfind"},
                          {"name":"start_pos","value":start},
                          {"name":"game_map","value":json.dumps(MAP)}]}
        res = m.lambda_handler(ev, None)
    except Exception as e:
        print(f"[CRASH] {name}: {type(e).__name__}: {e}"); return
    if not res.get("success"):
        print(f"[EMPTY] {name}: {res.get('error')}"); return
    # Use the SAME normalized map the Lambda used
    norm = m._normalize_map(MAP)
    rows, cols = len(norm), (len(norm[0]) if norm else 0)
    path = json.loads(res["result"])
    sp = m._parse_start(start)
    if not (0 <= sp[0] < rows and 0 <= sp[1] < cols): sp=(0,0)
    r,c = sp; wall=False; spikes=set()
    treasure_pos = next(((rr,cc) for rr in range(rows) for cc in range(cols) if norm[rr][cc]=='treasure'), None)
    for mv in path:
        dr,dc=DIRS[mv]; nr,nc=r+dr,c+dc
        if not(0<=nr<rows and 0<=nc<cols) or norm[nr][nc]=='wall': wall=True; break
        r,c=nr,nc
        if norm[r][c]=='c8': spikes.add((r,c))
    reached = (treasure_pos is not None and (r,c)==treasure_pos)
    # is treasure even reachable (spikes+doors passable)?
    reachable = True
    if treasure_pos:
        alld={(rr,cc) for rr in range(rows) for cc in range(cols) if m._is_door(norm[rr][cc])}
        pth,_=m._dijkstra(norm,rows,cols,sp,treasure_pos,blocked=set(),open_cells=alld)
        reachable = pth is not None
    probs=[]
    if wall: probs.append("WALL")
    if treasure_pos and reachable and not reached: probs.append("MISSED REACHABLE TREASURE")
    status="OK" if not probs else "PROBLEM: "+",".join(probs)
    note = "" if reachable else " (treasure genuinely unreachable - correct to skip)"
    print(f"[{status}] {name}: steps={len(path)} distinct_spikes={len(spikes)} reached_treasure={reached}{note}")

run("ragged rows", [["normal","c7","treasure"],["c7"],["normal","normal"]])
run("start as [row,col] list", [["normal","c7"],["c7","treasure"]], start="[1, 0]")
random.seed(7)
tiles=["normal"]*40+["c7"]*20+["wall"]*15+["c8"]*5+["c1","c2","c3","c4","c5","c18"]*2
big=[[random.choice(tiles) for _ in range(10)] for _ in range(10)]
big[0][0]="normal"; big[9][9]="treasure"; big[5][5]="c41"; big[6][6]="c31"; big[3][3]="c40"; big[4][4]="c30"
run("random 10x10 (seed7)", big)
# a few more random seeds to check treasure guarantee
for s in [1,2,3,11,42,99]:
    random.seed(s)
    t=["normal"]*45+["c7"]*18+["wall"]*18+["c8"]*4+["c1","c2","c4","c5"]*2
    g=[[random.choice(t) for _ in range(10)] for _ in range(10)]
    g[0][0]="normal"; g[9][9]="treasure"
    # random key/door placement
    g[random.randint(2,7)][random.randint(2,7)]="c40"; g[random.randint(2,7)][random.randint(2,7)]="c30"
    run(f"random seed{s}", g)
