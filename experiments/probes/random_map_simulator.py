"""
Randomized judge-map simulator.

Goal: determine what a 17,600-capable map draw looks like and whether the
current pathfinder captures it. Answers three questions:
  1. When spikes are AVOIDABLE, does the pathfinder achieve 0 spikes (5 lives)?
  2. How often are randomized maps "clean" (0 forced spikes)?
  3. Can coinsEarned exceed 14,350 (bigger maps) -> is 17,600 reachable
     without impossible tokenBonus?

Confirmed mechanics used for scoring:
  - coin c7 = 250
  - challenge points (observed): c2=600, c3=550, c4=800, c5=250, c1=100,
    c18=500, c41/c40=50 (key), c31/c30=1000 (door). We SUM whatever challenges
    the map contains (full clear assumed for reachable challenges).
  - lifeBonus = 250 * livesRemaining; start 5 lives; each DISTINCT spike hit -1
  - treasureBonus = 1000 (if treasure reached)
  - tokenBonus = 1000 - round(tokensUsed / challengesAttempted); we model a
    realistic tokensUsed to project (see project_score).
"""
import sys, random, json
sys.path.insert(0, '.')
for m in list(sys.modules):
    if 'mapanalyzer' in m:
        del sys.modules[m]
import mapanalyzer_lambda as M

MV = {'up': (-1, 0), 'down': (1, 0), 'left': (0, -1), 'right': (0, 1)}

# Challenge point values observed in real logs.
CHALLENGE_POINTS = {
    'c1': 100, 'c2': 600, 'c3': 550, 'c4': 800, 'c5': 250, 'c18': 500,
    'c40': 50, 'c41': 50, 'c30': 1000, 'c31': 1000,
}
COIN = 250


def _reachable_from(game_map, start, rows, cols, doors_open=True):
    """BFS reachable set. If doors_open, treat doors + spikes as passable."""
    from collections import deque
    seen = {start}
    q = deque([start])
    while q:
        r, c = q.popleft()
        for dr, dc, _ in M.DIRECTIONS:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            if (nr, nc) in seen:
                continue
            cell = game_map[nr][nc]
            if cell == 'wall':
                continue
            if not doors_open and M._is_door(cell):
                continue
            seen.add((nr, nc))
            q.append((nr, nc))
    return seen


def gen_random_map(rows, cols, rng, spike_style):
    """Generate a solvable map. spike_style in {'none','avoidable','forced'}.
    Returns (map, start, meta) or None if generation failed (retry)."""
    # Base: all normal.
    g = [['normal'] * cols for _ in range(rows)]
    start = (0, 0)
    treasure = (rng.randint(0, rows - 1), rng.randint(0, cols - 1))
    while treasure == start:
        treasure = (rng.randint(0, rows - 1), rng.randint(0, cols - 1))
    g[treasure[0]][treasure[1]] = 'treasure'

    cells = [(r, c) for r in range(rows) for c in range(cols)
             if (r, c) not in (start, treasure)]
    rng.shuffle(cells)

    # sprinkle walls (~18%)
    nwall = int(len(cells) * 0.18)
    walls = set(cells[:nwall])
    for (r, c) in walls:
        g[r][c] = 'wall'
    rest = [x for x in cells if x not in walls]

    # ensure start & treasure connected (doors/spikes open); if not, bail
    if treasure not in _reachable_from(g, start, rows, cols, doors_open=True):
        return None

    # place challenges: a realistic mix. counts scale with area.
    rng.shuffle(rest)
    area = rows * cols
    n_chal = max(6, int(area * 0.14))
    chal_pool = (['c5'] * 5 + ['c2'] * 2 + ['c4'] * 2 + ['c3'] * 1 +
                 ['c1'] * 3 + ['c18'] * 1)
    challenges = []
    for i in range(min(n_chal, len(rest))):
        code = rng.choice(chal_pool)
        r, c = rest[i]
        g[r][c] = code
        challenges.append((r, c, code))
    rest = rest[n_chal:]

    # optionally one key/door pair (green) in ~half the maps
    if rng.random() < 0.5 and len(rest) >= 4:
        kr, kc = rest[0]
        dr2, dc2 = rest[1]
        g[kr][kc] = 'c41'
        g[dr2][dc2] = 'c31'
        rest = rest[2:]

    # remaining -> coins
    for (r, c) in rest:
        g[r][c] = 'c7'

    # spikes according to style
    spikes = []
    walkable = [(r, c) for r in range(rows) for c in range(cols)
                if g[r][c] not in ('wall', 'treasure', 'start') and (r, c) != start]
    rng.shuffle(walkable)
    if spike_style == 'none':
        pass
    elif spike_style == 'avoidable':
        # place 1-2 spikes on tiles whose removal doesn't disconnect anything
        # heuristic: place on a cell that has >=3 non-wall neighbors (not a
        # bottleneck), and verify treasure still reachable without stepping on it.
        placed = 0
        for (r, c) in walkable:
            if placed >= 2:
                break
            nb = sum(1 for dr, dc, _ in M.DIRECTIONS
                     if 0 <= r + dr < rows and 0 <= c + dc < cols
                     and g[r + dr][c + dc] != 'wall')
            if nb >= 3:
                g[r][c] = 'c8'
                # check treasure still reachable avoiding spikes
                gg = [row[:] for row in g]
                # mark spikes as walls for avoidance test
                sp = [(rr, cc) for rr in range(rows) for cc in range(cols) if gg[rr][cc] == 'c8']
                for (sr, sc) in sp:
                    gg[sr][sc] = 'wall'
                if treasure in _reachable_from(gg, start, rows, cols, doors_open=True):
                    spikes.append((r, c)); placed += 1
                else:
                    g[r][c] = 'c7'  # revert; would force
    elif spike_style == 'forced':
        # place a spike on a genuine cut-vertex if we can find one
        for (r, c) in walkable:
            gg = [row[:] for row in g]
            gg[r][c] = 'wall'
            if treasure not in _reachable_from(gg, start, rows, cols, doors_open=True):
                g[r][c] = 'c8'; spikes.append((r, c)); break

    return g, start, {'treasure': treasure, 'challenges': challenges, 'spikes': spikes}


