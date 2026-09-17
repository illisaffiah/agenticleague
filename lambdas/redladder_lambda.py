import json


def _extract_params(event):
    """Handle AgentCore Gateway tool invocation shapes + direct test payloads."""
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


def transform_code(code):
    """
    Red door transform.

    The red door hands over the key value (e.g. "shut") and asks the agent to
    return the code the door actually accepts. The accepted code is the key
    value read BACKWARDS:

        "shut" -> "tuhs"   (WINS the red door)

    This is a pure, derived string transform of whatever key value is supplied
    (no hardcoded answer): we reverse the characters of the received code.
    """
    if code is None:
        return ""
    code = str(code).strip()
    return code[::-1]


def lambda_handler(event, context):
    print(f"RAW EVENT: {json.dumps(event)[:1000]}")
    params = _extract_params(event)

    # The key value can arrive under several parameter names.
    code = (
        params.get('code')
        or params.get('key')
        or params.get('value')
        or params.get('text')
        or params.get('input')
        or ''
    )

    result = transform_code(code)

    return {
        "result": result,
        "success": True,
    }
