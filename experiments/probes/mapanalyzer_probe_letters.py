import json
import re
import heapq

# =====================================================================
# TEMPORARY MOVE-FORMAT PROBE build of the map/path tool.
# Returns the SAME optimal path but as SINGLE-LETTER moves (u/d/l/r) to
# test whether the game's move parser accepts abbreviated moves.
#   - If the avatar MOVES normally on practice -> format accepted -> big token win
#   - If the avatar does NOT move -> revert immediately (practice, no harm)
# Keeps count/find analysis intact so c3 still works during the probe.
# REVERT to the real tool after ONE practice run.
# =====================================================================

COIN_TILES = {"c7"}
SPIKE_TILES = {"c8"}
NONWALK_BASE = {"wall"}
DIRECTIONS = [(-1, 0, "up"), (1, 0, "down"), (0, -1, "left"), (0, 1, "right")]
SPIKE_COST = 100000
LETTER = {"up": "u", "down": "d", "left": "l", "right": "r"}


def _is_key(c): return bool(re.fullmatch(r"c4\d", c or ""))
def _is_door(c): return bool(re.fullmatch(r"c3\d", c or ""))
def _door_for_key(c): return "c3" + c[2:]
def _is_challenge(c):
    if not c: return False
    if c in COIN_TILES or c in SPIKE_TILES or c in NONWALK_BASE: return False
    if c in ("normal", "treasure", "start"): return False
    if _is_key(c) or _is_door(c): return False
    return bool(re.fullmatch(r"c\d+", c))


def _parse_start(pos):
    try:
        if isinstance(pos, (list, tuple)):
            if len(pos) >= 2:
                a = re.sub(r'[^A-Za-z0-9]', '', str(pos[0]))
                b = re.sub(r'[^A-Za-z0-9]', '', str(pos[1]))
                if a.isalpha():
                    return (int(b) - 1, ord(a.upper()) - ord('A'))
                return (int(a), int(b))
        s = str(pos)
        chess = re.match(r'^\s*[\[\(]?\s*([A-Za-z])\s*(\d+)\s*[\]\)]?\s*$', s)
        if chess:
            return (int(chess.group(2)) - 1, ord(chess.group(1).upper()) - ord('A'))
        nums = re.findall(r'\d+', s)
        if len(nums) >= 2:
            return (int(nums[0]), int(nums[1]))
    except Exception:
        pass
    return (0, 0)


def _dijkstra(gm, rows, cols, start, goal, blocked, open_cells, trig=None):
    trig = frozenset(trig or ())
    dist = {(start[0], start[1], trig): 0}
    pq = [(0, start[0], start[1], trig, [])]
    while pq:
        cost, r, c, tr, path = heapq.heappop(pq)
        if (r, c) == goal:
            return path, set(tr) - set(trig)
        if cost > dist.get((r, c, tr), float('inf')):
            continue
        for dr, dc, mv in DIRECTIONS:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols): continue
            if (nr, nc) in blocked: continue
            cell = gm[nr][nc]
            fo = (nr, nc) in open_cells or (nr, nc) == goal
            if not fo:
                if cell in NONWALK_BASE: continue
                if _is_door(cell): continue
            nt = tr
            if cell in SPIKE_TILES and (nr, nc) not in tr:
                step = SPIKE_COST; nt = tr | frozenset({(nr, nc)})
            else:
                step = 1
            nco = cost + step
            ns = (nr, nc, nt)
            if nco < dist.get(ns, float('inf')):
                dist[ns] = nco
                heapq.heappush(pq, (nco, nr, nc, nt, path + [mv]))
    return None, None


