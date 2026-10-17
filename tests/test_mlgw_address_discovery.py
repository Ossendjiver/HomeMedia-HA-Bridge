import ast,asyncio,logging,pathlib,types,unittest,os
SOURCE=pathlib.Path(os.environ.get('MLGW_MEDIA_PLAYER_SOURCE','/nonexistent-mlgw-source'))
node=next((n for n in ast.parse(SOURCE.read_text() if SOURCE.is_file() else '').body if isinstance(n,ast.AsyncFunctionDef) and n.name=='async_create_devices'),None)
for n in ast.walk(node) if node else []:
 if isinstance(n,ast.arg):n.annotation=None
 if isinstance(n,ast.AnnAssign):n.annotation=ast.Name(id='object',ctx=ast.Load())
class Device:
 def __init__(self,mln,*args,**kwargs):self.mln=mln;self.ml=None
 def set_ml(self,ml):self.ml=ml
class Bus:
 def __init__(self):self.listener=None;self.closed=False
 def async_listen(self,event,callback):
  self.listener=callback
  def close():self.closed=True;self.listener=None
  return close
class Gateway:
 def __init__(self,replies,use=True,connected=True):
  self.replies=replies;self.calls=[];self.devices=[];self.connectedMLGW=True;self.connectedML=connected;self.use_mllog=use;self._hass=types.SimpleNamespace(bus=Bus())
 def set_devices(self,devices):self.devices=devices
 def mlgw_send_beo4_cmd(self,mln,*args):
  self.calls.append(mln)
  if mln in self.replies:
   def reply():
    if self._hass.bus.listener:self._hass.bus.listener(types.SimpleNamespace(data={'from_device':'MLGW','payload_type':'MLGW_REMOTE_BEO4','payload':{'command':'Light Timeout'},'to_device':self.replies[mln]}))
   asyncio.get_running_loop().call_later(.001,reply)
ns={'asyncio':asyncio,'_LOGGER':logging.getLogger('test'),'BeoSpeaker':Device,'MLGW_EVENT_ML_TELEGRAM':'event','reverse_ml_destselectordict':{'AUDIO SOURCE':1},'BEO4_CMDS':{'LIGHT TIMEOUT':0x58},'ML_ID_TIMEOUT':.02}
if node:exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(SOURCE),'exec'),ns)
CONFIG={'zones':[{'number':1,'name':'room','products':[{'MLN':i,'name':str(i),'sources':[]} for i in [3,1,2,4]]}]}
@unittest.skipUnless(node is not None,'Set MLGW_MEDIA_PLAYER_SOURCE to the patched module')
class Tests(unittest.IsolatedAsyncioTestCase):
 async def run_discovery(self,g):
  added=[];await ns['async_create_devices'](CONFIG,g,added.extend);self.assertEqual(added,g.devices);return g
 async def test_correct_room_addresses(self):
  g=await self.run_discovery(Gateway({3:'0x2',1:'VIDEO_MASTER',2:'0xd',4:'0x3'}));self.assertEqual(g.calls,[3,1,2,4]);self.assertEqual([x.ml for x in g.devices],['0x2','VIDEO_MASTER','0xd','0x3']);self.assertTrue(g._hass.bus.closed)
 async def test_timeout_aborts_before_next_room(self):
  g=await self.run_discovery(Gateway({3:'0x2',2:'0xd',4:'0x3'}));self.assertEqual(g.calls,[3,1]);self.assertEqual([x.ml for x in g.devices],['0x2',None,None,None]);self.assertTrue(g._hass.bus.closed)
 async def test_duplicate_aborts_without_assigning(self):
  g=await self.run_discovery(Gateway({3:'0x2',1:'0x2',2:'0xd'}));self.assertEqual(g.calls,[3,1]);self.assertIsNone(g.devices[1].ml)
 async def test_logging_disabled_sends_no_probe(self):
  g=await self.run_discovery(Gateway({},use=False));self.assertEqual(g.calls,[]);self.assertIsNone(g._hass.bus.listener)
 async def test_no_ml_connection_sends_no_probe(self):
  g=await self.run_discovery(Gateway({},connected=False));self.assertEqual(g.calls,[]);self.assertTrue(g._hass.bus.closed)
 async def test_cancellation_unsubscribes(self):
  g=Gateway({});task=asyncio.create_task(ns['async_create_devices'](CONFIG,g,lambda x:None));await asyncio.sleep(.001);task.cancel()
  with self.assertRaises(asyncio.CancelledError):await task
  self.assertTrue(g._hass.bus.closed)
if __name__=='__main__':unittest.main()
