"""
Prove the one-time-toll model changes routing.

Board where a spike is the ONLY connection (cut-vertex) between the start side
and a coin cluster + treasure. The avatar MUST cross the spike to finish, and
must cross BACK to grab a coin behind it, then forward again.

OLD model: each crossing = SPIKE_COST, so it would avoid re-crossing -> skip the
           coin behind the spike (undervalue it).
NEW model: pay toll ONCE, re-cross freely -> grab the extra coin, still 1 life.
"""
import sys, json
sys.path.insert(0, '/projects/sandbox/agenticleague')
for m in list(sys.modules):
    if 'mapanalyzer' in m:
        del sys.modules[m]
import mapanalyzer_lambda as M

# 3 rows, 5 cols. Single horizontal corridor. Spike at (0,2) is the only path.
# Layout:  start  c7   c8   c7   treasure
#          wall   wall wall wall wall
#  A coin pocket hangs BELOW the far side, reachable only by going back-and-forth
#  is overkill; simpler: put a coin at each end of a corridor bisected by a spike.
#  col:   0       1     2     3       4
MAP = [
 ['start', 'c7',  'c8',  'c7',  'treasure'],
]
MV = {'up':(-1,0),'down':(1,0),'left':(0,-1),'right':(0,1)}
def lbl(r,c): return chr(65+c)+str(r+1)

p = M._pathfind(MAP,(0,0))
r,c=0,0; contacts=[]; distinct=set(); coins=0; ok=True
coin_cells={(rr,cc) for rr in range(len(MAP)) for cc in range(len(MAP[0])) if MAP[rr][cc]=='c7'}
seen=set()
for m in p:
    dr,dc=MV[m]; nr,nc=r+dr,c+dc
    if not(0<=nr<len(MAP) and 0<=nc<len(MAP[0])) or MAP[nr][nc]=='wall':
        ok=False; break
    r,c=nr,nc
    if MAP[r][c]=='c8': contacts.append(lbl(r,c)); distinct.add(lbl(r,c))
    if (r,c) in coin_cells and (r,c) not in seen: coins+=1; seen.add((r,c))
print('CORRIDOR TEST (spike is sole path to treasure):')
print(' path:', p)
print(' len:', len(p), 'valid:', ok, 'ends treasure:', (r,c)==(0,4))
print(' coins:', coins, '/', len(coin_cells), ' spike contacts:', len(contacts), contacts)
print(' DISTINCT spikes (life cost):', len(distinct), sorted(distinct))
print()

# Second board: prove FREE RE-CROSS. Coin behind spike that requires going
# past the spike, grabbing a dead-end coin, coming BACK across the same spike,
# then to treasure on the near side.
#  col:    0       1      2      3
#  row0:  start   c8     c7    (dead-end coin)
#  row0 treasure is at col0-adjacent? put treasure below start.
MAP2 = [
 ['start', 'c8',  'c7',  'c7'],
 ['treasure','wall','wall','wall'],
]
for m in list(sys.modules):
    if 'mapanalyzer' in m: del sys.modules[m]
import mapanalyzer_lambda as M2
p2 = M2._pathfind(MAP2,(0,0))
r,c=0,0; contacts=[]; distinct=set(); coins=0; ok=True
coin_cells={(rr,cc) for rr in range(len(MAP2)) for cc in range(len(MAP2[0])) if MAP2[rr][cc]=='c7'}
seen=set()
for m in p2:
    dr,dc=MV[m]; nr,nc=r+dr,c+dc
    if not(0<=nr<len(MAP2) and 0<=nc<len(MAP2[0])) or MAP2[nr][nc]=='wall':
        ok=False; break
    r,c=nr,nc
    if MAP2[r][c]=='c8': contacts.append(lbl(r,c)); distinct.add(lbl(r,c))
    if (r,c) in coin_cells and (r,c) not in seen: coins+=1; seen.add((r,c))
print('FREE-RECROSS TEST (grab coins past spike, return across same spike):')
print(' path:', p2)
print(' len:', len(p2), 'valid:', ok, 'ends treasure:', (r,c)==(1,0))
print(' coins:', coins, '/', len(coin_cells), ' spike contacts:', len(contacts), contacts)
print(' DISTINCT spikes (life cost):', len(distinct), sorted(distinct))
print()
print(' EXPECTED: 2 coins collected, spike crossed 2x physically, life cost = 1.')
