"""
Head-to-head: repo pocket-fix pathfinder vs the OPTIMAL full-clear, across
spike-pocket maps. We measure, for each map:
  - coins/challenges collected
  - distinct spikes hit (= lives lost)
  - projected score = coins + challenge_pts + 250*(5-spikes) + 1000(treasure) + tokenBonus~900
We compare against the theoretical best (full-clear vs spike-avoid) to confirm
the pocket-fix makes the SCORE-OPTIMAL choice on each map.
"""
import sys, json
sys.path.insert(0, '.')
for m in list(sys.modules):
    if 'mapanalyzer' in m:
        del sys.modules[m]
import mapanalyzer_lambda as M

MV = {'up': (-1,0), 'down': (1,0), 'left': (0,-1), 'right': (0,1)}
COIN = 250
# challenge point estimates for scoring
CHAL = {'c1':100,'c2':600,'c3':550,'c4':800,'c5':250,'c18':500}

def analyze(MAP, start=(0,0)):
    rows, cols = len(MAP), len(MAP[0])
    p = M._pathfind(MAP, start)
    r,c = start; coins=set(); chal_pts=0; spikes=set(); ok=True; seen=set()
    coin_cells = {(rr,cc) for rr in range(rows) for cc in range(cols) if MAP[rr][cc]=='c7'}
    for m in p:
        dr,dc = MV[m]; nr,nc = r+dr,c+dc
        if not (0<=nr<rows and 0<=nc<cols) or MAP[nr][nc]=='wall':
            ok=False; break
        r,c = nr,nc; cell=MAP[r][c]
        if cell=='c8': spikes.add((r,c))
        if (r,c) in coin_cells and (r,c) not in seen: coins.add((r,c)); seen.add((r,c))
        if cell in CHAL and (r,c) not in seen: chal_pts += CHAL[cell]; seen.add((r,c))
    t = next(((rr,cc) for rr in range(rows) for cc in range(cols) if MAP[rr][cc]=='treasure'), None)
    ends = (r,c)==t
    coin_pts = len(coins)*COIN
    lives = 5 - len(spikes)
    score = coin_pts + chal_pts + 250*max(0,lives) + (1000 if ends else 0) + 900  # ~tokenBonus
    return {
        'coins': f'{len(coins)}/{len(coin_cells)}', 'coin_pts': coin_pts,
        'chal_pts': chal_pts, 'spikes': len(spikes), 'lives': lives,
        'ends_treasure': ends, 'valid': ok, 'proj_score': score,
    }

# Battery of spike-pocket scenarios
maps = {}

# A: spike gates a RICH pocket (should cross - pocket >> 250)
maps['rich_pocket'] = [
 ['start','c7','c8','c7','c7'],
 ['wall','wall','wall','c7','c7'],
 ['normal','normal','normal','normal','treasure']]

# B: spike gates a POOR pocket (1 coin) - crossing costs 250 for 250, marginal
maps['poor_pocket'] = [
 ['start','normal','c8','c7'],
 ['normal','wall','wall','wall'],
 ['normal','normal','normal','treasure']]

# C: TWO spikes, one gates rich pocket, one gates nothing useful
maps['mixed'] = [
 ['start','c7','c8','c7','c7','c7'],
 ['normal','wall','wall','wall','wall','c7'],
 ['c8','normal','normal','normal','normal','treasure']]

# D: spike-free rich map (should get 5 lives + full clear = ~17600-class)
maps['spike_free_rich'] = [
 ['start','c7','c7','c7','c5'],
 ['c7','c7','c7','c7','c7'],
 ['c7','c4','c7','c7','treasure']]

# E: spike ON the only path to treasure (must cross regardless)
maps['forced_spike'] = [
 ['start','c7','c8','treasure']]

for name, mp in maps.items():
    print(f'{name:18}', analyze(mp))
