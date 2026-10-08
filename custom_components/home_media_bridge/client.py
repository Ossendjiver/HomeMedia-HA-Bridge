"""Private, bounded BS5c library connection. HA credentials never go to BS5c."""
import asyncio
import aiohttp
from .policy import local_host, validate

class BridgeUnavailable(Exception):
    """The local service cannot answer this request."""

class BridgeClient:
    def __init__(self, session, host, port):
        self.session = session
        host = local_host(host)
        self.base = f"http://{'['+host+']' if ':' in host else host}:{int(port)}"

    async def request(self, operation, query=None, payload=None):
        method, path, query, payload = validate(operation, query, payload)
        try:
            async with self.session.request(method, self.base + path, params=query,
                json=payload if method == "POST" else None, allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=35, connect=5)) as response:
                if not 200 <= response.status < 300:
                    raise BridgeUnavailable("BS5c library did not accept the request")
                data = bytearray()
                async for chunk in response.content.iter_chunked(16384):
                    data.extend(chunk)
                    if len(data) > 1048576:
                        raise BridgeUnavailable("BS5c response exceeded the bridge limit")
                import json
                result = json.loads(data)
                if not isinstance(result, dict):
                    raise BridgeUnavailable("Invalid BS5c response")
                return result
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as error:
            raise BridgeUnavailable("BS5c library unavailable or invalid response") from error
