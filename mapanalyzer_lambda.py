import json
import re
import heapq
from collections import deque

# --- Generic tile classification (NO hardcoded challenge allowlist) ---
# A tile is a COIN if it matches c7. It is a CHALLENGE if it is a c<N> tile that
# is not a coin, spike, key, or door. Keys/doors/spikes detected by pattern.
COIN_TILES = {"c7"}
SPIKE_TILES = {"c8"}
NONWALK_BASE = {"wall"}
DIRECTIONS = [(-1, 0, "up"), (1, 0, "down"), (0, -1, "left"), (0, 1, "right")]

# Key/door codes. Keys c40/c41; doors c30/c31. Pair by trailing digit:
#   red   key c40 <-> door c30
#   green key c41 <-> door c31
def _is_key(cell):
    return bool(re.fullmatch(r"c4\d", cell or ""))

def _is_door(cell):
    return bool(re.fullmatch(r"c3\d", cell or ""))

def _door_for_key(cell):
    # c40 -> c30, c41 -> c31 (swap the '4' tens digit for '3')
    return "c3" + cell[2:]

def _is_challenge(cell):
    if not cell:
        return False
    if cell in COIN_TILES or cell in SPIKE_TILES or cell in NONWALK_BASE:
        return False
    if cell in ("normal", "treasure", "start"):
        return False
    if _is_key(cell) or _is_door(cell):
        return False
    return bool(re.fullmatch(r"c\d+", cell))  # any other c<N> is a challenge


def _extract_params(event):
    if 'parameters' in event and isinstance(event['parameters'], list):
        params = {}
        for p in event['parameters']:
            name = p.get('name', '')
            value = p.get('value', '')
            try:
                params[name] = json.loads(value) if isinstance(value, str) else value
            except (json.JSONDecodeError, TypeError):
                params[name] = value
        return params
    if 'body' in event:
        body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        return body
    return event


def _parse_start(pos):
    """Parse a start position from any format into (row_index, col_index), 0-based.
    Handles: 'A1' (col letter + 1-based row), [row,col] list/tuple,
    and numeric strings like '[1, 0]', '1,0', '(2,3)', 'row0col0'."""
    try:
        # List/tuple form
        if isinstance(pos, (list, tuple)):
            if len(pos) == 1:
                return _parse_start(pos[0])
            if len(pos) >= 2:
                a = re.sub(r'[^A-Za-z0-9]', '', str(pos[0]))
                b = re.sub(r'[^A-Za-z0-9]', '', str(pos[1]))
                if a.isalpha():                       # ['A','1'] -> letter=col, num=row
                    return (int(b) - 1, ord(a.upper()) - ord('A'))
                return (int(a), int(b))               # [row, col]
        s = str(pos)
        # Chess-style "A1" / "B3": a letter followed by digits => col letter, 1-based row
        mm = re.search(r'([A-Za-z])\s*[,;:]?\s*(\d+)', s)
        # Only treat as chess-style if it's genuinely letter-then-number with no leading digits
        chess = re.match(r'^\s*[\[\(]?\s*([A-Za-z])\s*(\d+)\s*[\]\)]?\s*$', s)
        if chess:
            return (int(chess.group(2)) - 1, ord(chess.group(1).upper()) - ord('A'))
        # Otherwise pull ALL numbers from the ORIGINAL string (before stripping separators)
        nums = re.findall(r'\d+', s)
        if len(nums) >= 2:                            # "[1, 0]" / "1,0" / "(2,3)" -> row,col
            return (int(nums[0]), int(nums[1]))
        # dict-ish "row0col0"
        rc = re.search(r'row\s*(\d+).*?col\s*(\d+)', s, re.IGNORECASE)
        if rc:
            return (int(rc.group(1)), int(rc.group(2)))
        if len(nums) == 1:
            return (int(nums[0]), 0)
    except (ValueError, TypeError, IndexError):
        pass
    return (0, 0)


# --- Spike-weighted shortest path (state-augmented Dijkstra) ---
# CONFIRMED game mechanic (F7 probe: 3 physical contacts -> exactly 1 damage
# event): a spike tile is a ONE-TIME TOLL. The FIRST time the avatar enters a
# given spike tile it costs 1 life; every SUBSEQUENT entry of that SAME tile is
# FREE. So spike cost is path-dependent: it depends on which spikes have already
# been triggered earlier on the route.
#
# We model this by augmenting the search state with the set of spikes already
# triggered. Entering a spike:
#   - already in `triggered`  -> step cost 1 (free highway, re-crossing)
#   - not yet triggered       -> step cost SPIKE_COST (pay the toll once)
# `already_triggered` seeds spikes paid for in PRIOR planner segments so later
# trips reuse them for free. The number of DISTINCT NEW tolls paid on a route is
# cost // SPIKE_COST (path length always << SPIKE_COST on a real board).
SPIKE_COST = 100000

