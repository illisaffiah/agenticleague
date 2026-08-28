"""
Build fine-tuning datasets for the Qwen3 0.6B pathfinding SPECIALIST sub-agent,
matching the AWS AI League platform's EXACT training schema (agentcore_gateway_tools).

Per the reference example, each JSONL line is an object with:
  data_source : "agentcore_gateway_tools"
  prompt      : [ {role:system, content: <tool-call template>},
                  {role:user,   content: "Find a path from position {POS}, where ..."} ]
  ability     : "tool_use"
  reward_model: { ground_truth: <JSON string of {tool_call_id,type,function{name,arguments},output}>,
                  style: "rule" }
  extra_info  : { index, split, tool, map_size, strategy, position }
  tools       : [ <full pathfinding_lambda function schema> ]

KEY INSIGHT: The model only needs to emit the TOOL CALL (game_map, start_pos, strategy).
The Lambda produces the path; the reward's `output` field holds the Lambda response.
So we generate paths with a BFS/coins_first reference impl purely to fill `output`.

We build heavy coverage of OUR competition map + random solvable maps for generalization.
"""
import json
import random
from collections import deque

random.seed(7)

DIRECTIONS = [(-1, 0, "up"), (1, 0, "down"), (0, -1, "left"), (0, 1, "right")]
COINS = {"c7"}
CHALLENGES = {"c1", "c2", "c3", "c4", "c5", "c6", "c17"}
BLOCKED = {"wall", "c8"}
BLOCKED_NO_SPIKE = {"wall"}

OUR_MAP = [
    ["normal","normal","c7","c7","c7","c5","c7","c7","c1","treasure"],
    ["normal","wall","wall","wall","wall","wall","wall","wall","wall","wall"],
    ["c2","normal","c7","c5","c7","normal","c7","c4","normal","c7"],
    ["wall","wall","wall","wall","wall","wall","wall","wall","wall","c7"],
    ["c7","c7","c7","c7","wall","c41","wall","normal","c7","c7"],
    ["c8","wall","wall","c30","wall","c7","wall","c5","wall","c1"],
    ["c1","c2","wall","c7","wall","c8","wall","normal","wall","normal"],
    ["c7","c7","wall","c1","wall","c4","wall","c7","wall","c5"],
    ["c7","c7","wall","c31","wall","normal","wall","c7","wall","c7"],
    ["c18","c7","wall","normal","c7","c3","normal","c7","wall","c40"],
]

SYSTEM_CONTENT = (
    "Output ONLY a tool call to find a path on the map:\n\n"
    "<tool_call>\n"
    "{\"name\": \"pathfinding_lambda\", \"arguments\": {\"game_map\": <2d_array>, "
    "\"start_pos\": [row,col], \"strategy\": \"quickest|coins_first\"}}\n"
    "</tool_call>"
)

USER_PREAMBLE = (
    "Find a path from position <POS>, where the position is formatted as "
    "{column}{row}. {column} is a letter starting with A, and {row} is a "
    "number starting with 1. The map object's coordinates are formatted as "
    "[{rowIndex},{columnIndex}], where {rowIndex} is the row number starting "
    "with 0, and {columnIndex} is the column number starting with 0. The path "
    "should find the treasure on this map: <MAP>. Use strategy: <STRAT>."
)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "pathfinding_lambda",
        "description": (
            "AWS Lambda function for pathfinding with multiple strategies on a 2D "
            "game map. Supports two strategies: 'quickest' for shortest path using "
            "BFS, and 'coins_first' to collect all coins first, then other "
            "challenges, then treasure. The map contains various cell types including "
            "start, normal, wall, treasure, and challenge types (c1-c8) with "
            "different point values and damage."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "game_map": {
                    "type": "array",
                    "description": "2D array representing the game map where each cell can be 'start', 'normal', 'wall', 'treasure', or challenge types 'c1'-'c8'",
                    "items": {"type": "array", "items": {"type": "string"}},
                },
                "start_pos": {
                    "type": "array",
                    "description": "Starting position as [row, column] coordinates",
                    "items": {"type": "number"},
                },
                "strategy": {
                    "type": "string",
                    "description": "Pathfinding strategy to use. Available options: 'quickest' (shortest path using BFS) or 'coins_first' (collect all coins first, then other challenges, then treasure)",
                },
            },
            "required": ["game_map", "start_pos", "strategy"],
        },
    },
}]


