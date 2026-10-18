import tempfile
import unittest
import voluptuous as vol
from types import SimpleNamespace
from homeassistant.core import HomeAssistant
from custom_components.home_media_bridge import async_setup,ROUTER_SCRIPTS
from custom_components.home_media_bridge.routing_lease import RoutingLease

class RouterServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_calls_worker_not_wrapper_and_releases_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            hass=HomeAssistant(directory);hass.http=SimpleNamespace(register_view=lambda view:None)
            await async_setup(hass,{})
            lease=RoutingLease(lambda:False)
            hass.data['home_media_bridge']['test']=SimpleNamespace(routing_lease=lease)
            seen=[]
            name='beosystem_sync_link_audio'
            async def script(call):
                seen.append(call.data)
                self.assertEqual(lease.state()['owner'],call.data['routing_owner'])
            hass.services.async_register('script',name+'_hm_worker',script)
            await hass.services.async_call('home_media_bridge','run_legacy_router',{'script':name,'variables':{'ensure_playback':False}},blocking=True)
            self.assertEqual(len(seen),1);self.assertFalse(seen[0]['ensure_playback']);self.assertFalse(lease.state()['active'])
            for invalid in [{'script':'arbitrary','variables':{}},{'script':name,'variables':{'routing_owner':'forged-owner-0123456789'}}]:
                with self.assertRaises((ValueError,vol.Invalid)):await hass.services.async_call('home_media_bridge','run_legacy_router',invalid,blocking=True)
            self.assertEqual(len(seen),1)
            await hass.async_stop(force=True)
