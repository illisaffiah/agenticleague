"""
Build SageMaker SFT datasets in the {"prompt":..., "completion":...} format
(matching the console's example dataset line).

Task: pathfinding specialist. Given a map + start + strategy in the prompt, the
model must OUTPUT the pathfinding_lambda tool call (that is the completion).
This guarantees a valid invocation for the flat customModelBonus.
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

# The prompt merges the system instruction and the user request into ONE string,
# exactly like the example (which folds the "Let's think step by step..." style
# instruction into the prompt field).
PROMPT_TMPL = (
    "Output ONLY a tool call to find a path on the map, in the form:\n"
    "<tool_call>{\"name\": \"pathfinding_lambda\", \"arguments\": "
    "{\"game_map\": <2d_array>, \"start_pos\": [row,col], "
    "\"strategy\": \"quickest|coins_first\"}}</tool_call>\n\n"
    "Find a path from position <POS>, where the position is formatted as "
    "{column}{row}. {column} is a letter starting with A, and {row} is a number "
    "starting with 1. The map object's coordinates are formatted as "
    "[{rowIndex},{columnIndex}], where {rowIndex} is the row number starting with "
    "0, and {columnIndex} is the column number starting with 0. The path should "
    "find the treasure on this map: <MAP>. Use strategy: <STRAT>."
)


def pos_to_display(r, c):
    return f"{chr(65 + c)}{r + 1}"


def bfs(gmap, start, goal, allow_spikes=False):
    rows, cols = len(gmap), len(gmap[0])
    block = BLOCKED_NO_SPIKE if allow_spikes else BLOCKED
    q = deque([(start[0], start[1], [])])
    seen = {tuple(start)}
    while q:
        r, c, path = q.popleft()
        if (r, c) == tuple(goal):
            return path
        for dr, dc, mv in DIRECTIONS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in seen:
                if gmap[nr][nc] in block:
                    continue
                seen.add((nr, nc))
                q.append((nr, nc, path + [mv]))
    return None


def bfs_sa(gmap, start, goal):
    p = bfs(gmap, start, goal, False)
    return p if p is not None else bfs(gmap, start, goal, True)


def find_tile(gmap, name):
    for r, row in enumerate(gmap):
        for c, v in enumerate(row):
            if v == name:
                return (r, c)
    return None


def find_start(gmap):
    return find_tile(gmap, "start") or (0, 0)


def quickest_path(gmap, start):
    tre = find_tile(gmap, "treasure")
    return (bfs_sa(gmap, start, tre) or []) if tre else []


def coins_first_path(gmap, start):
    rows, cols = len(gmap), len(gmap[0])
    board = [row[:] for row in gmap]
    r, c = start
    full = []
    tre = find_tile(board, "treasure")

    def targets(kinds):
        return {(rr, cc) for rr in range(rows) for cc in range(cols)
                if board[rr][cc] in kinds}

    def sweep(cr, cc, kinds):
        nonlocal full
        for _ in range(200):
            best = best_t = None
            for t in targets(kinds):
                if t == (cr, cc):
                    board[cr][cc] = "normal"
                    continue
                p = bfs_sa(board, (cr, cc), t)
                if p is not None and (best is None or len(p) < len(best)):
                    best, best_t = p, t
            if best_t:
                full.extend(best)
                cr, cc = best_t
                board[cr][cc] = "normal"
            else:
                break
        return cr, cc

    r, c = sweep(r, c, COINS)
    r, c = sweep(r, c, CHALLENGES)
    if tre:
        p = bfs_sa(board, (r, c), tre)
        if p:
            full.extend(p)
    return full


def make_pair(gmap, strategy):
    start = find_start(gmap)
    path = quickest_path(gmap, start) if strategy == "quickest" else coins_first_path(gmap, start)
    prompt = (PROMPT_TMPL
              .replace("<POS>", pos_to_display(*start))
              .replace("<MAP>", json.dumps(gmap))
              .replace("<STRAT>", strategy))
    tool_call = {"name": "pathfinding_lambda",
                 "arguments": {"game_map": gmap, "start_pos": list(start),
                               "strategy": strategy}}
    completion = f"<tool_call>{json.dumps(tool_call)}</tool_call>"
    return {"prompt": prompt, "completion": completion}, path


def with_start(gmap, start):
    g = [row[:] for row in gmap]
    r, c = start
    if g[r][c] != "treasure":
        g[r][c] = "start"
    return g


def random_map():
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
        if bfs_sa(g, (sr, sc), (tr, tc)):
            return g


def build():
    train, valid = [], []
    for st in [(0, 0), (0, 1), (2, 0), (2, 1), (4, 0), (0, 9), (9, 9)]:
        g = with_start(OUR_MAP, st)
        for strat in ("quickest", "coins_first"):
            ex, path = make_pair(g, strat)
            if path:
                (train if random.random() > 0.15 else valid).append(ex)
    for _ in range(20):
        train.append(make_pair(with_start(OUR_MAP, (0, 0)), "coins_first")[0])
    for _ in range(10):
        train.append(make_pair(with_start(OUR_MAP, (0, 0)), "quickest")[0])
    made = 0
    while made < 140:
        g = random_map()
        ex, path = make_pair(g, random.choice(["quickest", "coins_first"]))
        if path:
            (train if random.random() > 0.12 else valid).append(ex)
            made += 1
    random.shuffle(train)
    random.shuffle(valid)
    return train, valid


if __name__ == "__main__":
    train, valid = build()
    with open("train_sft.jsonl", "w") as f:
        for ex in train:
            f.write(json.dumps(ex) + "\n")
    with open("validation_sft.jsonl", "w") as f:
        for ex in valid:
            f.write(json.dumps(ex) + "\n")
    print(f"train: {len(train)}  validation: {len(valid)}")
    # sanity
    for line in [json.loads(l) for l in open("train_sft.jsonl")][:1]:
        assert set(line.keys()) == {"prompt", "completion"}
    print("keys OK: {'prompt','completion'} only")
    ex, path = make_pair(with_start(OUR_MAP, (0, 0)), "coins_first")
    print("\n--- sample prompt (first 160 chars) ---")
    print(ex["prompt"][:160])
    print("--- sample completion ---")
    print(ex["completion"][:120], "...")
    print(f"\ncanonical coins_first path len: {len(path)}")
