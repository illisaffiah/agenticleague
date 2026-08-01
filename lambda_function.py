import json
from collections import deque

COLLECTIBLE_COINS = {"c7"}
CHALLENGE_TILES = {"c1", "c2", "c3", "c4", "c5", "c6", "c17"}
BLOCKED_TILES = {"wall", "c8"}
BLOCKED_TILES_NO_SPIKES = {"wall"}
DIRECTIONS = [(-1, 0, "up"), (1, 0, "down"), (0, -1, "left"), (0, 1, "right")]

# Point values for cost-benefit analysis
REWARD_VALUES = {
    "c7": 250, "c1": 400, "c2": 600, "c3": 550, "c4": 800,
    "c5": 250, "c6": 250, "c17": 50, "c40": 50, "c41": 50,
    "c30": 1000, "c31": 1000, "treasure": 1000
}
SPIKE_COST = 250  # Cost of losing 1 life

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
    import re
    try:
        if isinstance(pos, (list, tuple)):
            if len(pos) >= 2:
                a = re.sub(r'[^A-Za-z0-9]', '', str(pos[0]))
                b = re.sub(r'[^A-Za-z0-9]', '', str(pos[1]))
                if a.isalpha():
                    return (int(b) - 1, ord(a.upper()) - ord('A'))
                return (int(a), int(b))
        s = re.sub(r'[^A-Za-z0-9]', '', str(pos))
        m = re.match(r'([A-Za-z])(\d+)', s)
        if m:
            return (int(m.group(2)) - 1, ord(m.group(1).upper()) - ord('A'))
        nums = re.findall(r'\d+', s)
        if len(nums) >= 2:
            return (int(nums[0]), int(nums[1]))
    except (ValueError, TypeError, IndexError):
        pass
    return (0, 0)

def _bfs(game_map, rows, cols, start, goal, extra_blocked=None, allow_cells=None, allow_spikes=False):
    blocked = extra_blocked or set()
    allowed = allow_cells or set()
    block_set = BLOCKED_TILES_NO_SPIKES if allow_spikes else BLOCKED_TILES
    queue = deque([(start[0], start[1], [])])
    visited = {(start[0], start[1])}
    while queue:
        r, c, path = queue.popleft()
        if (r, c) == goal:
            return path
        for dr, dc, move in DIRECTIONS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in visited:
                cell = game_map[nr][nc]
                if (nr, nc) in allowed:
                    visited.add((nr, nc))
                    queue.append((nr, nc, path + [move]))
                elif cell not in block_set and (nr, nc) not in blocked:
                    visited.add((nr, nc))
                    queue.append((nr, nc, path + [move]))
    return None

def _get_reachable_rewards(game_map, rows, cols, start, extra_blocked=None, allow_spikes=False):
    """Find all reachable reward cells from a position."""
    blocked = extra_blocked or set()
    block_set = BLOCKED_TILES_NO_SPIKES if allow_spikes else BLOCKED_TILES
    queue = deque([(start[0], start[1])])
    visited = {(start[0], start[1])}
    rewards = []
    while queue:
        r, c = queue.popleft()
        cell = game_map[r][c]
        if cell in REWARD_VALUES and (r, c) != start:
            rewards.append((r, c, cell))
        for dr, dc, _ in DIRECTIONS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in visited:
                ncell = game_map[nr][nc]
                if ncell not in block_set and (nr, nc) not in blocked:
                    visited.add((nr, nc))
                    queue.append((nr, nc))
    return rewards

def _calculate_spike_value(game_map, rows, cols, spike_pos, current_pos, extra_blocked=None):
    """Calculate net value of walking through a spike.
    Returns the value of rewards ONLY accessible through this spike minus the spike cost."""
    blocked = extra_blocked or set()
    
    # Find rewards reachable WITHOUT the spike (current situation)
    rewards_without = set()
    for r, c, cell in _get_reachable_rewards(game_map, rows, cols, current_pos, extra_blocked=blocked, allow_spikes=False):
        rewards_without.add((r, c))
    
    # Find rewards reachable WITH the spike allowed
    allowed_spike = {spike_pos}
    rewards_with = set()
    # Temporarily allow this one spike
    for r, c, cell in _get_reachable_rewards(game_map, rows, cols, current_pos, extra_blocked=blocked, allow_spikes=False):
        rewards_with.add((r, c))
    # Also check from the spike position itself (what's beyond it)
    for r, c, cell in _get_reachable_rewards(game_map, rows, cols, spike_pos, extra_blocked=blocked, allow_spikes=False):
        rewards_with.add((r, c))
    
    # Rewards ONLY accessible through the spike
    new_rewards = rewards_with - rewards_without
    
    # Calculate total value of new rewards
    total_value = 0
    for r, c in new_rewards:
        cell = game_map[r][c]
        total_value += REWARD_VALUES.get(cell, 0)
    
    # Net value = rewards gained - cost of spike
    return total_value - SPIKE_COST

