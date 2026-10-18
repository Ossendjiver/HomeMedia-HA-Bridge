"""Set up the bridge to a local BS5c device."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .client import BridgeClient, BridgeUnavailable
from .const import DOMAIN, DEFAULT_HOST, DEFAULT_PORT
from .policy import local_host
from .wiim_eq import CONF_WIIM_HOST, DEFAULT_WIIM_HOST

class HomeMediaBridgeFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HomeMediaOptionsFlow()


    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        errors = {}
        if user_input is not None:
            try:
                host = local_host(user_input[CONF_HOST])
                port = int(user_input[CONF_PORT])
                wiim_value = user_input.get(CONF_WIIM_HOST, DEFAULT_WIIM_HOST).strip()
                wiim_host = local_host(wiim_value) if wiim_value else ""
                if not 1 <= port <= 65535:
                    raise ValueError("Invalid port")
                client = BridgeClient(async_get_clientsession(self.hass), host, port)
                await client.request("mood", {"room":"lounge"})
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Home Media Bridge", data={CONF_HOST:host, CONF_PORT:port, CONF_WIIM_HOST:wiim_host})
            except ValueError:
                errors["base"] = "invalid_host"
            except BridgeUnavailable:
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
            vol.Optional(CONF_WIIM_HOST, default=DEFAULT_WIIM_HOST): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(vol.Coerce(int), vol.Range(min=1,max=65535)),
        }), errors=errors)


class HomeMediaOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors={}
        if user_input is not None:
            key=user_input.get("coordinator_key","").strip()
            if key and not 32 <= len(key) <= 256: errors["base"]="invalid_coordinator_key"
            else:
                updated=dict(self.config_entry.options)
                if key:updated["coordinator_key"]=key
                wiim_value=user_input.get(CONF_WIIM_HOST, self.config_entry.data.get(CONF_WIIM_HOST, "")).strip()
                try:updated[CONF_WIIM_HOST]=local_host(wiim_value) if wiim_value else ""
                except ValueError:
                    return self.async_abort(reason="invalid_host")
                return self.async_create_entry(title="",data=updated)
        from homeassistant.helpers import selector
        return self.async_show_form(step_id="init",data_schema=vol.Schema({
            vol.Optional(CONF_WIIM_HOST, default=self.config_entry.options.get(CONF_WIIM_HOST, self.config_entry.data.get(CONF_WIIM_HOST, ""))):str,
            vol.Optional("coordinator_key"):selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        }),errors=errors)