def pos_to_display(r, c):
    return f"{chr(65 + c)}{r + 1}"


def display_to_pos(disp):
    col = ord(disp[0]) - 65
    row = int(disp[1:]) - 1
    return (row, col)


# ---------------- pathfinding reference (for the `output` field) ----------------
def bfs(gmap, start, goal, allow_spikes=False, extra_blocked=None):
    rows, cols = len(gmap), len(gmap[0])
    block = BLOCKED_NO_SPIKE if allow_spikes else BLOCKED
    extra = extra_blocked or set()
    q = deque([(start[0], start[1], [])])
    seen = {tuple(start)}
    while q:
        r, c, path = q.popleft()
        if (r, c) == tuple(goal):
            return path
        for dr, dc, mv in DIRECTIONS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in seen:
                if gmap[nr][nc] in block or (nr, nc) in extra:
                    continue
                seen.add((nr, nc))
                q.append((nr, nc, path + [mv]))
    return None


def bfs_spike_aware(gmap, start, goal, extra_blocked=None):
    p = bfs(gmap, start, goal, allow_spikes=False, extra_blocked=extra_blocked)
    if p is not None:
        return p
    return bfs(gmap, start, goal, allow_spikes=True, extra_blocked=extra_blocked)


def find_tile(gmap, name):
    for r, row in enumerate(gmap):
        for c, v in enumerate(row):
            if v == name:
                return (r, c)
    return None


def find_start(gmap):
    s = find_tile(gmap, "start")
    return s if s else (0, 0)


def quickest_path(gmap, start):
    tre = find_tile(gmap, "treasure")
    if tre is None:
        return []
    return bfs_spike_aware(gmap, start, tre) or []


def coins_first_path(gmap, start):
    rows, cols = len(gmap), len(gmap[0])
    board = [row[:] for row in gmap]
    r, c = start
    full = []
    tre = find_tile(board, "treasure")

    def targets(kinds):
        t = set()
        for rr in range(rows):
            for cc in range(cols):
                if board[rr][cc] in kinds:
                    t.add((rr, cc))
        return t

    def sweep(cr, cc, kinds):
        nonlocal full
        for _ in range(200):
            best = best_t = None
            for t in targets(kinds):
                if t == (cr, cc):
                    board[cr][cc] = "normal"
                    continue
                p = bfs_spike_aware(board, (cr, cc), t)
                if p is not None and (best is None or len(p) < len(best)):
                    best, best_t = p, t
            if best_t:
                full.extend(best)
                cr, cc = best_t
                board[cr][cc] = "normal"
            else:
                break
        return cr, cc

    # coins first, then other challenges, then treasure
    r, c = sweep(r, c, COINS)
    r, c = sweep(r, c, CHALLENGES)
    if tre:
        p = bfs_spike_aware(board, (r, c), tre)
        if p:
            full.extend(p)
    return full


def make_line(gmap, strategy, index, split):
    start = find_start(gmap)
    pos_disp = pos_to_display(*start)
    map_json = json.dumps(gmap)

    if strategy == "quickest":
        path = quickest_path(gmap, start)
    else:
        path = coins_first_path(gmap, start)

    # arguments is a JSON STRING (matching reference)
    args_str = json.dumps(
        {"game_map": gmap, "start_pos": list(start), "strategy": strategy}
    )
    output_body = json.dumps(
        {"path": path, "steps": len(path), "start_position": list(start)}
    )
    ground_truth_obj = {
        "tool_call_id": f"chatcmpl-tool-{index:024x}"[:36],
        "type": "function",
        "function": {"name": "pathfinding_lambda", "arguments": args_str},
        "output": {"statusCode": 200, "body": output_body},
    }

    user_content = (
        USER_PREAMBLE.replace("<POS>", pos_disp)
        .replace("<MAP>", map_json)
        .replace("<STRAT>", strategy)
    )

    return {
        "data_source": "agentcore_gateway_tools",
        "prompt": [
            {"role": "system", "content": SYSTEM_CONTENT},
            {"role": "user", "content": user_content},
        ],
        "ability": "tool_use",
        "reward_model": {
            "ground_truth": json.dumps(ground_truth_obj),
            "style": "rule",
        },
        "extra_info": {
            "index": index,
            "split": split,
            "tool": "pathfinding_lambda",
            "map_size": len(gmap),
            "strategy": strategy,
            "position": pos_disp,
        },
        "tools": TOOLS,
    }, path


