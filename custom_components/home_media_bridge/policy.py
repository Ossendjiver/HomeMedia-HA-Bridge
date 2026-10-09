"""Closed command boundary; callers cannot choose a backend URL or HTTP method."""
import ipaddress
import json
import math
import re

ROUTES = {
    "recommend": ("GET", "/library/recommend/music"),
    "mood": ("GET", "/library/mood"),
    "mix_state": ("GET", "/library/mix"),
    "suggestions": ("GET", "/library/suggestions"),
    "context": ("GET", "/library/context"),
    "mix": ("POST", "/library/mix"),
    "event": ("POST", "/library/event"),
    "action": ("POST", "/library/action"),
}
QUERY_KEYS = {
    "recommend": {"room", "limit", "angle", "radius"},
    "mood": {"room"}, "mix_state": {"queue_id", "feedback"},
    "suggestions": {"room"}, "context": {"room"},
}
BODY_KEYS = {
    "mix": {"action", "queue_id", "room", "mode", "seed", "angle", "radius", "session_id", "current_item_id", "vote"},
    "event": {"type", "media_type", "title", "artist", "album", "uri", "duration", "room", "reason", "prompt_id", "kind", "action", "angle", "radius", "items", "listening_mood", "event_id", "timestamp_ms", "seconds"},
    "action": {"kind", "action", "prompt_id", "room"},
}

def local_host(raw):
    host = str(raw).strip().lower()
    try:
        ip = ipaddress.ip_address(host)
        if not (ip.is_private and not ip.is_unspecified and not ip.is_multicast):
            raise ValueError("Use the BS5c device's local address")
    except ValueError:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.local", host):
            raise ValueError("Use a private IP address or .local hostname") from None
    return host

def validate(operation, query=None, payload=None):
    if operation not in ROUTES:
        raise ValueError("Unsupported bridge operation")
    query, payload = query or {}, payload or {}
    if not isinstance(query, dict) or not isinstance(payload, dict):
        raise ValueError("Query and payload must be objects")
    if len(json.dumps({"query": query, "payload": payload}, allow_nan=False).encode()) > 65536:
        raise ValueError("Request too large")
    method, path = ROUTES[operation]
    allowed = QUERY_KEYS.get(operation, set())
    if set(query) - allowed or set(payload) - BODY_KEYS.get(operation, set()):
        raise ValueError("Unsupported command fields")
    if (method == "GET" and payload) or (method == "POST" and query):
        raise ValueError("Invalid request shape")
    for key, value in query.items():
        if isinstance(value, (dict, list, bool)) or value is None or len(str(value)) > 512:
            raise ValueError("Invalid query value")
    values = payload if method == "POST" else query
    for key in ("room", "queue_id", "prompt_id", "uri", "title", "artist", "album", "reason", "kind", "type", "media_type", "action", "mode", "event_id"):
        if key in values and (not isinstance(values[key], str) or len(values[key]) > 4096):
            raise ValueError("Invalid text field")
    for key, lo, hi in (("angle", 0, 360), ("radius", 0, 1), ("limit", 1, 50), ("duration", 0, 86400), ("seconds", 0, 86400), ("timestamp_ms", 1, 1e15)):
        if key in values:
            try:
                number = float(values[key])
                if isinstance(values[key], bool) or not math.isfinite(number) or not lo <= number <= hi:
                    raise ValueError()
            except (TypeError, ValueError):
                raise ValueError("Invalid " + key) from None
    if operation == "event" and payload.get("type") == "listen_feedback":
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", payload.get("event_id", "")) or payload.get("reason") != "skip":
            raise ValueError("Invalid listening feedback")
        if not {"timestamp_ms", "seconds", "title", "uri"} <= set(payload):
            raise ValueError("Missing listening feedback")
    if operation == "mix_state" and query.get("feedback", "0") not in ("0", "1"):
        raise ValueError("Invalid feedback query")
    if operation == "mix":
        if payload.get("action") not in {"begin", "update", "stop", "feedback"} or not payload.get("queue_id"):
            raise ValueError("A valid mix action and queue are required")
        if payload["action"] == "feedback":
            if type(payload.get("vote")) is not int or payload["vote"] not in (-1, 0, 1):
                raise ValueError("Invalid session vote")
            for key in ("session_id", "current_item_id"):
                if not isinstance(payload.get(key), str) or not 1 <= len(payload[key]) <= 512:
                    raise ValueError("A session and current song are required")
        if payload["action"] == "update" and not {"angle", "radius"} <= set(payload):
            raise ValueError("Mood coordinates are required")
        if payload.get("mode", "mood") not in {"mood", "radio"}:
            raise ValueError("Invalid mix mode")
        if "seed" in payload and not isinstance(payload["seed"], dict):
            raise ValueError("Seed must be an object")
    return method, path, query, payload
