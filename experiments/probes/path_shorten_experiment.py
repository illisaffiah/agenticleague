"""
Experiment: can we shorten the 173-move full-clear path WITHOUT losing any
objective or life? Try alternative next-target heuristics in the sweep and
compare total move count. Purely offline; does not touch the deployed Lambda.

We re-implement the planner's sweep with a pluggable "pick next target" policy
and measure: total moves, coins, challenges, lives lost, ends-on-treasure.
"""
import sys, json, heapq
sys.path.insert(0, '.')
for m in list(sys.modules):
    if 'mapanalyzer' in m:
        del sys.modules[m]
import mapanalyzer_lambda as M

MAP = [['normal','normal','c7','c7','c7','c5','c7','c7','c1','treasure'],
['normal','wall','wall','wall','wall','wall','wall','wall','wall','wall'],
['c2','normal','c7','c5','c7','normal','c7','c4','normal','c7'],
['wall','wall','wall','wall','wall','wall','wall','wall','wall','c7'],
['c7','c7','c7','c7','wall','c41','wall','normal','c7','c7'],
['c8','wall','wall','c30','wall','c7','wall','c5','wall','c1'],
['c1','c2','wall','c7','wall','c8','wall','normal','wall','normal'],
['c7','c7','wall','c1','wall','c4','wall','c7','wall','c5'],
['c7','c7','wall','c31','wall','normal','wall','c7','wall','c7'],
['c18','c7','wall','normal','c7','c3','normal','c7','wall','c40']]
ROWS, COLS = 10, 10
MV = {'up':(-1,0),'down':(1,0),'left':(0,-1),'right':(0,1)}
def lbl(r,c): return chr(65+c)+str(r+1)

def evaluate(path, start=(0,0)):
    r,c = start; distinct=set(); coins=set(); chals=set(); ok=True
    coin_cells={(rr,cc) for rr in range(ROWS) for cc in range(COLS) if MAP[rr][cc]=='c7'}
    chal_cells={(rr,cc) for rr in range(ROWS) for cc in range(COLS) if M._is_challenge(MAP[rr][cc])}
    for m in path:
        dr,dc=MV[m]; nr,nc=r+dr,c+dc
        if not(0<=nr<ROWS and 0<=nc<COLS) or MAP[nr][nc]=='wall':
            ok=False; break
        r,c=nr,nc
        if MAP[r][c]=='c8': distinct.add((r,c))
        if (r,c) in coin_cells: coins.add((r,c))
        if (r,c) in chal_cells: chals.add((r,c))
    return {
        'moves': len(path), 'valid': ok, 'ends_treasure': (r,c)==(0,9),
        'coins': len(coins), 'coins_total': len(coin_cells),
        'chals': len(chals), 'chals_total': len(chal_cells),
        'lives_lost': len(distinct), 'spikes': sorted(lbl(*s) for s in distinct),
    }

# Baseline: current deployed planner
base = M._pathfind(MAP,(0,0))
print("BASELINE (current greedy sweep):")
print(" ", evaluate(base))
print()
print("Baseline move count:", len(base))



# ---------------------------------------------------------------------------
# Reimplement the planner with a pluggable next-target policy so we can compare.
# We reuse M._dijkstra for routing (it already handles spikes/doors correctly).
# ---------------------------------------------------------------------------
def plan(policy):
    """policy(cur, targets, board, triggered) -> chosen target (r,c) or None."""
    board = [row[:] for row in MAP]
    r, c = 0, 0
    full = []
    triggered = set()
    open_cells = M._find_start_exit(MAP, ROWS, COLS, (0,0))

    treasure = None; keys={}; doors={}
    for rr in range(ROWS):
        for cc in range(COLS):
            cell = board[rr][cc]
            if cell=='treasure': treasure=(rr,cc)
            elif M._is_key(cell): keys[cell]=(rr,cc)
            elif M._is_door(cell): doors[cell]=(rr,cc)
    locked = set(doors.values())
    keys_held=set()

    def value_of(cell):
        if cell in M.COIN_TILES: return 250
        if M._is_challenge(cell): return 400
        return 0

    def route(goal, blocked):
        return M._dijkstra(board, ROWS, COLS, (r,c), goal, blocked=blocked,
                           open_cells=open_cells, already_triggered=triggered)

    def commit(path, new_spikes, dest):
        nonlocal r,c
        full.extend(path); r,c = dest; triggered.update(new_spikes)

    def sweep():
        nonlocal r,c
        for _ in range(400):
            targets=[]
            for rr in range(ROWS):
                for cc in range(COLS):
                    cell=board[rr][cc]
                    if not (cell in M.COIN_TILES or M._is_challenge(cell)): continue
                    if (rr,cc)==(r,c): continue
                    p,ns = route((rr,cc), blocked=locked)
                    if p is None: continue
                    if ns and value_of(cell) < len(ns)*250: continue
                    targets.append(((rr,cc), p, ns))
            if not targets: break
            chosen = policy((r,c), targets)
            if chosen is None: break
            dest,p,ns = chosen
            commit(p, ns, dest)
            board[dest[0]][dest[1]]='normal'

    def collect_keys():
        nonlocal r,c
        prog=True
        while prog:
            prog=False
            for kcode,kpos in list(keys.items()):
                if board[kpos[0]][kpos[1]]=='normal': continue
                p,ns=route(kpos, blocked=locked)
                if p is None: continue
                commit(p,ns,kpos); board[kpos[0]][kpos[1]]='normal'
                keys_held.add(M._door_for_key(kcode)); prog=True

    def open_doors():
        nonlocal r,c
        prog=False
        for dcode in list(keys_held):
            dpos=doors.get(dcode)
            if dpos is None or dpos not in locked: continue
            p,ns=route(dpos, blocked=locked-{dpos})
            if p is None: continue
            commit(p,ns,dpos); board[dpos[0]][dpos[1]]='normal'
            locked.discard(dpos); prog=True
        return prog

    for _ in range(20):
        sweep(); collect_keys(); opened=open_doors(); collect_keys()
        if not opened and not any(board[kp[0]][kp[1]]!='normal' for kp in keys.values()):
            sweep()
            if not any(dp in locked for dp in doors.values()): break

    p,ns = M._dijkstra(board, ROWS, COLS, (r,c), treasure, blocked=set(),
                       open_cells=open_cells, already_triggered=triggered)
    if p is not None: full.extend(p)
    return full

