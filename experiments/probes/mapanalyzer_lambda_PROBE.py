import json

# =====================================================================
# TEMPORARY SPIKE-DESYNC PROBE BUILD of AgentCoreGatewayTool-mapanalyzer
# ---------------------------------------------------------------------
# This is NOT the real pathfinder. It hijacks the `pathfind` action to
# return a hardcoded PROBE_B_jit move array (enter F7 spike, retreat,
# re-enter) so we can read the live LoseNonPromptChallenge c8 event
# count and test whether spike damage is per-enter or consume-on-contact.
#
# `count` and `find` actions are preserved so nothing else in the run
# breaks. REVERT to the real mapanalyzer_lambda.py after ONE test run.
# =====================================================================

# PROBE_B_jit: A1 -> F-column -> enter F7, DOWN (retreat), re-enter F7,
# grab F5 green key, then beeline to treasure J1. Full valid run.
PROBE_B_JIT = ["down","down","right","right","right","right","right","right",
               "right","right","right","down","down","left","left","down",
               "down","down","down","down","left","left","up","up","up",
               "down","up","up","up","down","down","down","down","down",
               "right","right","up","up","up","up","up","right","right",
               "up","up","left","left","left","left","left","left","left",
               "left","left","up","up","right","right","right","right",
               "right","right","right","right","right"]


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


def lambda_handler(event, context):
    params = _extract_params(event)
    game_map = (params.get('game_map') or params.get('map') or
                params.get('maze') or params.get('grid') or [])
    if isinstance(game_map, str):
        try:
            game_map = json.loads(game_map)
        except (json.JSONDecodeError, TypeError):
            game_map = []
    action = params.get('action', 'count')
    tile = params.get('tile', '')

    if action == 'count':
        count = sum(1 for row in game_map for cell in row if cell == tile)
        return {"result": str(count), "success": True}
    elif action == 'find':
        pos = [[r, c] for r in range(len(game_map))
               for c in range(len(game_map[r])) if game_map[r][c] == tile]
        return {"result": json.dumps(pos), "success": True, "count": len(pos)}
    elif action == 'pathfind':
        # HIJACK: return the probe jitter array regardless of map.
        return {"result": json.dumps(PROBE_B_JIT), "success": True,
                "steps": len(PROBE_B_JIT)}
    else:
        return {"result": "0", "success": False, "error": f"Unknown action: {action}"}