def simulate(game_map, start):
    """Run pathfinder, replay, return metrics."""
    rows, cols = len(game_map), len(game_map[0])
    try:
        path = M._pathfind(game_map, start)
    except Exception as e:
        return None
    r, c = start
    distinct_spikes = set()
    coins = 0
    chal_points = 0
    coin_cells = {(rr, cc) for rr in range(rows) for cc in range(cols) if game_map[rr][cc] == 'c7'}
    seen = set()
    for m in path:
        dr, dc = MV[m]
        nr, nc = r + dr, c + dc
        if not (0 <= nr < rows and 0 <= nc < cols) or game_map[nr][nc] == 'wall':
            break
        r, c = nr, nc
        cell = game_map[r][c]
        if cell == 'c8':
            distinct_spikes.add((r, c))
        if (r, c) in coin_cells and (r, c) not in seen:
            coins += 1; seen.add((r, c))
        if cell in CHALLENGE_POINTS and (r, c) not in seen:
            chal_points += CHALLENGE_POINTS[cell]; seen.add((r, c))
    # find treasure
    treasure = next(((rr, cc) for rr in range(rows) for cc in range(cols)
                     if game_map[rr][cc] == 'treasure'), None)
    ends_treasure = (r, c) == treasure
    total_chals = sum(1 for rr in range(rows) for cc in range(cols)
                      if game_map[rr][cc] in CHALLENGE_POINTS)
    reachable_coins = sum(1 for cell in coin_cells)
    return {
        'coins': coins, 'coins_total': len(coin_cells),
        'coin_pts': coins * COIN, 'chal_pts': chal_points,
        'distinct_spikes': len(distinct_spikes),
        'lives': 5 - len(distinct_spikes),
        'ends_treasure': ends_treasure,
        'total_chals': total_chals,
    }


def project_score(metrics, tokens_used=1900, challenges_attempted=19):
    if metrics is None:
        return None
    coins_earned = metrics['coin_pts'] + metrics['chal_pts']
    life_bonus = 250 * max(0, metrics['lives'])
    treasure_bonus = 1000 if metrics['ends_treasure'] else 0
    token_bonus = max(0, 1000 - round(tokens_used / challenges_attempted))
    return coins_earned + life_bonus + treasure_bonus + token_bonus


def project_calibrated(metrics, tokens_used=1900):
    """Project using the REAL judge-map economy: assume coinsEarned is fixed at
    the known full-clear value 14350 (28 coins + 14 challenges), and ONLY the
    lifeBonus varies with spikes. This isolates the lifeBonus lever, which is
    what actually determines 17,600 reachability on a real-sized map."""
    if metrics is None:
        return None
    COINS_EARNED_REAL = 14350
    life_bonus = 250 * max(0, metrics['lives'])
    treasure_bonus = 1000 if metrics['ends_treasure'] else 0
    token_bonus = max(0, 1000 - round(tokens_used / 19))
    return COINS_EARNED_REAL + life_bonus + treasure_bonus + token_bonus


if __name__ == '__main__':
    rng = random.Random(42)
    print("=== RANDOMIZED JUDGE-MAP SIMULATION ===\n")
    print("Structural test: does the pathfinder get 5 lives when spikes avoidable?\n")
    for style in ('none', 'avoidable', 'forced'):
        results = []
        attempts = 0
        while len(results) < 100 and attempts < 1000:
            attempts += 1
            rows = rng.choice([8, 9, 10, 10, 10])
            cols = rng.choice([8, 9, 10, 10, 10])
            out = gen_random_map(rows, cols, rng, style)
            if out is None:
                continue
            g, start, meta = out
            mtr = simulate(g, start)
            if mtr is None or not mtr['ends_treasure']:
                continue
            results.append(mtr)
        if not results:
            print(f"[{style}] no valid maps generated"); continue
        avg_spikes = sum(r['distinct_spikes'] for r in results) / len(results)
        five_life = sum(1 for r in results if r['lives'] == 5)
        print(f"[{style:9}] maps={len(results):3}  avg_distinct_spikes={avg_spikes:.2f}  "
              f"5-life(0 damage)={five_life:3}/{len(results)}  ({100*five_life/len(results):.0f}%)")

    # Calibrated projection: real coin economy (14350), tokenBonus at realistic best.
    print("\n--- CALIBRATED to real map economy (coinsEarned=14350 fixed) ---")
    print("Projected total = 14350 + 250*lives + 1000(treasure) + tokenBonus\n")
    for tb_tokens, label in [(1900, 'tokenBonus~900 (best real observed)'),
                             (1500, 'tokenBonus~921 (aggressive token opt)')]:
        tbonus = max(0, 1000 - round(tb_tokens/19))
        for lives in (5, 4, 3):
            total = 14350 + 250*lives + 1000 + tbonus
            print(f"  {label:42}  lives={lives} -> {total}")
        print()