# --- Policies ---
def policy_greedy(cur, targets):
    # baseline: fewest new spikes then shortest path (matches current planner)
    return min(targets, key=lambda t: (len(t[2]), len(t[1])))

def policy_farthest_cluster(cur, targets):
    # Prefer the target that, once reached, leaves us closest to OTHER targets
    # (a cheap "clear the far dead-end first" heuristic). Tiebreak on path len.
    def score(t):
        dest, p, ns = t
        # sum of Manhattan dist from dest to all other targets (want SMALL -> central)
        others = [o[0] for o in targets if o[0]!=dest]
        cent = sum(abs(dest[0]-o[0])+abs(dest[1]-o[1]) for o in others)
        return (len(ns), cent, len(p))
    return min(targets, key=score)

def policy_directional(cur, targets):
    # Nearest-neighbor but break ties by continuing in a consistent direction
    # (reduces zig-zag). Prefer fewest spikes, then shortest, then lowest row+col.
    return min(targets, key=lambda t: (len(t[2]), len(t[1]), t[0][0]+t[0][1]))

for name, pol in [("greedy(=baseline reimpl)", policy_greedy),
                  ("farthest/central", policy_farthest_cluster),
                  ("directional", policy_directional)]:
    path = plan(pol)
    ev = evaluate(path)
    tag = "FULL-CLEAR" if (ev['coins']==ev['coins_total'] and ev['chals']==ev['chals_total']
                           and ev['ends_treasure'] and ev['lives_lost']<=2) else "!! REGRESSION"
    print(f"{name:26} moves={ev['moves']:3}  lives={ev['lives_lost']}  "
          f"coins={ev['coins']}/{ev['coins_total']} chals={ev['chals']}/{ev['chals_total']}  {tag}")



# ---------------------------------------------------------------------------
# CEILING TEST: what's the shortest full-clear path achievable by optimizing
# the VISIT ORDER of all objectives (TSP-ish), respecting keys-before-doors?
# We compute pairwise shortest paths, then nearest-neighbor + 2-opt on the
# order, then stitch. This tells us the best-case move count => is it worth it?
# ---------------------------------------------------------------------------
def pairwise_and_order():
    # All must-visit objective cells (coins, challenges, keys, doors, treasure).
    board = [row[:] for row in MAP]
    objs = []
    keypos={}; doorpos={}; treasure=None
    for rr in range(ROWS):
        for cc in range(COLS):
            cell=board[rr][cc]
            if cell=='c7' or M._is_challenge(cell):
                objs.append((rr,cc))
            elif M._is_key(cell): keypos[cell]=(rr,cc); objs.append((rr,cc))
            elif M._is_door(cell): doorpos[cell]=(rr,cc); objs.append((rr,cc))
            elif cell=='treasure': treasure=(rr,cc)
    nodes=[(0,0)]+objs+[treasure]
    open_cells = {(r,c) for r in range(ROWS) for c in range(COLS) if M._is_door(MAP[r][c])}
    # cost between nodes: dijkstra move count with doors+spikes passable (upper bound)
    def d(a,b):
        p,_=M._dijkstra(MAP,ROWS,COLS,a,b,blocked=set(),open_cells=open_cells)
        return len(p) if p else 9999
    N=len(nodes)
    D=[[0]*N for _ in range(N)]
    for i in range(N):
        for j in range(N):
            if i!=j: D[i][j]=d(nodes[i],nodes[j])
    # nearest-neighbor order from node 0, ending at treasure (last node)
    start=0; end=N-1
    unvisited=set(range(1,N-1))
    order=[start]; cur=start
    while unvisited:
        nxt=min(unvisited, key=lambda j:D[cur][j])
        order.append(nxt); unvisited.discard(nxt); cur=nxt
    order.append(end)
    def tour_len(o): return sum(D[o[i]][o[i+1]] for i in range(len(o)-1))
    best=order[:]; blen=tour_len(best)
    # 2-opt (keep endpoints fixed)
    improved=True
    while improved:
        improved=False
        for i in range(1,len(best)-2):
            for k in range(i+1,len(best)-1):
                cand=best[:i]+best[i:k+1][::-1]+best[k+1:]
                cl=tour_len(cand)
                if cl<blen:
                    best=cand; blen=cl; improved=True
    return blen, len(objs)

ceiling_moves, nobj = pairwise_and_order()
print()
print(f"CEILING (2-opt TSP order, doors/spikes passable, {nobj} objectives):")
print(f"  best tour length ~ {ceiling_moves} moves (lower bound-ish; ignores relock/key gating)")
print(f"  current planner: 173 moves")
print(f"  theoretical headroom: ~{173-ceiling_moves} moves if order were optimal")
