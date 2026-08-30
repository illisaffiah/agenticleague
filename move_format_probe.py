"""
Probe: does the game's move parser accept ABBREVIATED moves (single letter or
run-length) instead of full words? If yes, we can slash the path array's ~365
tokens (the single biggest token sink) down to ~100, jumping tokenBonus.

This computes what the compact-format path arrays WOULD look like, so we can
decide what to test live. We do NOT know the parser accepts these — the live
probe (return one of these from the tool on a PRACTICE run) tells us:
  - if the avatar MOVES normally -> format accepted -> deploy it (big win)
  - if the avatar does NOT move -> format rejected -> revert, zero harm

We test on the known map's full-clear path.
"""
import sys, json
sys.path.insert(0, '.')
for m in list(sys.modules):
    if 'mapanalyzer' in m:
        del sys.modules[m]
import mapanalyzer_lambda as M

MAP = [['normal','normal','c7','c7','c7','c5','c7','c7','c1','treasure'],
['normal','wall','wall','wall','wall','wall','wall','wall','wall','wall'],
['c2','normal','c7','c5','c7','normal','c7','c4','normal','c7'],
['wall','wall','wall','wall','wall','wall','wall','wall','wall','c7'],
['c7','c7','c7','c7','wall','c41','wall','normal','c7','c7'],
['c8','wall','wall','c30','wall','c7','wall','c5','wall','c1'],
['c1','c2','wall','c7','wall','c8','wall','normal','wall','normal'],
['c7','c7','wall','c1','wall','c4','wall','c7','wall','c5'],
['c7','c7','wall','c31','wall','normal','wall','c7','wall','c7'],
['c18','c7','wall','normal','c7','c3','normal','c7','wall','c40']]

path = M._pathfind(MAP, (0, 0))

def toklen(s):
    return round(len(s) / 4)

# Format 1: current full-word WITH spaces (baseline)
f1 = json.dumps(path)  # json has no spaces by default; model adds them
f1_spaced = "[" + ", ".join(f'"{m}"' for m in path) + "]"
# Format 2: full-word compact (no spaces) - SAFE
f2 = json.dumps(path, separators=(",", ":"))
# Format 3: single letters u/d/l/r
letter = {"up":"u","down":"d","left":"l","right":"r"}
f3 = json.dumps([letter[m] for m in path], separators=(",", ":"))
# Format 4: bare letter string "rrllud..."
f4 = "".join(letter[m] for m in path)
# Format 5: run-length "8r8l2d..."
rle = []
i = 0
while i < len(path):
    j = i
    while j < len(path) and path[j] == path[i]:
        j += 1
    n = j - i
    rle.append((str(n) if n > 1 else "") + letter[path[i]])
    i = j
f5 = "".join(rle)

print(f"path moves: {len(path)}")
print(f"{'format':32} {'chars':>6} {'~tokens':>8}  SAFE?")
print("-"*60)
print(f"{'1 full-word +spaces (current)':32} {len(f1_spaced):>6} {toklen(f1_spaced):>8}  baseline")
print(f"{'2 full-word compact (no space)':32} {len(f2):>6} {toklen(f2):>8}  YES (valid words)")
print(f"{'3 single-letter JSON [u,d,l]':32} {len(f3):>6} {toklen(f3):>8}  needs live test")
print(f"{'4 bare letter string rrll':32} {len(f4):>6} {toklen(f4):>8}  needs live test")
print(f"{'5 run-length 8r8l2d':32} {len(f5):>6} {toklen(f5):>8}  needs live test")
print()
print("Format 2 (compact) sample:", f2[:50], "...")
print("Format 4 (letters)  sample:", f4[:30], "...")
print("Format 5 (RLE)      sample:", f5[:30], "...")
print()
print("SAFE WIN NOW: format 2 saves ~", toklen(f1_spaced)-toklen(f2), "tokens (no risk)")
print("BIG WIN IF ACCEPTED: format 4/5 saves ~", toklen(f1_spaced)-toklen(f4), "tokens (needs probe)")
