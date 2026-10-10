import unittest
from custom_components.home_media_bridge.policy import validate


class SessionFeedbackTests(unittest.TestCase):
    def test_allowlist_and_vote_boundary(self):
        payload = dict(action='feedback', queue_id='q', session_id='session', current_item_id='song', vote=1)
        self.assertEqual(validate('mix', payload=payload)[:2], ('POST', '/library/mix'))
        self.assertEqual(validate('mix_state', query={'queue_id':'q','feedback':'1'})[:2], ('GET', '/library/mix'))
        for changes in ({'vote':True}, {'vote':2}, {'vote':'1'}, {'session_id':''}, {'current_item_id':{}}, {'url':'http://evil'}):
            with self.assertRaises(ValueError):validate('mix', payload=dict(payload, **changes))
        with self.assertRaises(ValueError):validate('mix_state', query={'queue_id':'q','feedback':'all'})

    def test_reasons_are_vote_scoped_and_cannot_change_routes(self):
        payload = dict(action='feedback', queue_id='q', session_id='s', current_item_id='i')
        for vote, reasons in ((1, ['more_like_this']), (-1, ['wrong_mood', 'overplayed', 'dislike_recording'])):
            for reason in reasons:
                self.assertEqual(validate('mix', payload=dict(payload, vote=vote, reason=reason))[1], '/library/mix')
        for vote, reason in ((1,'wrong_mood'), (-1,'more_like_this'), (0,'overplayed'), (-1,'http://evil'), (-1,'')):
            with self.assertRaises(ValueError): validate('mix', payload=dict(payload, vote=vote, reason=reason))
        with self.assertRaises(ValueError): validate('mix', payload=dict(payload, action='begin', vote=-1, reason='overplayed'))