def _dijkstra(game_map, rows, cols, start, goal, blocked, open_cells,
              already_triggered=None):
    """
    blocked: set of cells treated as walls (e.g. locked doors).
    open_cells: set of cells force-walkable (e.g. an unlocked door, or start-trapped spikes).
    already_triggered: set of spike (r,c) already paid for in earlier segments;
        entering these is FREE.
    Returns (path_moves, new_spikes_triggered_set) or (None, None).
    The second value is the SET of spike tiles this route triggers for the FIRST
    time (empty set if none). len(...) is the life cost of taking this route.
    """
    if already_triggered is None:
        already_triggered = frozenset()
    else:
        already_triggered = frozenset(already_triggered)

    start_state = (start[0], start[1], already_triggered)
    dist = {start_state: 0}
    # heap entries: (cost, r, c, triggered_frozenset, path)
    pq = [(0, start[0], start[1], already_triggered, [])]
    while pq:
        cost, r, c, triggered, path = heapq.heappop(pq)
        if (r, c) == goal:
            new_spikes = set(triggered) - set(already_triggered)
            return path, new_spikes
        if cost > dist.get((r, c, triggered), float('inf')):
            continue
        for dr, dc, move in DIRECTIONS:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            if (nr, nc) in blocked:
                continue
            cell = game_map[nr][nc]
            forced_open = (nr, nc) in open_cells or (nr, nc) == goal
            if not forced_open:
                if cell in NONWALK_BASE:
                    continue
                if _is_door(cell):   # locked door acts as wall unless in open_cells/goal
                    continue
            ntrig = triggered
            if cell in SPIKE_TILES and (nr, nc) not in triggered:
                step = SPIKE_COST                       # first entry: pay the toll
                ntrig = triggered | frozenset({(nr, nc)})
            else:
                step = 1                                # normal step OR free re-cross
            ncost = cost + step
            nstate = (nr, nc, ntrig)
            if ncost < dist.get(nstate, float('inf')):
                dist[nstate] = ncost
                heapq.heappush(pq, (ncost, nr, nc, ntrig, path + [move]))
    return None, None


def _find_start_exit(game_map, rows, cols, start_pos):
    """If the avatar is walled in with only spikes adjacent, allow stepping onto them."""
    r, c = start_pos
    allow = set()
    has_free = False
    for dr, dc, _ in DIRECTIONS:
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            cell = game_map[nr][nc]
            if cell not in NONWALK_BASE and cell not in SPIKE_TILES and not _is_door(cell):
                has_free = True
                break
    if not has_free:
        for dr, dc, _ in DIRECTIONS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and game_map[nr][nc] in SPIKE_TILES:
                allow.add((nr, nc))
    return allow


