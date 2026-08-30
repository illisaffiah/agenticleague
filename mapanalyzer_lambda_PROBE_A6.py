import json

# =====================================================================
# TEMPORARY A6 SPIKE-DESYNC PROBE build of AgentCoreGatewayTool-mapanalyzer
# ---------------------------------------------------------------------
# Confirms the consume-on-contact spike mechanic on the A6 spike (the
# F7 probe already showed 1 c8 event for 3 physical contacts). Hijacks
# `pathfind` to return a hardcoded jitter over A6=(5,0):
#   route to A5 -> enter A6 -> retreat A5 -> re-enter A6 -> A7 -> treasure.
# REVERT to the real mapanalyzer_lambda.py after ONE test run.
# =====================================================================

PROBE_A6 = ["down","down","right","right","right","right","right","right",
            "right","right","right","down","down","left","left","down",
            "down","down","down","down","left","left","left","left","up",
            "up","up","up","up","left","left","left","down","up","down",
            "down","up","up","right","right","right","down","down","down",
            "down","down","right","right","right","right","up","up","up",
            "up","up","right","right","up","up","left","left","left","left",
            "left","left","left","left","left","up","up","right","right",
            "right","right","right","right","right","right","right"]


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
        return {"result": json.dumps(PROBE_A6), "success": True,
                "steps": len(PROBE_A6)}
    else:
        return {"result": "0", "success": False, "error": f"Unknown action: {action}"}
