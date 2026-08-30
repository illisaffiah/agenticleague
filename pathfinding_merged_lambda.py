import json
import re
import heapq
from collections import deque

# =====================================================================
# MERGED "Pathfinding" Lambda (organizer default tool, edited in place).
# Replaces the weak swift/get_coins BFS with the full mapanalyzer engine:
#   - spike ONE-TIME-TOLL weighted pathfinding (state-augmented Dijkstra)
#   - key/door gating (collect key before its door)
#   - guaranteed treasure fallback + wall-safe move validation
#   - find / count actions (for the c3 "how many <tile>" challenge)
# Keeps Pathfinding's I/O contract:
#   input:  body/event with game_map (+ strategy | action | tile | start_pos)
#   output: {'statusCode':200, 'body': json.dumps({...})}
# so the organizer tool schema stays valid and mapanalyzer can be removed.
# =====================================================================

COIN_TILES = {"c7"}
SPIKE_TILES = {"c8"}
NONWALK_BASE = {"wall"}
DIRECTIONS = [(-1, 0, "up"), (1, 0, "down"), (0, -1, "left"), (0, 1, "right")]
SPIKE_COST = 100000


def _is_key(cell):
    return bool(re.fullmatch(r"c4\d", cell or ""))

def _is_door(cell):
    return bool(re.fullmatch(r"c3\d", cell or ""))

def _door_for_key(cell):
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
    return bool(re.fullmatch(r"c\d+", cell))


def _parse_start(pos):
    try:
        if isinstance(pos, (list, tuple)):
            if len(pos) == 1:
                return _parse_start(pos[0])
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
        rc = re.search(r'row\s*(\d+).*?col\s*(\d+)', s, re.IGNORECASE)
        if rc:
            return (int(rc.group(1)), int(rc.group(2)))
        if len(nums) == 1:
            return (int(nums[0]), 0)
    except (ValueError, TypeError, IndexError):
        pass
    return (0, 0)


def _dijkstra(game_map, rows, cols, start, goal, blocked, open_cells,
              already_triggered=None):
    if already_triggered is None:
        already_triggered = frozenset()
    else:
        already_triggered = frozenset(already_triggered)
    dist = {(start[0], start[1], already_triggered): 0}
    pq = [(0, start[0], start[1], already_triggered, [])]
    while pq:
        cost, r, c, triggered, path = heapq.heappop(pq)
        if (r, c) == goal:
            return path, set(triggered) - set(already_triggered)
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
                if _is_door(cell):
                    continue
            ntrig = triggered
            if cell in SPIKE_TILES and (nr, nc) not in triggered:
                step = SPIKE_COST
                ntrig = triggered | frozenset({(nr, nc)})
            else:
                step = 1
            ncost = cost + step
            nstate = (nr, nc, ntrig)
            if ncost < dist.get(nstate, float('inf')):
                dist[nstate] = ncost
                heapq.heappush(pq, (ncost, nr, nc, ntrig, path + [move]))
    return None, None


def _find_start_exit(game_map, rows, cols, start_pos):
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

    treasure = None
    keys = {}
    doors = {}
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
    keys_held = set()
    key_pos_by_code = dict(keys)
    door_pos_by_code = dict(doors)
    triggered_spikes = set()

    def value_of(cell):
        if cell in COIN_TILES:
            return 250
        if _is_challenge(cell):
            return 400
        return 0

    def commit(path, new_spikes, dest):
        nonlocal r, c
        full_path.extend(path)
        r, c = dest
        triggered_spikes.update(new_spikes)

    def sweep():
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
                    if new_spikes and value_of(cell) < len(new_spikes) * life_value:
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
        progressed = True
        while progressed:
            progressed = False
            for kcode, kpos in list(key_pos_by_code.items()):
                if board[kpos[0]][kpos[1]] == 'normal':
                    continue
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

    for _ in range(20):
        sweep()
        collect_keys()
        opened = open_doors()
        collect_keys()
        if not opened and not any(board[kp[0]][kp[1]] != 'normal' for kp in key_pos_by_code.values()):
            sweep()
            if not any(dp in locked_doors for dp in door_pos_by_code.values()):
                break

    path, _new = _dijkstra(board, rows, cols, (r, c), treasure,
                           blocked=set(), open_cells=open_cells,
                           already_triggered=triggered_spikes)
    if path is not None:
        full_path.extend(path)
        return full_path
    path, _ = _dijkstra(board, rows, cols, start_pos, treasure,
                        blocked=set(), open_cells=open_cells)
    return path or full_path