def _bfs_spike_strategic(game_map, rows, cols, start, goal, extra_blocked=None, allow_cells=None):
    """Try path avoiding spikes. If no path, check if spike is worth the cost."""
    # First try: avoid all spikes
    path = _bfs(game_map, rows, cols, start, goal, extra_blocked=extra_blocked, allow_cells=allow_cells, allow_spikes=False)
    if path is not None:
        return path
    
    # No spike-free path exists. Check if going through spike is worth it.
    # Find which spikes are between us and the goal
    # For simplicity: if the goal itself is valuable enough, allow spikes
    goal_cell = game_map[goal[0]][goal[1]]
    goal_value = REWARD_VALUES.get(goal_cell, 0)
    
    # Also estimate rewards beyond the goal
    beyond_value = 0
    for r, c, cell in _get_reachable_rewards(game_map, rows, cols, goal, extra_blocked=extra_blocked, allow_spikes=False):
        beyond_value += REWARD_VALUES.get(cell, 0)
    
    total_accessible_value = goal_value + beyond_value
    
    # Allow spike if the total value justifies it (rewards > spike cost)
    if total_accessible_value > SPIKE_COST:
        return _bfs(game_map, rows, cols, start, goal, extra_blocked=extra_blocked, allow_cells=allow_cells, allow_spikes=True)
    
    # Not worth it — skip this target
    return None

def _find_start_exit(game_map, rows, cols, start_pos):
    r, c = start_pos
    allow = set()
    has_free_exit = False
    for dr, dc, _ in DIRECTIONS:
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            cell = game_map[nr][nc]
            if cell not in BLOCKED_TILES:
                has_free_exit = True
                break
    if not has_free_exit:
        for dr, dc, _ in DIRECTIONS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                if game_map[nr][nc] == 'c8':
                    allow.add((nr, nc))
    return allow

