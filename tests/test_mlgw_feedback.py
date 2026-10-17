import ast
from pathlib import Path
from types import SimpleNamespace
import os
import unittest
SOURCE=Path(os.environ.get('MLGW_MEDIA_PLAYER_SOURCE', '/nonexistent/optional-mlgw-source.py'))

def speaker(address='0x3', powered=False):
    tree=ast.parse(SOURCE.read_text()); cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='BeoSpeaker')
    init=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
    listener=next(n for n in init.body if isinstance(n,ast.FunctionDef) and n.name=='_beospeaker_message_listener')
    fake=SimpleNamespace(_ml=address,_mln=2,_pwon=powered,_playing=powered,_pending_source_request=False,source=None,
        clear_media_info=lambda:None,set_source_info=lambda *a:None,schedule_update_ha_state=lambda:None)
    fake.set_source=lambda value:setattr(fake,'source',value)
    ns={'self':fake,'Event':object,'_LOGGER':SimpleNamespace(debug=lambda *a:None),'STATE_PLAYING':'playing','STATE_OFF':'off','STATE_UNKNOWN':'unknown','STATE_PAUSED':'paused'}
    exec(compile(ast.Module(body=[listener],type_ignores=[]),'staged-listener','exec'),ns)
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='set_state')
    exec(compile(ast.Module(body=[method],type_ignores=[]),'staged-power-status','exec'),ns)
    state=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='state');state.decorator_list=[]
    exec(compile(ast.Module(body=[state],type_ignores=[]),'staged-power-state','exec'),ns)
    fake.read_state=lambda:ns['state'](fake)
    return fake,ns[listener.name],lambda state:ns['set_state'](fake,state)

def event(sender='0x3',kind='GOTO_SOURCE'):
    return SimpleNamespace(data={'from_device':sender,'to_device':'VIDEO_MASTER','payload_type':kind,
        'payload':{'source':'TV','sourceID':11,'channel_track':0}})

@unittest.skipUnless(SOURCE.is_file(), 'Set MLGW_MEDIA_PLAYER_SOURCE to check the optional staged MLGW repair')
class MlgwFeedbackTests(unittest.TestCase):
    def test_source_request_does_not_power_an_inactive_receiver(self):
        fake,listen,confirm=speaker();listen(event())
        self.assertFalse(fake._pwon)
        self.assertTrue(fake._pending_source_request)
        self.assertEqual(fake.source,11)
        self.assertEqual(fake.read_state(),'unknown')
        confirm('playing');self.assertTrue(fake._pwon);self.assertFalse(fake._pending_source_request)
    def test_active_room_still_gets_source_updates(self):
        fake,listen,_=speaker(powered=True);listen(event())
        self.assertTrue(fake._pwon);self.assertEqual(fake.source,11)
    def test_other_address_cannot_activate_receiver(self):
        fake,listen,_=speaker('other');listen(event());self.assertFalse(fake._pwon);self.assertIsNone(fake.source)
    def test_unknown_address_cannot_activate_receiver(self):
        fake,listen,_=speaker(None);listen(event());self.assertFalse(fake._pwon);self.assertIsNone(fake.source)
    def test_release_clears_pending_request(self):
        fake,listen,_=speaker();listen(event());listen(event(kind='RELEASE'))
        self.assertFalse(fake._pwon);self.assertFalse(fake._pending_source_request)
