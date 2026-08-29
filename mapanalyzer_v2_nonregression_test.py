import json
from mapanalyzer_lambda import lambda_handler, _is_challenge, _is_key, _is_door, _door_for_key

MAP = [["normal","normal","c7","c7","c7","c5","c7","c7","c1","treasure"],
["normal","wall","wall","wall","wall","wall","wall","wall","wall","wall"],
["c2","normal","c7","c5","c7","normal","c7","c4","normal","c7"],
["wall","wall","wall","wall","wall","wall","wall","wall","wall","c7"],
["c7","c7","c7","c7","wall","c41","wall","normal","c7","c7"],
["c8","wall","wall","c30","wall","c7","wall","c5","wall","c1"],
["c1","c2","wall","c7","wall","c8","wall","normal","wall","normal"],
["c7","c7","wall","c1","wall","c4","wall","c7","wall","c5"],
["c7","c7","wall","c31","wall","normal","wall","c7","wall","c7"],
["c18","c7","wall","normal","c7","c3","normal","c7","wall","c40"]]

rows, cols = len(MAP), len(MAP[0])
def lbl(r,c): return f"{chr(ord('A')+c)}{r+1}"

# enumerate expected targets
coins = {(r,c) for r in range(rows) for c in range(cols) if MAP[r][c]=="c7"}
challenges = {(r,c) for r in range(rows) for c in range(cols) if _is_challenge(MAP[r][c])}
keys = {MAP[r][c]:(r,c) for r in range(rows) for c in range(cols) if _is_key(MAP[r][c])}
doors = {MAP[r][c]:(r,c) for r in range(rows) for c in range(cols) if _is_door(MAP[r][c])}
treasure = next((r,c) for r in range(rows) for c in range(cols) if MAP[r][c]=="treasure")

ev = {"parameters":[
    {"name":"action","value":"pathfind"},
    {"name":"game_map","value":json.dumps(MAP)},
    {"name":"start_pos","value":"A1"},
]}
res = lambda_handler(ev, None)
path = json.loads(res["result"])
print("steps:", res["steps"])

# replay
mv={"up":(-1,0),"down":(1,0),"left":(0,-1),"right":(0,1)}
r,c=0,0
visited={(0,0)}
spikes=0
collected_coins=set(); reached_challenges=set(); reached_keys=set(); opened_doors=set()
locked = set(doors.values())
key_before_door_ok = True
for m in path:
    dr,dc=mv[m]; r+=dr; c+=dc
    assert 0<=r<rows and 0<=c<cols, f"out of bounds at {lbl(r,c)}"
    assert MAP[r][c]!="wall", f"WALKED INTO WALL at {lbl(r,c)}"
    if (r,c) in locked:
        # door must be unlocked (its key collected) before stepping on
        dcode = MAP[r][c]
        kcode = "c4"+dcode[2:]
        if keys.get(kcode) not in reached_keys and keys.get(kcode) is not None:
            key_before_door_ok = False
        opened_doors.add((r,c)); locked.discard((r,c))
    visited.add((r,c))
    cell=MAP[r][c]
    if cell=="c8": spikes+=1  # raw crossings
    if (r,c) in coins: collected_coins.add((r,c))
    if (r,c) in challenges: reached_challenges.add((r,c))
    if (r,c) in keys.values(): reached_keys.add((r,c))

print("\n=== NON-REGRESSION CHECKS ===")
print(f"end position: {lbl(r,c)}  (treasure {lbl(*treasure)})  ->", "REACHED TREASURE" if (r,c)==treasure else "!! DID NOT REACH TREASURE")
print(f"coins:      {len(collected_coins)}/{len(coins)}", "OK" if collected_coins==coins else f"MISSING {[lbl(*x) for x in coins-collected_coins]}")
print(f"challenges: {len(reached_challenges)}/{len(challenges)}", "OK" if reached_challenges==challenges else f"MISSING {[lbl(*x) for x in challenges-reached_challenges]}")
print(f"keys:       {len(reached_keys)}/{len(keys)}", "OK" if len(reached_keys)==len(keys) else "MISSING")
print(f"doors:      {len(opened_doors)}/{len(doors)}", "OK" if len(opened_doors)==len(doors) else "MISSING")
print(f"key-before-door order:", "OK" if key_before_door_ok else "!! VIOLATED")
distinct_spikes=set()
r,c=0,0
for m in path:
    dr,dc=mv[m]; r+=dr; c+=dc
    if MAP[r][c]=="c8": distinct_spikes.add((r,c))
print(f"raw spike crossings: {spikes}")
print(f"DISTINCT spike tiles hit (= lives lost): {len(distinct_spikes)} {[lbl(*x) for x in distinct_spikes]}")
print("  winning run lost 2 lives (A6, F7). forced minimum = 2.",
      "OK NON-REGRESSION" if len(distinct_spikes)<=2 else "!! REGRESSION: more lives lost")
print(f"\nlives remaining would be: {3 if len(distinct_spikes)==2 else 'depends on max-lives'}")
print(f"lifeBonus preserved:", "YES (3 lives -> 750)" if len(distinct_spikes)==2 else "CHECK")