def with_start(gmap, start):
    """Return a copy of gmap with a 'start' marker at `start` (preserving treasure)."""
    g = [row[:] for row in gmap]
    r, c = start
    if g[r][c] not in ("treasure",):
        g[r][c] = "start"
    return g


def random_map(rows=None, cols=None):
    if rows is None:
        rows = random.choice([6, 7, 8, 9, 10])
        cols = rows if random.random() < 0.7 else random.choice([6, 7, 8, 9, 10])
    while True:
        g = [["normal"] * cols for _ in range(rows)]
        for r in range(rows):
            for c in range(cols):
                x = random.random()
                if x < 0.2:
                    g[r][c] = "wall"
                elif x < 0.38:
                    g[r][c] = "c7"
                elif x < 0.46:
                    g[r][c] = random.choice(["c1", "c2", "c4", "c5", "c6", "c8"])
                else:
                    g[r][c] = "normal"
        sr, sc = random.randint(0, rows - 1), random.randint(0, cols - 1)
        tr, tc = rows - 1, cols - 1
        if (sr, sc) == (tr, tc):
            continue
        g[sr][sc] = "start"
        g[tr][tc] = "treasure"
        if bfs_spike_aware(g, (sr, sc), (tr, tc)):
            return g


def build():
    train, valid = [], []
    idx = 0

    # 1) OUR map, many start positions x both strategies (heavy anchoring).
    our_starts = [(0, 0), (0, 1), (2, 0), (2, 1), (4, 0), (0, 9), (9, 9)]
    for st in our_starts:
        g = with_start(OUR_MAP, st)
        for strat in ("quickest", "coins_first"):
            line, path = make_line(g, strat, idx, "train")
            idx += 1
            if path:
                (train if random.random() > 0.15 else valid).append(line)

    # Anchor canonical (0,0) coins_first + quickest hard.
    for _ in range(20):
        line, _ = make_line(with_start(OUR_MAP, (0, 0)), "coins_first", idx, "train")
        idx += 1
        train.append(line)
    for _ in range(10):
        line, _ = make_line(with_start(OUR_MAP, (0, 0)), "quickest", idx, "train")
        idx += 1
        train.append(line)

    # 2) Generalization: random solvable maps of varied sizes.
    made = 0
    while made < 140:
        g = random_map()
        strat = random.choice(["quickest", "coins_first"])
        line, path = make_line(g, strat, idx, "train")
        idx += 1
        if path:
            (train if random.random() > 0.12 else valid).append(line)
            made += 1

    random.shuffle(train)
    random.shuffle(valid)
    return train, valid


if __name__ == "__main__":
    train, valid = build()
    with open("train.jsonl", "w") as f:
        for ex in train:
            f.write(json.dumps(ex) + "\n")
    with open("validation.jsonl", "w") as f:
        for ex in valid:
            f.write(json.dumps(ex) + "\n")
    # combined single file (in case the fine-tune UI wants one file + internal split)
    with open("dataset.jsonl", "w") as f:
        for ex in train + valid:
            f.write(json.dumps(ex) + "\n")
    print(f"train examples:      {len(train)}")
    print(f"validation examples: {len(valid)}")
    print(f"combined examples:   {len(train) + len(valid)}")

    # Sanity: canonical example
    line, path = make_line(with_start(OUR_MAP, (0, 0)), "coins_first", 999, "train")
    print(f"\ncanonical coins_first path length: {len(path)}")
    print("top-level keys:", list(line.keys()))
    print("prompt roles:", [m["role"] for m in line["prompt"]])
    print("user preview:", line["prompt"][1]["content"][:90], "...")
    gt = json.loads(line["reward_model"]["ground_truth"])
    print("ground_truth keys:", list(gt.keys()))
    print("gt.function.name:", gt["function"]["name"])
