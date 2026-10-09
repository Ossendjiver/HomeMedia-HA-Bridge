"""Offline protocol and HA view checks using a local fake BS5c service."""
import asyncio
import json
import math
import unittest
from types import SimpleNamespace
from aiohttp import web, ClientSession
from aiohttp.test_utils import TestServer, TestClient, make_mocked_request
from custom_components.home_media_bridge.policy import validate, local_host
from custom_components.home_media_bridge.client import BridgeClient, BridgeUnavailable
from custom_components.home_media_bridge import AuthClientView, BridgeView, async_setup, async_unload_entry

class PolicyTests(unittest.TestCase):
    def test_host_boundary(self):
        self.assertEqual(local_host('192.168.4.103'), '192.168.4.103')
        self.assertEqual(local_host('beosound5c.local'),'beosound5c.local')
        for host in ['https://example.org','8.8.8.8','169.254.169.254/secret','0.0.0.0','evil.local/path','224.0.0.1','example.com']:
            with self.subTest(host=host), self.assertRaises(ValueError):local_host(host)
    def test_command_boundary(self):
        for operation, query, payload in [('proxy',{},{}),('mood',{'url':'http://evil'},{}),('mix',{}, {'action':'raw','queue_id':'q'}),('mix',{}, {'action':'update','queue_id':'q','radius':2,'angle':0}),('mix',{}, {'action':'update','queue_id':'q','radius':.5,'angle':math.nan}),('recommend',{'limit':999},{}),('mood',{}, {'host':'evil'})]:
            with self.subTest(operation=operation), self.assertRaises(ValueError):validate(operation,query,payload)
    def test_skip_feedback_boundary(self):
        payload=dict(type='listen_feedback', event_id='event-0123456789012345',timestamp_ms=1791514724000,
                     seconds=120,title='Song',uri='tidal://track/1',reason='skip')
        self.assertEqual(validate('event',payload=payload)[:2],('POST','/library/event'))
        for bad in [dict(payload,event_id='short'),dict(payload,seconds=-1),dict(payload,reason='pause')]:
            with self.assertRaises(ValueError):validate('event',payload=bad)

    def test_valid_commands(self):
        self.assertEqual(validate('mix',{}, {'action':'update','queue_id':'q','angle':270,'radius':.5})[:2],('POST','/library/mix'))
        self.assertEqual(validate('recommend',{'room':'phone','limit':'20'},{} )[0],'GET')

