"""Authenticated Home Assistant gateway for the BS5c music library service."""
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.const import KEY_HASS_USER
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import ConfigEntryNotReady
from .client import BridgeClient, BridgeUnavailable
from .const import DOMAIN, API_VERSION, CALLBACK

async def async_setup(hass, config):
    hass.data.setdefault(DOMAIN, {})
    hass.http.register_view(AuthClientView())
    hass.http.register_view(BridgeView(hass))
    return True

async def async_setup_entry(hass, entry):
    client = BridgeClient(async_get_clientsession(hass), entry.data[CONF_HOST], entry.data[CONF_PORT])
    try:
        await client.request("mood", {"room": "lounge"})
    except BridgeUnavailable as error:
        raise ConfigEntryNotReady("BS5c library is unavailable") from error
    hass.data[DOMAIN][entry.entry_id] = client
    return True

async def async_unload_entry(hass, entry):
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True

class AuthClientView(HomeAssistantView):
    """Public static client metadata only; no state, tokens or local URLs."""
    url = "/api/home_media_bridge/auth-client"
    name = "api:home_media_bridge:auth_client"
    requires_auth = False

    async def get(self, request):
        return web.Response(text=f'<!doctype html><html><head><title>Home Media</title><link rel="redirect_uri" href="{CALLBACK}"></head><body>Home Media remote connection</body></html>',
            content_type="text/html", headers={"Cache-Control": "no-store"})

class BridgeView(HomeAssistantView):
    url = "/api/home_media_bridge"
    name = "api:home_media_bridge"
    requires_auth = True

    def __init__(self, hass):
        self.hass = hass

    async def get(self, request):
        return web.json_response({"api_version": API_VERSION, "configured": bool(self.hass.data.get(DOMAIN)),
            "service": "BS5c library", "operations": ["recommend", "mood", "mix_state", "mix", "suggestions", "context", "event", "action"]}, headers={"Cache-Control":"no-store"})

    async def post(self, request):
        user = request.get(KEY_HASS_USER)
        if user is None or not user.is_admin:
            return web.json_response({"error":"Home Media bridge commands require an HA administrator"}, status=403)
        if request.content_length is not None and request.content_length > 65536:
            return web.json_response({"error": "Request too large"}, status=413)
        raw = bytearray()
        async for chunk in request.content.iter_chunked(8192):
            raw.extend(chunk)
            if len(raw) > 65536:
                return web.json_response({"error": "Request too large"}, status=413)
        try:
            import json
            command = json.loads(raw)
            if not isinstance(command, dict) or set(command) - {"operation", "query", "payload"}:
                raise ValueError("Invalid bridge request")
            clients = list(self.hass.data.get(DOMAIN, {}).values())
            if not clients:
                return web.json_response({"error":"Bridge is not configured or is unavailable"}, status=503)
            result = await clients[0].request(command.get("operation"), command.get("query"), command.get("payload"))
            return web.json_response(result, headers={"Cache-Control":"no-store"})
        except (ValueError, TypeError):
            return web.json_response({"error":"Invalid or unsupported bridge command"}, status=400)
        except BridgeUnavailable:
            # Never automatically replay a mutation that may already have completed.
            return web.json_response({"error":"BS5c library unavailable; check its local service"}, status=502)
