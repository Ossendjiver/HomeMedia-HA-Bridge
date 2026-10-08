"""Set up the bridge to a local BS5c device."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .client import BridgeClient, BridgeUnavailable
from .const import DOMAIN, DEFAULT_HOST, DEFAULT_PORT
from .policy import local_host

class HomeMediaBridgeFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        errors = {}
        if user_input is not None:
            try:
                host = local_host(user_input[CONF_HOST])
                port = int(user_input[CONF_PORT])
                if not 1 <= port <= 65535:
                    raise ValueError("Invalid port")
                client = BridgeClient(async_get_clientsession(self.hass), host, port)
                await client.request("mood", {"room":"lounge"})
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Home Media Bridge", data={CONF_HOST:host, CONF_PORT:port})
            except ValueError:
                errors["base"] = "invalid_host"
            except BridgeUnavailable:
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(vol.Coerce(int), vol.Range(min=1,max=65535)),
        }), errors=errors)
