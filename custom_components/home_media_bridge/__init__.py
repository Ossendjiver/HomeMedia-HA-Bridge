"""Authenticated Home Assistant gateway for the BS5c music library service."""
from aiohttp import web
import voluptuous as vol
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.const import KEY_HASS_USER
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import ConfigEntryNotReady
from .client import BridgeClient, BridgeUnavailable
from .const import DOMAIN, API_VERSION, CALLBACK
from .wiim_eq import WiiMEqReader, CONF_WIIM_HOST, DEFAULT_WIIM_HOST
from .routing_lease import RoutingLease, LeaseBusy, LeaseLost
from homeassistant.helpers.service import async_register_admin_service
import asyncio
import uuid

ROUTER_SCRIPTS = {'home_media_auto_1697842628021', 'home_media_auto_1780569042000', 'beosystem_route_link_audio', 'home_media_auto_1780662300002', 'beosystem_logic_handler', 'beosystem_sync_link_audio', 'beosystem_route_link_to_cuisine'}


async def async_setup(hass, config):
    hass.data.setdefault(DOMAIN, {})
    hass.http.register_view(AuthClientView())
    hass.http.register_view(BridgeView(hass))
    hass.http.register_view(WiiMEqView(hass))
    hass.http.register_view(RoutingLeaseView(hass))
    async def run_legacy(call):
        script = call.data.get("script")
        variables = call.data.get("variables", {})
        if script not in ROUTER_SCRIPTS or not isinstance(variables,dict) or len(variables)>16 or "routing_owner" in variables:
            raise ValueError("Unsupported legacy routing request")
        lease = lease_for(hass)
        if lease is None: raise LeaseBusy("Routing bridge is not configured")
        owner="ha-"+uuid.uuid4().hex
        async with lease.hold(owner):
            await asyncio.wait_for(hass.services.async_call("script",script+"_hm_worker",{**variables,"routing_owner":owner},blocking=True,context=call.context),timeout=150)
    async_register_admin_service(hass, DOMAIN, "run_legacy_router", run_legacy, schema=vol.Schema({vol.Required("script"):vol.In(ROUTER_SCRIPTS),vol.Optional("variables",default=dict):dict}))
    return True

async def async_setup_entry(hass, entry):
    client = BridgeClient(async_get_clientsession(hass), entry.data[CONF_HOST], entry.data[CONF_PORT],
        entry.options.get("coordinator_key", entry.data.get("coordinator_key", "")))
    # HA hardware routing must remain available while BS5c/MA are restarting.
    # Probe the backend on demand, not as a prerequisite for loading the HA lease.
    def legacy_busy():
        guard=hass.states.get("input_boolean.homemedia_routing_active")
        if guard is None or guard.state != "off": return True
        return any((state:=hass.states.get("script."+name+"_hm_worker")) is not None and state.state == "on" for name in ROUTER_SCRIPTS)
    client.routing_lease = RoutingLease(legacy_busy)
    client.wiim_eq = WiiMEqReader(async_get_clientsession(hass), entry.data.get(CONF_WIIM_HOST, DEFAULT_WIIM_HOST))
    hass.data[DOMAIN][entry.entry_id] = client
    await hass.config_entries.async_forward_entry_setups(entry, ["binary_sensor"])
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True

async def async_unload_entry(hass, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, ["binary_sensor"])
    if unloaded: hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded

async def async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

def lease_for(hass):
    clients=list(hass.data.get(DOMAIN,{}).values())
    return getattr(clients[0], "routing_lease", None) if clients else None

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
            "service": "BS5c library", "operations": ["recommend", "mood", "mix_state", "mix", "suggestions", "context", "event", "action", "playback_capabilities", "playback_state", "playback_intent", "playback_status"]}, headers={"Cache-Control":"no-store"})

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
        except BridgeUnavailable as error:
            # Never automatically replay a mutation that may already have completed.
            return web.json_response({"error":str(error), "code":error.code, "outcome":"unknown" if error.status >= 500 else "rejected"}, status=error.status)


class WiiMEqView(HomeAssistantView):
    """Authenticated fixed read route; cannot apply a profile or change playback."""
    url = "/api/home_media_bridge/wiim-eq"
    name = "api:home_media_bridge:wiim_eq"
    requires_auth = True

    def __init__(self, hass):
        self.hass = hass

    async def get(self, request):
        headers = {"Cache-Control": "no-store"}
        if request.query:
            return web.json_response({"error": "EQ status does not accept parameters"}, status=400, headers=headers)
        clients = list(self.hass.data.get(DOMAIN, {}).values())
        reader = getattr(clients[0], "wiim_eq", None) if clients else None
        if reader is None:
            return web.json_response({"available": False}, status=503, headers=headers)
        try:
            return web.json_response(await reader.status(), headers=headers)
        except BridgeUnavailable:
            return web.json_response({"available": False}, status=502, headers=headers)


class RoutingLeaseView(HomeAssistantView):
    url = "/api/home_media_bridge/routing-lease"
    name = "api:home_media_bridge:routing_lease"
    requires_auth = True
    def __init__(self,hass): self.hass=hass
    async def post(self,request):
        user=request.get(KEY_HASS_USER)
        if user is None or not user.is_admin: return web.json_response({"error":"Administrator required"},status=403)
        raw=await request.content.read(2049)
        if len(raw)>2048 or not request.content.at_eof(): return web.json_response({"error":"Request too large"},status=413)
        try:
            import json
            body=json.loads(raw)
            if not isinstance(body,dict) or set(body)!={"action","owner"} or body["action"] not in {"acquire","renew","release"}:
                raise ValueError("Invalid lease action")
            owner=body["owner"]
            if not isinstance(owner,str) or len(owner)>96: raise ValueError("Invalid owner")
            lease=lease_for(self.hass)
            if lease is None:return web.json_response({"error":"Lease unavailable"},status=503)
            # A concurrently started old app wins; the backend must stop actuating.
            if body["action"] != "release" and not self.hass.states.is_state("input_boolean.homemedia_routing_active","off"):
                raise LeaseBusy("Legacy routing operation active")
            if body["action"]=="release":
                await lease.release(owner);result=lease.state()
            elif body["action"]=="acquire":result=await lease.acquire(owner)
            else:result=await lease.renew(owner)
            return web.json_response(result,headers={"Cache-Control":"no-store"})
        except (ValueError,TypeError):return web.json_response({"error":"Invalid lease request"},status=400)
        except (LeaseBusy,LeaseLost):return web.json_response({"error":"Routing busy or ownership lost"},status=409)
