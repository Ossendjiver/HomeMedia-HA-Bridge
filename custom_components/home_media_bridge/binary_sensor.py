"""A HA-native lease sensor; independent of BS5c's availability."""
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.event import async_track_time_interval
from datetime import timedelta
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([RoutingLeaseSensor(hass.data[DOMAIN][entry.entry_id].routing_lease)])

class RoutingLeaseSensor(BinarySensorEntity):
    _attr_name = "Home Media routing active"
    _attr_unique_id = "home_media_bridge_routing_active"
    _attr_should_poll = False
    def __init__(self, lease):
        self.lease = lease
        self.entity_id = "binary_sensor.home_media_bridge_routing_active"
    @property
    def is_on(self): return self.lease.state()["active"]
    @property
    def extra_state_attributes(self): return self.lease.state()
    async def async_added_to_hass(self):
        self.lease.notify = self.async_write_ha_state
        async def tick(_):
            await self.lease.expire(); self.async_write_ha_state()
        self.async_on_remove(async_track_time_interval(self.hass,tick,timedelta(seconds=2)))
    async def async_will_remove_from_hass(self):
        self.lease.notify = lambda: None