def _pathfind(game_map, start_pos, life_value=250):
    rows = len(game_map)
    cols = len(game_map[0])
    board = [row[:] for row in game_map]
    r, c = start_pos
    full_path = []
    open_cells = _find_start_exit(game_map, rows, cols, start_pos)

    # locate special tiles
    treasure = None
    keys = {}      # cell_code -> (r,c)
    doors = {}     # cell_code -> (r,c)
    for row in range(rows):
        for col in range(cols):
            cell = board[row][col]
            if cell == 'treasure':
                treasure = (row, col)
            elif _is_key(cell):
                keys[cell] = (row, col)
            elif _is_door(cell):
                doors[cell] = (row, col)
    if not treasure:
        return []

    locked_doors = set(doors.values())
    keys_held = set()          # door codes we can open (matched key collected)
    key_pos_by_code = dict(keys)
    door_pos_by_code = dict(doors)

    # Persistent set of spike tiles already triggered (paid for) so far on the
    # actual route. Seeds every _dijkstra call: re-crossing a paid spike is free.
    triggered_spikes = set()

    def value_of(cell):
        if cell in COIN_TILES:
            return 250
        if _is_challenge(cell):
            return 400  # conservative; challenges always worth >= a life -> always take
        return 0

    def commit(path, new_spikes, dest):
        """Apply a chosen route: record it, advance position, mark spikes paid."""
        nonlocal r, c
        full_path.extend(path)
        r, c = dest
        triggered_spikes.update(new_spikes)

    def pocket_value(new_spikes):
        """Total reward reachable ONCE we pay for `new_spikes` (i.e. treating those
        spikes as free-crossable highways from now on). This is the PCOP pocket
        insight: a spike gates a POCKET, so crossing it once unlocks EVERYTHING
        beyond it, not just the single next tile. Sum coins+challenges reachable
        with the new spikes considered already-triggered."""
        if not new_spikes:
            return 0
        seed = set(triggered_spikes) | set(new_spikes)
        total = 0
        for rr in range(rows):
            for cc in range(cols):
                cell = board[rr][cc]
                if not (cell in COIN_TILES or _is_challenge(cell)):
                    continue
                p, ns = _dijkstra(board, rows, cols, (r, c), (rr, cc),
                                  blocked=locked_doors, open_cells=open_cells,
                                  already_triggered=seed)
                # reachable using ONLY the spikes we're about to pay for (no extra new ones)
                if p is not None and not (set(ns) - set(new_spikes)):
                    total += value_of(cell)
        return total

    def worth_crossing(new_spikes):
        """Cross the new spikes iff total reward they unlock exceeds their life cost.
        1 spike = 1 life = life_value (250) lost lifeBonus."""
        if not new_spikes:
            return True
        return pocket_value(new_spikes) >= len(new_spikes) * life_value

    def go_to(goal, force_take=False):
        """Move to goal via fewest-NEW-spike path (locked doors block).
        Only NEW (un-paid) spikes count toward life cost; already-paid spikes are
        free highways. Cross new spikes iff the POCKET they unlock is worth it."""
        path, new_spikes = _dijkstra(board, rows, cols, (r, c), goal,
                                     blocked=locked_doors - {goal}, open_cells=open_cells,
                                     already_triggered=triggered_spikes)
        if path is None:
            return False
        if new_spikes and not force_take and not worth_crossing(new_spikes):
            return False
        commit(path, new_spikes, goal)
        return True

    def sweep():
        """Collect all currently-reachable coins/challenges, fewest-NEW-spikes then nearest."""
        for _ in range(400):
            best = None
            for row in range(rows):
                for col in range(cols):
                    cell = board[row][col]
                    if not (cell in COIN_TILES or _is_challenge(cell)):
                        continue
                    if (row, col) == (r, c):
                        continue
                    path, new_spikes = _dijkstra(board, rows, cols, (r, c), (row, col),
                                                 blocked=locked_doors, open_cells=open_cells,
                                                 already_triggered=triggered_spikes)
                    if path is None:
                        continue
                    # Pocket-value: cross new spikes only if the whole pocket they
                    # unlock is worth the life cost (not just this single tile).
                    if new_spikes and not worth_crossing(new_spikes):
                        continue
                    key = (len(new_spikes), len(path))
                    if best is None or key < best[0]:
                        best = (key, path, new_spikes, (row, col))
            if not best:
                break
            _, path, new_spikes, tgt = best
            commit(path, new_spikes, tgt)
            board[tgt[0]][tgt[1]] = 'normal'

    def collect_keys():
        """Pick up every currently-reachable key (keys gate +1000 doors -> force)."""
        progressed = True
        while progressed:
            progressed = False
            for kcode, kpos in list(key_pos_by_code.items()):
                if board[kpos[0]][kpos[1]] == 'normal':
                    continue  # already taken
                path, new_spikes = _dijkstra(board, rows, cols, (r, c), kpos,
                                             blocked=locked_doors, open_cells=open_cells,
                                             already_triggered=triggered_spikes)
                if path is None:
                    continue
                commit(path, new_spikes, kpos)
                board[kpos[0]][kpos[1]] = 'normal'
                keys_held.add(_door_for_key(kcode))
                progressed = True

    def open_doors():
        """Walk onto any door whose key we hold (unlocks + passes through). Force-take."""
        progressed = False
        for dcode in list(keys_held):
            dpos = door_pos_by_code.get(dcode)
            if dpos is None or dpos not in locked_doors:
                continue
            path, new_spikes = _dijkstra(board, rows, cols, (r, c), dpos,
                                         blocked=locked_doors - {dpos}, open_cells=open_cells,
                                         already_triggered=triggered_spikes)
            if path is None:
                continue
            commit(path, new_spikes, dpos)
            board[dpos[0]][dpos[1]] = 'normal'
            locked_doors.discard(dpos)
            progressed = True
        return progressed

    # Topology-driven loop: sweep, grab reachable keys, open reachable doors, repeat
    # until nothing new opens. Handles nested pockets (green door -> red door).
    for _ in range(20):
        sweep()
        collect_keys()
        opened = open_doors()
        # after opening, keys inside the new pocket may now be reachable
        collect_keys()
        if not opened and not any(board[kp[0]][kp[1]] != 'normal' for kp in key_pos_by_code.values()):
            # nothing left to open and all keys collected -> final sweep then done
            sweep()
            if not any(dp in locked_doors for dp in door_pos_by_code.values()):
                break

    # 4) go to treasure (must-take; already-paid spikes are free highways)
    path, _new = _dijkstra(board, rows, cols, (r, c), treasure,
                           blocked=set(), open_cells=open_cells,
                           already_triggered=triggered_spikes)
    if path is not None:
        full_path.extend(path)
        return full_path

    # fallback: shouldn't happen, but never forfeit the treasure
    path, _ = _dijkstra(board, rows, cols, start_pos, treasure,
                        blocked=set(), open_cells=open_cells)
    return path or full_path


