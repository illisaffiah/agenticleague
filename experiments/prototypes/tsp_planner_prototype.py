"""
Prototype TSP-ordered full-clear planner honoring key->door gating and the
one-time-toll spike model. Goal: full-clear in far fewer moves than the greedy
173 by optimizing visit ORDER, while NEVER losing an objective or extra life.

Strategy:
  1. Partition objectives by which "region" they live in:
       - free region (reachable without any door)
       - behind green door only
       - behind red door only / nested
     We don't hardcode colors; we compute reachability with each door locked.
  2. Collect keys first (they gate +1000 doors). Determine a phase order:
       free objectives -> get key(s) -> open door -> pocket objectives -> ...
     But instead of greedy nearest, we 2-opt the order WITHIN each reachable
     phase, then stitch phases with the door transitions.
  3. Always end on treasure.

Validated offline against the baseline before any deployment.
"""
import sys
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
ROWS,COLS=10,10
MV={'up':(-1,0),'down':(1,0),'left':(0,-1),'right':(0,1)}
def lbl(r,c): return chr(65+c)+str(r+1)

def evaluate(path, start=(0,0)):
    r,c=start; distinct=set(); coins=set(); chals=set(); ok=True
    coin_cells={(rr,cc) for rr in range(ROWS) for cc in range(COLS) if MAP[rr][cc]=='c7'}
    chal_cells={(rr,cc) for rr in range(ROWS) for cc in range(COLS) if M._is_challenge(MAP[rr][cc])}
    key_cells={(rr,cc) for rr in range(ROWS) for cc in range(COLS) if M._is_key(MAP[rr][cc])}
    door_cells={(rr,cc) for rr in range(ROWS) for cc in range(COLS) if M._is_door(MAP[rr][cc])}
    keys_seen=set(); doors_seen=set(); order_ok=True
    for m in path:
        dr,dc=MV[m]; nr,nc=r+dr,c+dc
        if not(0<=nr<ROWS and 0<=nc<COLS) or MAP[nr][nc]=='wall':
            ok=False; break
        r,c=nr,nc
        if MAP[r][c]=='c8': distinct.add((r,c))
        if (r,c) in coin_cells: coins.add((r,c))
        if (r,c) in chal_cells: chals.add((r,c))
        if (r,c) in key_cells: keys_seen.add(MAP[r][c])
        if (r,c) in door_cells:
            dcode=MAP[r][c]; kcode='c4'+dcode[2:]
            if kcode not in keys_seen: order_ok=False
            doors_seen.add((r,c))
    return {'moves':len(path),'valid':ok,'ends_treasure':(r,c)==(0,9),
            'coins':len(coins),'coins_total':len(coin_cells),
            'chals':len(chals),'chals_total':len(chal_cells),
            'keys':len(keys_seen),'keys_total':len(key_cells),
            'doors':len(doors_seen),'doors_total':len(door_cells),
            'lives_lost':len(distinct),'key_before_door':order_ok,
            'spikes':sorted(lbl(*s) for s in distinct)}


def _two_opt(order, D, fixed_start=True, fixed_end=True):
    def tl(o): return sum(D[o[i]][o[i+1]] for i in range(len(o)-1))
    best=order[:]; blen=tl(best)
    lo = 1 if fixed_start else 0
    hi = len(best)-1 if fixed_end else len(best)
    improved=True
    while improved:
        improved=False
        for i in range(lo, hi-1):
            for k in range(i+1, hi):
                cand=best[:i]+best[i:k+1][::-1]+best[k+1:]
                cl=tl(cand)
                if cl < blen - 1e-9:
                    best=cand; blen=cl; improved=True
    return best


