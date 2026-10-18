"""Read the active WiiM custom PEQ through the API used by pywiim/HA.

The generic player `eq` field describes graphic EQ, not this custom PEQ.
No playback/EQ writes, caller-selected hosts, credentials or redirects.
"""
import asyncio
import json
import time
from urllib.parse import quote
from aiohttp import ClientTimeout
from .client import BridgeUnavailable
from .policy import local_host

DEFAULT_WIIM_HOST = ""
CONF_WIIM_HOST = "wiim_host"
PEQ_READ_COMMAND = "EQGetLV2SourceBandEx:" + json.dumps({"source_name": "wifi", "pluginURI": "http://moddevices.com/plugins/caps/EqNp", "EQLevel": 2}, separators=(",", ":"))


def profile_status(raw):
    if not isinstance(raw, dict) or str(raw.get("status", "")).upper() != "OK":
        raise ValueError("WiiM PEQ status unavailable")
    state = str(raw.get("EQStat", "")).lower()
    if state not in {"on", "off"}:
        raise ValueError("WiiM PEQ enabled status unavailable")
    name = raw.get("Name", "")
    if not isinstance(name, str) or len(name) > 256:
        raise ValueError("Invalid WiiM PEQ name")
    return {"available": True, "enabled": state == "on", "profile": name.strip(),
            "source": str(raw.get("source_name", ""))[:64],
            "channel_mode": str(raw.get("channelMode", ""))[:32],
            "eq_level": 2, "observed_at_ms": int(time.time() * 1000)}


class WiiMEqReader:
    def __init__(self, session, host):
        self.session = session
        self.host = local_host(host)
        self._lock = asyncio.Lock()
        self._cached = None
        self._expires = 0.0

    async def status(self):
        async with self._lock:
            if self._cached is not None and time.monotonic() < self._expires:
                return dict(self._cached)
            # Self-signed TLS exception is confined to this configured LAN device.
            url = f"https://{self.host}/httpapi.asp?command={quote(PEQ_READ_COMMAND, safe='')}"
            try:
                async with self.session.get(url, ssl=False, allow_redirects=False,
                                            timeout=ClientTimeout(total=6)) as response:
                    if response.status != 200:
                        raise ValueError("WiiM status request failed")
                    body = bytearray()
                    async for chunk in response.content.iter_chunked(8192):
                        body.extend(chunk)
                        if len(body) > 65536:
                            raise ValueError("WiiM status response too large")
                    result = profile_status(json.loads(body))
                self._cached = result
                self._expires = time.monotonic() + 10
                return dict(result)
            except (Exception,) as error:
                self._cached = None
                self._expires = 0.0
                raise BridgeUnavailable("WiiM custom EQ unavailable") from error