def _replay_end(game_map, rows, cols, start, path):
    """Replay path (stopping at walls/edges) and return the final valid position."""
    mv = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}
    r, c = start
    for m in path:
        dr, dc = mv.get(m, (0, 0))
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols and game_map[nr][nc] != "wall":
            r, c = nr, nc
        else:
            break
    return (r, c)


def _ensure_treasure(game_map, rows, cols, start, path):
    """Guarantee the returned path ends on the treasure when it is reachable
    at all. Doors and spikes are treated as passable for this safety route so
    the avatar is never stranded and the +1000 treasure is never forfeited."""
    treasure = None
    for r in range(rows):
        for c in range(cols):
            if game_map[r][c] == 'treasure':
                treasure = (r, c)
                break
        if treasure:
            break
    if treasure is None:
        return path  # no treasure on this map; nothing to guarantee

    end = _replay_end(game_map, rows, cols, start, path)
    if end == treasure:
        return path

    # Append a route from wherever the plan left us to the treasure.
    # Doors passable (open_cells = all doors), spikes crossable.
    all_doors = {(r, c) for r in range(rows) for c in range(cols) if _is_door(game_map[r][c])}
    tail, _ = _dijkstra(game_map, rows, cols, end, treasure,
                        blocked=set(), open_cells=all_doors)
    if tail:
        return list(path) + tail
    # Last resort: fresh route straight from start.
    direct, _ = _dijkstra(game_map, rows, cols, start, treasure,
                         blocked=set(), open_cells=all_doors)
    return direct if direct is not None else path


def _normalize_map(game_map):
    """Coerce to a rectangular grid of strings. Pads short rows, replaces
    non-string / empty cells with 'normal'. Never raises."""
    if not isinstance(game_map, list) or not game_map:
        return []
    rows = []
    for row in game_map:
        if isinstance(row, list):
            rows.append([str(x) if x is not None else 'normal' for x in row])
        elif row is None:
            rows.append([])
        else:
            rows.append([str(row)])
    max_cols = max((len(r) for r in rows), default=0)
    if max_cols == 0:
        return []
    return [r + ['normal'] * (max_cols - len(r)) for r in rows]


def lambda_handler(event, context):
    params = _extract_params(event)
    game_map = (params.get('game_map') or params.get('map') or
                params.get('maze') or params.get('grid') or [])
    if isinstance(game_map, str):
        try:
            game_map = json.loads(game_map)
        except (json.JSONDecodeError, TypeError):
            game_map = []
    game_map = _normalize_map(game_map)
    action = params.get('action', 'count')
    tile = params.get('tile', '')
    if not game_map:
        return {"result": "0", "success": False, "error": "No map provided"}

    if action == 'count':
        count = sum(1 for row in game_map for cell in row if cell == tile)
        return {"result": str(count), "success": True}
    elif action == 'find':
        pos = [[r, c] for r in range(len(game_map)) for c in range(len(game_map[r])) if game_map[r][c] == tile]
        return {"result": json.dumps(pos), "success": True, "count": len(pos)}
    elif action == 'pathfind':
        raw_start = (params.get('start_pos') or params.get('start') or
                     params.get('position') or params.get('playerStart') or [0, 0])
        if isinstance(raw_start, dict):
            start_pos = (raw_start.get('row', 0), raw_start.get('col', 0))
        else:
            start_pos = _parse_start(raw_start)
        rows, cols = len(game_map), len(game_map[0])
        if not (0 <= start_pos[0] < rows and 0 <= start_pos[1] < cols):
            start_pos = (0, 0)

        # Primary planner, fully guarded: any error falls back to a safe route.
        try:
            path = _pathfind(game_map, start_pos)
        except Exception as e:
            print(f"PATHFIND ERROR (falling back): {type(e).__name__}: {e}")
            path = []

        # Guaranteed treasure fallback: if the plan does not end on the treasure,
        # append/return a spike-and-door-allowed route to the treasure so we never
        # strand the avatar or forfeit the +1000 (only skipped if truly unreachable).
        path = _ensure_treasure(game_map, rows, cols, start_pos, path)

        # Validation: never emit a move that walks into a wall or off-grid.
        validated = []
        cr, cc = start_pos
        mv = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}
        for mve in path:
            dr, dc = mv.get(mve, (0, 0))
            nr, nc = cr + dr, cc + dc
            if 0 <= nr < rows and 0 <= nc < cols and game_map[nr][nc] != "wall":
                validated.append(mve)
                cr, cc = nr, nc
            else:
                break
        return {"result": json.dumps(validated), "success": True, "steps": len(validated)}
    else:
        return {"result": "0", "success": False, "error": f"Unknown action: {action}"}