def plan_tsp():
    board=[row[:] for row in MAP]
    r,c=0,0; full=[]; triggered=set()
    open_start=M._find_start_exit(MAP,ROWS,COLS,(0,0))
    treasure=None; keys={}; doors={}
    for rr in range(ROWS):
        for cc in range(COLS):
            cell=board[rr][cc]
            if cell=='treasure': treasure=(rr,cc)
            elif M._is_key(cell): keys[cell]=(rr,cc)
            elif M._is_door(cell): doors[cell]=(rr,cc)
    locked=set(doors.values())
    keys_held=set()

    def route(a,b,blocked):
        return M._dijkstra(board,ROWS,COLS,a,b,blocked=blocked,
                           open_cells=open_start,already_triggered=triggered)
    def commit(p,ns,dest):
        nonlocal r,c
        full.extend(p); r,c=dest; triggered.update(ns)
    def value_of(cell):
        if cell in M.COIN_TILES: return 250
        if M._is_challenge(cell): return 400
        return 0

    def reachable_objs():
        out=[]
        for rr in range(ROWS):
            for cc in range(COLS):
                cell=board[rr][cc]
                if not (cell in M.COIN_TILES or M._is_challenge(cell)): continue
                if (rr,cc)==(r,c): continue
                p,ns=route((r,c),(rr,cc),blocked=locked)
                if p is None: continue
                if ns and value_of(cell) < len(ns)*250: continue
                out.append((rr,cc))
        return out

    def tsp_sweep():
        """Collect all currently-reachable objectives in 2-opt-optimized order."""
        nonlocal r,c
        while True:
            objs=reachable_objs()
            if not objs: break
            nodes=[(r,c)]+objs
            N=len(nodes)
            D=[[0]*N for _ in range(N)]
            reachable_ok=True
            for i in range(N):
                for j in range(N):
                    if i==j: continue
                    p,_=route(nodes[i],nodes[j],blocked=locked)
                    D[i][j]=len(p) if p is not None else 10**6
            # nearest-neighbor seed from current pos (node 0), open end
            unv=set(range(1,N)); order=[0]; cur=0
            while unv:
                nxt=min(unv,key=lambda j:D[cur][j]); order.append(nxt); unv.discard(nxt); cur=nxt
            order=_two_opt(order,D,fixed_start=True,fixed_end=False)
            # walk the order, committing each hop; re-plan if board changed enough
            moved=False
            for idx in order[1:]:
                dest=nodes[idx]
                if board[dest[0]][dest[1]]=='normal': continue
                p,ns=route((r,c),dest,blocked=locked)
                if p is None: continue
                if ns and value_of(board[dest[0]][dest[1]]) < len(ns)*250: continue
                commit(p,ns,dest); board[dest[0]][dest[1]]='normal'; moved=True
            if not moved: break

    def collect_keys():
        nonlocal r,c
        prog=True
        while prog:
            prog=False
            for kcode,kpos in list(keys.items()):
                if board[kpos[0]][kpos[1]]=='normal': continue
                p,ns=route((r,c),kpos,blocked=locked)
                if p is None: continue
                commit(p,ns,kpos); board[kpos[0]][kpos[1]]='normal'
                keys_held.add(M._door_for_key(kcode)); prog=True

    def open_doors():
        nonlocal r,c
        prog=False
        for dcode in list(keys_held):
            dpos=doors.get(dcode)
            if dpos is None or dpos not in locked: continue
            p,ns=route((r,c),dpos,blocked=locked-{dpos})
            if p is None: continue
            commit(p,ns,dpos); board[dpos[0]][dpos[1]]='normal'; locked.discard(dpos); prog=True
        return prog

    for _ in range(20):
        tsp_sweep(); collect_keys(); opened=open_doors(); collect_keys()
        if not opened and not any(board[kp[0]][kp[1]]!='normal' for kp in keys.values()):
            tsp_sweep()
            if not any(dp in locked for dp in doors.values()): break

    p,ns=M._dijkstra(board,ROWS,COLS,(r,c),treasure,blocked=set(),
                     open_cells=open_start,already_triggered=triggered)
    if p is not None: full.extend(p)
    return full


baseline = M._pathfind(MAP,(0,0))
tsp = plan_tsp()
print("BASELINE :", evaluate(baseline))
print()
print("TSP      :", evaluate(tsp))
print()
be, te = evaluate(baseline), evaluate(tsp)
full_clear = (te['coins']==te['coins_total'] and te['chals']==te['chals_total']
              and te['keys']==te['keys_total'] and te['doors']==te['doors_total']
              and te['ends_treasure'] and te['valid'] and te['key_before_door']
              and te['lives_lost']<=be['lives_lost'])
print(f"TSP full-clear & no-regression: {full_clear}")
print(f"moves: baseline {be['moves']} -> tsp {te['moves']}  (saved {be['moves']-te['moves']})")