def _pathfind(game_map, start_pos):
    rows = len(game_map)
    cols = len(game_map[0])
    board = [row[:] for row in game_map]
    r, c = start_pos
    full_path = []
    allowed_spikes = _find_start_exit(game_map, rows, cols, start_pos)
    treasure = None
    red_key_pos = None
    red_door_pos = None
    green_key_pos = None
    green_door_pos = None
    for row in range(rows):
        for col in range(cols):
            cell = board[row][col]
            if cell == 'treasure':
                treasure = (row, col)
            elif cell == 'c40':
                red_key_pos = (row, col)
            elif cell == 'c30':
                red_door_pos = (row, col)
            elif cell == 'c41':
                green_key_pos = (row, col)
            elif cell == 'c31':
                green_door_pos = (row, col)
    if not treasure:
        return []
    blocked_doors = set()
    if red_door_pos:
        blocked_doors.add(red_door_pos)
    if green_door_pos:
        blocked_doors.add(green_door_pos)

    def get_targets(board, blocked):
        targets = set()
        for row in range(rows):
            for col in range(cols):
                cell = board[row][col]
                if cell in COLLECTIBLE_COINS or cell in CHALLENGE_TILES:
                    if (row, col) not in blocked:
                        targets.add((row, col))
        return targets

    def sweep(board, cur_r, cur_c, blocked):
        path = []
        r, c = cur_r, cur_c
        for _ in range(80):
            targets = get_targets(board, blocked)
            best_dist = float('inf')
            best_path = None
            best_target = None
            for target in list(targets):
                if target == (r, c):
                    board[r][c] = 'normal'
                    continue
                # Use strategic spike decision
                tp = _bfs_spike_strategic(board, rows, cols, (r, c), target, extra_blocked=blocked, allow_cells=allowed_spikes)
                if tp and len(tp) < best_dist:
                    best_dist = len(tp)
                    best_path = tp
                    best_target = target
            if best_target:
                path.extend(best_path)
                r, c = best_target
                board[r][c] = 'normal'
            else:
                break
        return path, r, c

    # PHASE 1: Sweep accessible targets (both doors blocked)
    path_segment, r, c = sweep(board, r, c, blocked_doors)
    full_path.extend(path_segment)

    # PHASE 2: Get RED key (keys/doors are always worth the spike cost)
    if red_key_pos and red_door_pos:
        if board[red_key_pos[0]][red_key_pos[1]] != 'normal':
            # Keys are critical — always allow spikes for keys
            path_to_key = _bfs(board, rows, cols, (r, c), red_key_pos, extra_blocked=blocked_doors, allow_cells=allowed_spikes, allow_spikes=False)
            if not path_to_key:
                path_to_key = _bfs(board, rows, cols, (r, c), red_key_pos, extra_blocked=blocked_doors, allow_cells=allowed_spikes, allow_spikes=True)
            if path_to_key:
                full_path.extend(path_to_key)
                r, c = red_key_pos
                board[r][c] = 'normal'
        blocked_doors.discard(red_door_pos)

    # PHASE 3: Get GREEN key
    if green_key_pos and green_door_pos:
        if board[green_key_pos[0]][green_key_pos[1]] != 'normal':
            path_to_key = _bfs(board, rows, cols, (r, c), green_key_pos, extra_blocked=blocked_doors, allow_cells=allowed_spikes, allow_spikes=False)
            if not path_to_key:
                path_to_key = _bfs(board, rows, cols, (r, c), green_key_pos, extra_blocked=blocked_doors, allow_cells=allowed_spikes, allow_spikes=True)
            if path_to_key:
                full_path.extend(path_to_key)
                r, c = green_key_pos
                board[r][c] = 'normal'
        blocked_doors.discard(green_door_pos)

    # PHASE 4: Sweep ALL remaining targets (both doors now open)
    path_segment, r, c = sweep(board, r, c, blocked_doors)
    full_path.extend(path_segment)

    # PHASE 5: Go to treasure (always worth allowing spikes — treasure = 1000 pts)
    path_to_treasure = _bfs(board, rows, cols, (r, c), treasure, extra_blocked=blocked_doors, allow_cells=allowed_spikes, allow_spikes=False)
    if not path_to_treasure:
        path_to_treasure = _bfs(board, rows, cols, (r, c), treasure, extra_blocked=blocked_doors, allow_cells=allowed_spikes, allow_spikes=True)
    if path_to_treasure:
        full_path.extend(path_to_treasure)
        return full_path

    # Final fallback
    all_spikes = set()
    for row in range(rows):
        for col in range(cols):
            if game_map[row][col] == 'c8':
                all_spikes.add((row, col))
    direct = _bfs(game_map, rows, cols, start_pos, treasure, allow_cells=all_spikes, allow_spikes=True)
    return direct or []

def lambda_handler(event, context):
    print(f"RAW EVENT: {json.dumps(event)[:1000]}")
    params = _extract_params(event)
    game_map = (params.get('game_map') or params.get('map') or
               params.get('maze') or params.get('grid') or [])
    if isinstance(game_map, str):
        try:
            game_map = json.loads(game_map)
        except (json.JSONDecodeError, TypeError):
            game_map = []
    if game_map:
        max_cols = max(len(row) for row in game_map)
        game_map = [row + ['normal'] * (max_cols - len(row)) for row in game_map]
    action = params.get('action', 'count')
    tile = params.get('tile', '')
    if not game_map:
        return {"result": "0", "success": False, "error": "No map provided"}

    if action == 'count':
        count = 0
        for row in game_map:
            for cell in row:
                if cell == tile:
                    count += 1
        return {"result": str(count), "success": True}

    elif action == 'find':
        positions = []
        for r in range(len(game_map)):
            for c in range(len(game_map[r])):
                if game_map[r][c] == tile:
                    positions.append([r, c])
        return {"result": json.dumps(positions), "success": True, "count": len(positions)}

    elif action == 'pathfind':
        raw_start = (params.get('start_pos') or params.get('start') or
                    params.get('position') or params.get('playerStart') or [0, 0])
        if isinstance(raw_start, str):
            start_pos = _parse_start(raw_start)
        elif isinstance(raw_start, dict):
            start_pos = (raw_start.get('row', 0), raw_start.get('col', 0))
        else:
            start_pos = _parse_start(raw_start)
        rows, cols = len(game_map), len(game_map[0])
        if start_pos[0] >= rows or start_pos[1] >= cols:
            start_pos = (0, 0)

        path = _pathfind(game_map, start_pos)
        return {"result": json.dumps(path), "success": True, "steps": len(path)}

    else:
        return {"result": "0", "success": False, "error": f"Unknown action: {action}"}