class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls=[]
        async def handle(request):
            self.calls.append((request.method,request.path,request.headers.get('Authorization'),dict(request.query),await request.json() if request.method=='POST' else None))
            if request.path.endswith('/bad'):return web.Response(text='bad')
            return web.json_response({'active':True,'suggested':{'angle':270,'radius':.5}})
        app=web.Application();app.router.add_route('*','/{tail:.*}',handle)
        self.server=TestServer(app);await self.server.start_server()
        self.session=ClientSession()
        self.bridge=BridgeClient(self.session,'127.0.0.1',self.server.port)
    async def asyncTearDown(self):
        await self.session.close();await self.server.close()
    async def test_maps_read_and_write_without_forwarding_credentials(self):
        await self.bridge.request('mood',{'room':'phone'})
        await self.bridge.request('mix',payload={'action':'stop','queue_id':'q'})
        self.assertEqual([x[:3] for x in self.calls],[('GET','/library/mood',None),('POST','/library/mix',None)])
        self.assertEqual(self.calls[1][4],{'action':'stop','queue_id':'q'})
    async def test_rejects_before_network(self):
        with self.assertRaises(ValueError):await self.bridge.request('proxy',{'url':'http://evil'})
        self.assertEqual(self.calls,[])
    async def test_redirect_not_followed(self):
        async def redirect(request):raise web.HTTPFound('/secret')
        app=web.Application();app.router.add_route('*','/{tail:.*}',redirect)
        async with TestServer(app) as server:
            bridge=BridgeClient(self.session,'127.0.0.1',server.port)
            with self.assertRaises(BridgeUnavailable):await bridge.request('mood')
    async def test_error_not_replayed(self):
        seen=[]
        async def fail(request):seen.append(request.method);return web.Response(status=503)
        app=web.Application();app.router.add_route('*','/{tail:.*}',fail)
        async with TestServer(app) as server:
            bridge=BridgeClient(self.session,'127.0.0.1',server.port)
            with self.assertRaises(BridgeUnavailable):await bridge.request('mix',payload={'action':'stop','queue_id':'q'})
        self.assertEqual(seen,['POST'])
    async def test_actual_ha_views_and_unload(self):
        hass=SimpleNamespace(data={'home_media_bridge':{'entry':self.bridge}})
        view=BridgeView(hass)
        self.assertTrue(view.requires_auth)
        status=await view.get(make_mocked_request('GET','/api/home_media_bridge'))
        self.assertTrue(json.loads(status.text)['configured'])
        await async_unload_entry(hass,SimpleNamespace(entry_id='entry'))
        status=await view.get(make_mocked_request('GET','/api/home_media_bridge'))
        self.assertFalse(json.loads(status.text)['configured'])
        client=AuthClientView();self.assertFalse(client.requires_auth)
        response=await client.get(make_mocked_request('GET','/api/home_media_bridge/auth-client'))
        self.assertIn('rel="redirect_uri" href="homemedia://ha/auth"',response.text)
        self.assertNotIn('192.168',response.text)
    async def test_chunked_response_and_size_boundary(self):
        async def stream(request):
            response=web.StreamResponse(headers={'Content-Type':'application/json'});await response.prepare(request)
            for part in [b'{"active":',b'true}']:await response.write(part);await asyncio.sleep(.01)
            await response.write_eof();return response
        app=web.Application();app.router.add_route('*','/{tail:.*}',stream)
        async with TestServer(app) as server:
            bridge=BridgeClient(self.session,'127.0.0.1',server.port)
            self.assertEqual(await bridge.request('mood'),{'active':True})
        async def large(request):return web.Response(body=b' '*1048577)
        app=web.Application();app.router.add_route('*','/{tail:.*}',large)
        async with TestServer(app) as server:
            bridge=BridgeClient(self.session,'127.0.0.1',server.port)
            with self.assertRaises(BridgeUnavailable):await bridge.request('mood')
    async def test_ha_post_contract(self):
        hass=SimpleNamespace(data={'home_media_bridge':{'entry':self.bridge}})
        view=BridgeView(hass)
        @web.middleware
        async def admin(request, handler):
            from homeassistant.components.http.const import KEY_HASS_USER
            request[KEY_HASS_USER]=SimpleNamespace(is_admin=True)
            return await handler(request)
        app=web.Application(middlewares=[admin]);app.router.add_post('/api/home_media_bridge',view.post)
        async with TestClient(TestServer(app)) as client:
            response=await client.post('/api/home_media_bridge',json={'operation':'mix','payload':{'action':'stop','queue_id':'q'}})
            self.assertEqual(response.status,200)
            self.assertTrue((await response.json())['active'])
            response=await client.post('/api/home_media_bridge',json={'operation':'proxy','payload':{'url':'http://evil'}})
            self.assertEqual(response.status,400)
            response=await client.post('/api/home_media_bridge',data='x'*65537)
            self.assertEqual(response.status,413)
            hass.data['home_media_bridge'].clear()
            response=await client.post('/api/home_media_bridge',json={'operation':'mood'})
            self.assertEqual(response.status,503)

class HaAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_ha_authentication_and_admin_boundary(self):
        import tempfile
        from homeassistant.core import HomeAssistant
        from homeassistant.auth import auth_manager_from_config
        from homeassistant.components.http.auth import async_setup_auth
        from homeassistant.helpers.http import KEY_HASS
        with tempfile.TemporaryDirectory() as directory:
            hass=HomeAssistant(directory)
            from homeassistant.helpers import device_registry as dr, entity_registry as er
            hass.data[dr.DATA_REGISTRY]=dr.DeviceRegistry(hass)
            hass.data[er.DATA_REGISTRY]=er.EntityRegistry(hass)
            hass.auth=await auth_manager_from_config(hass,[],[])
            hass.data['home_media_bridge']={}
            app=web.Application();app[KEY_HASS]=hass
            await async_setup_auth(hass,app)
            BridgeView(hass).register(hass,app,app.router)
            AuthClientView().register(hass,app,app.router)
            async with TestClient(TestServer(app)) as client:
                self.assertEqual((await client.get('/api/home_media_bridge')).status,401)
                self.assertEqual((await client.post('/api/home_media_bridge',json={'operation':'mood'})).status,401)
                self.assertEqual((await client.get('/api/home_media_bridge/auth-client')).status,200)
                admin=await hass.auth.async_create_user('Bridge test admin',group_ids=['system-admin'])
                refresh=await hass.auth.async_create_refresh_token(admin,client_id="https://example.test/client")
                token=hass.auth.async_create_access_token(refresh)
                headers={'Authorization':'Bearer '+token}
                self.assertEqual((await client.get('/api/home_media_bridge',headers=headers)).status,200)
                self.assertEqual((await client.post('/api/home_media_bridge',headers=headers,json={'operation':'mood'})).status,503)
                readonly=await hass.auth.async_create_user('Read only test',group_ids=['system-read-only'])
                refresh=await hass.auth.async_create_refresh_token(readonly,client_id="https://example.test/client")
                token=hass.auth.async_create_access_token(refresh)
                self.assertEqual((await client.post('/api/home_media_bridge',headers={'Authorization':'Bearer '+token},json={'operation':'mood'})).status,403)
            await hass.async_stop(force=True)

if __name__=='__main__':unittest.main()