def _pathfind(gm, start):
    rows, cols = len(gm), len(gm[0])
    board = [row[:] for row in gm]
    r, c = start
    full = []
    open_cells = set()
    treasure = None; keys = {}; doors = {}
    for R in range(rows):
        for C in range(cols):
            cell = board[R][C]
            if cell == 'treasure': treasure = (R, C)
            elif _is_key(cell): keys[cell] = (R, C)
            elif _is_door(cell): doors[cell] = (R, C)
    if not treasure: return []
    locked = set(doors.values()); held = set(); trig = set()

    def val(cell):
        if cell in COIN_TILES: return 250
        if _is_challenge(cell): return 400
        return 0

    def commit(p, ns, dest):
        nonlocal r, c
        full.extend(p); r, c = dest; trig.update(ns)

    def sweep():
        for _ in range(400):
            best = None
            for R in range(rows):
                for C in range(cols):
                    cell = board[R][C]
                    if not (cell in COIN_TILES or _is_challenge(cell)): continue
                    if (R, C) == (r, c): continue
                    p, ns = _dijkstra(board, rows, cols, (r, c), (R, C), locked, open_cells, trig)
                    if p is None: continue
                    if ns and val(cell) < len(ns) * 250: continue
                    k = (len(ns), len(p))
                    if best is None or k < best[0]: best = (k, p, ns, (R, C))
            if not best: break
            _, p, ns, t = best
            commit(p, ns, t); board[t[0]][t[1]] = 'normal'

    def collect_keys():
        prog = True
        while prog:
            prog = False
            for kc, kp in list(keys.items()):
                if board[kp[0]][kp[1]] == 'normal': continue
                p, ns = _dijkstra(board, rows, cols, (r, c), kp, locked, open_cells, trig)
                if p is None: continue
                commit(p, ns, kp); board[kp[0]][kp[1]] = 'normal'; held.add(_door_for_key(kc)); prog = True

    def open_doors():
        prog = False
        for dc in list(held):
            dp = doors.get(dc)
            if dp is None or dp not in locked: continue
            p, ns = _dijkstra(board, rows, cols, (r, c), dp, locked - {dp}, open_cells, trig)
            if p is None: continue
            commit(p, ns, dp); board[dp[0]][dp[1]] = 'normal'; locked.discard(dp); prog = True
        return prog

    for _ in range(20):
        sweep(); collect_keys(); op = open_doors(); collect_keys()
        if not op and not any(board[kp[0]][kp[1]] != 'normal' for kp in keys.values()):
            sweep()
            if not any(dp in locked for dp in doors.values()): break
    p, _ = _dijkstra(board, rows, cols, (r, c), treasure, set(), open_cells, trig)
    if p is not None: full.extend(p)
    return full


def _body(event):
    if isinstance(event, dict) and 'parameters' in event and isinstance(event['parameters'], list):
        prm = {}
        for p in event['parameters']:
            v = p.get('value', '')
            try: prm[p.get('name', '')] = json.loads(v) if isinstance(v, str) else v
            except Exception: prm[p.get('name', '')] = v
        return prm
    if isinstance(event, dict) and 'body' in event:
        b = event['body']
        try: return json.loads(b) if isinstance(b, str) else b
        except Exception: return {}
    return event if isinstance(event, dict) else {}


def lambda_handler(event, context):
    b = _body(event)
    gm = b.get('game_map') or b.get('map') or []
    if isinstance(gm, str):
        try: gm = json.loads(gm)
        except Exception: gm = []
    if not gm:
        return {'statusCode': 400, 'body': json.dumps({'error': 'no map'})}
    rows, cols = len(gm), len(gm[0])
    action = str(b.get('action', '') or '').lower().strip()
    tile = b.get('tile', '')

    if action in ('count', 'find') or (tile and not b.get('strategy')):
        positions = [(R, C) for R in range(rows) for C in range(cols) if gm[R][C] == tile]
        lines = ["Scanning the map:"] + [f"- Row {R}, Col {C}: {tile}" for (R, C) in positions] + [str(len(positions))]
        return {'statusCode': 200, 'body': json.dumps({'result': "\n".join(lines), 'count': len(positions)})}

    raw = b.get('start_pos') or b.get('playerStart') or b.get('start') or [0, 0]
    start = _parse_start(raw)
    if not (0 <= start[0] < rows and 0 <= start[1] < cols):
        start = (0, 0)
    path = _pathfind(gm, start)
    # PROBE: single-letter moves
    letters = [LETTER[m] for m in path]
    return {'statusCode': 200,
            'body': json.dumps({'path': letters, 'steps': len(letters),
                                'note': 'single-letter probe'})}
