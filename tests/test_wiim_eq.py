import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer, make_mocked_request
from custom_components.home_media_bridge.wiim_eq import WiiMEqReader, profile_status, PEQ_READ_COMMAND
from custom_components.home_media_bridge.client import BridgeUnavailable
from custom_components.home_media_bridge import WiiMEqView

class ProfileTests(unittest.TestCase):
    def test_custom_peq_not_graphic_eq(self):
        s=profile_status(dict(status='OK', EQStat='On', Name='BL9 Stereo Flat', channelMode='L/R', source_name='wifi',eq=0))
        self.assertEqual(s['profile'],'BL9 Stereo Flat'); self.assertTrue(s['enabled'])
        self.assertEqual(s['channel_mode'],'L/R'); self.assertGreater(s['observed_at_ms'],0)
    def test_disabled_retains_name_without_claiming_enabled(self):
        self.assertFalse(profile_status(dict(status='OK',EQStat='Off',Name='Bedroom'))['enabled'])
    def test_unknown_not_off(self):
        for raw in [None,{},dict(status='Failed'),dict(status='OK',EQStat='Unknown')]:
            with self.assertRaises(ValueError):profile_status(raw)
    def test_untrusted_hosts(self):
        for host in ['8.8.8.8','https://127.0.0.1','127.0.0.1/secret']:
            with self.assertRaises(ValueError):WiiMEqReader(None,host)

class ReaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_read_and_cached_then_failure_clears(self):
        seen=[];fail=False
        async def handle(request):
            seen.append((request.method,request.query.get('command'),request.headers.get('Authorization')))
            if fail:return web.Response(status=500)
            return web.json_response(dict(status='OK',EQStat='On',Name='BL9 Stereo Flat'))
        app=web.Application();app.router.add_get('/httpapi.asp',handle)
        async with TestServer(app) as server, ClientSession() as session:
            reader=WiiMEqReader(session,'127.0.0.1')
            original=session.get
            def local_get(url,**kw):return original(str(server.make_url('/httpapi.asp'))+'?'+url.split('?',1)[1],**kw)
            with patch.object(session,'get',side_effect=local_get):
                self.assertEqual((await reader.status())['profile'],'BL9 Stereo Flat')
                await reader.status();self.assertEqual(len(seen),1)
                self.assertEqual(json.loads(PEQ_READ_COMMAND.split(":", 1)[1])["EQLevel"], 2)
                self.assertEqual(seen[0],('GET',PEQ_READ_COMMAND,None))
                reader._expires=0;fail=True
                with self.assertRaises(BridgeUnavailable):await reader.status()
                self.assertIsNone(reader._cached)
    async def test_read_view_rejects_query_and_absent_configuration(self):
        view=WiiMEqView(SimpleNamespace(data={}))
        self.assertTrue(view.requires_auth)
        response=await view.get(make_mocked_request('GET',view.url+'?host=evil'))
        self.assertEqual(response.status,400)
        response=await view.get(make_mocked_request('GET',view.url))
        self.assertEqual(response.status,503);self.assertFalse(json.loads(response.text)['available'])
