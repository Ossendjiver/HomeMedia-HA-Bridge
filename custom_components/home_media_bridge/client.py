"""Private, bounded BS5c library connection. HA credentials never go to BS5c."""
import asyncio
import aiohttp
import logging
_LOGGER = logging.getLogger(__name__)
from .policy import local_host, validate

class BridgeUnavailable(Exception):
    """The local service cannot answer this request."""
    def __init__(self, message, code="backend_unavailable", status=502):
        super().__init__(message)
        self.code, self.status = code, status

class BridgeClient:
    def __init__(self, session, host, port, coordinator_key=""):
        self.session = session
        self.coordinator_key = coordinator_key
        host = local_host(host)
        self.base = f"http://{'['+host+']' if ':' in host else host}:{int(port)}"

    async def request(self, operation, query=None, payload=None):
        method, path, query, payload = validate(operation, query, payload)
        if operation.startswith("playback_") and operation != "playback_capabilities" and len(self.coordinator_key)<32:
            raise BridgeUnavailable("Configure the dedicated BS5c coordinator key first")
        headers = {"X-HomeMedia-Key": self.coordinator_key} if operation.startswith("playback_") and self.coordinator_key else {}
        try:
            async with self.session.request(method, self.base + path, params=query, headers=headers,
                json=payload if method == "POST" else None, allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=35, connect=5)) as response:
                if operation == "playback_capabilities" and response.status == 404:
                    return {"api_version":1,"enabled":False}
                if not 200 <= response.status < 300:
                    _LOGGER.warning("BS5c operation %s returned HTTP %s", operation, response.status)
                    if response.status in (400, 404, 409, 422) and operation == "mix":
                        raise BridgeUnavailable("Mood session could not be updated; reopen the wheel or start a Mood Mix", "mix_rejected", 409)
                    raise BridgeUnavailable("BS5c library did not accept the request", "backend_rejected")
                data = bytearray()
                async for chunk in response.content.iter_chunked(16384):
                    data.extend(chunk)
                    if len(data) > 1048576:
                        raise BridgeUnavailable("BS5c response exceeded the bridge limit")
                import json
                result = json.loads(data)
                if not isinstance(result, dict):
                    raise BridgeUnavailable("Invalid BS5c response")
                if operation == "playback_capabilities" and result.get("enabled") and len(self.coordinator_key)<32:
                    result["setup_error"]=True
                return result
        except asyncio.TimeoutError as error:
            _LOGGER.warning("BS5c operation %s timed out", operation)
            raise BridgeUnavailable("BS5c request timed out; completion is unknown and it has not been retried", "backend_timeout", 504) from error
        except (aiohttp.ClientError, ValueError) as error:
            raise BridgeUnavailable("BS5c library unavailable or invalid response") from error