def _replay_end(game_map, rows, cols, start, path):
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
    treasure = None
    for r in range(rows):
        for c in range(cols):
            if game_map[r][c] == 'treasure':
                treasure = (r, c)
                break
        if treasure:
            break
    if treasure is None:
        return path
    end = _replay_end(game_map, rows, cols, start, path)
    if end == treasure:
        return path
    all_doors = {(r, c) for r in range(rows) for c in range(cols) if _is_door(game_map[r][c])}
    tail, _ = _dijkstra(game_map, rows, cols, end, treasure,
                        blocked=set(), open_cells=all_doors)
    if tail:
        return list(path) + tail
    direct, _ = _dijkstra(game_map, rows, cols, start, treasure,
                         blocked=set(), open_cells=all_doors)
    return direct if direct is not None else path


def _normalize_map(game_map):
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


def _extract_body(event):
    """Accept AgentCore Gateway shapes AND the organizer's body/direct shape."""
    if isinstance(event, dict) and 'parameters' in event and isinstance(event['parameters'], list):
        params = {}
        for p in event['parameters']:
            name = p.get('name', '')
            value = p.get('value', '')
            try:
                params[name] = json.loads(value) if isinstance(value, str) else value
            except (json.JSONDecodeError, TypeError):
                params[name] = value
        return params
    if isinstance(event, dict) and 'body' in event:
        body = event['body']
        try:
            return json.loads(body) if isinstance(body, str) else body
        except (json.JSONDecodeError, TypeError):
            return {}
    return event if isinstance(event, dict) else {}


def lambda_handler(event, context):
    """
    Pathfinding tool (merged with mapanalyzer engine).

    Path mode (default): returns {'path':[...], 'steps':N, 'start_position':[r,c]}
      - spike one-time-toll optimal, key/door aware, treasure guaranteed.
    Analysis mode (action=find|count, tile=cX): returns {'result':..., 'count':N}
      - used by the c3 "How many <tile> on the map" challenge.
    """
    try:
        body = _extract_body(event)

        game_map = (body.get('game_map') or body.get('map') or
                    body.get('maze') or body.get('grid') or [])
        if isinstance(game_map, str):
            try:
                game_map = json.loads(game_map)
            except (json.JSONDecodeError, TypeError):
                game_map = []
        game_map = _normalize_map(game_map)
        if not game_map:
            return {'statusCode': 400, 'body': json.dumps({'error': 'Missing game_map'})}

        rows, cols = len(game_map), len(game_map[0])
        action = str(body.get('action', '') or '').lower().strip()
        tile = body.get('tile', '')

        # --- Analysis mode (c3): count / find a tile ---
        # Return the FULLY-FORMATTED "Scanning the map" answer so the model just
        # echoes it verbatim (no formatting step -> no bare-number failure).
        if action in ('count', 'find') or (tile and not body.get('strategy')):
            positions = [(r, c) for r in range(rows) for c in range(cols)
                         if game_map[r][c] == tile]
            lines = ["Scanning the map:"]
            for (r, c) in positions:
                lines.append(f"- Row {r}, Col {c}: {tile}")
            lines.append(str(len(positions)))
            formatted = "\n".join(lines)
            return {'statusCode': 200,
                    'body': json.dumps({'result': formatted,
                                        'answer': formatted,
                                        'count': len(positions),
                                        'positions': [[r, c] for (r, c) in positions]})}

        # --- Path mode (default) ---
        map_config = body.get('map_config', {})
        player_start = map_config.get('playerStart') or body.get('playerStart') or {}
        if isinstance(player_start, str):
            start_pos = _parse_start(player_start)
        elif isinstance(player_start, dict) and player_start:
            start_pos = (player_start.get('row', 0), player_start.get('col', 0))
        else:
            raw = (body.get('start_pos') or body.get('start') or
                   body.get('position') or [0, 0])
            start_pos = _parse_start(raw)
        if not (0 <= start_pos[0] < rows and 0 <= start_pos[1] < cols):
            start_pos = (0, 0)

        try:
            path = _pathfind(game_map, start_pos)
        except Exception as e:
            print(f"PATHFIND ERROR (falling back): {type(e).__name__}: {e}")
            path = []

        path = _ensure_treasure(game_map, rows, cols, start_pos, path)

        # wall-safe validation
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

        result = {'path': validated, 'steps': len(validated),
                  'start_position': list(start_pos)}
        return {'statusCode': 200, 'body': json.dumps(result)}

    except Exception as e:
        print(f"ERROR: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}
