import hashlib, hmac, json, time
from urllib.parse import parse_qsl

def verify_init_data(init_data: str, bot_token: str) -> dict | None:
    if not init_data or not bot_token:
        return None
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None
    received_hash = pairs.pop('hash', None)
    if not received_hash:
        return None
    check_string = '\n'.join(f'{key}={pairs[key]}' for key in sorted(pairs))
    secret = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None
    try:
        auth_date = int(pairs.get('auth_date', '0'))
    except ValueError:
        return None
    if auth_date and time.time() - auth_date > 24 * 60 * 60:
        return None
    try:
        pairs['user'] = json.loads(pairs.get('user', '{}'))
    except json.JSONDecodeError:
        pairs['user'] = {}
    return pairs
