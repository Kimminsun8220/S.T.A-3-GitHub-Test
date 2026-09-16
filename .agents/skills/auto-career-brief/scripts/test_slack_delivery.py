import tempfile
import unittest
from pathlib import Path
from slack_delivery import DeliveryError, Slack, adopt_receipts, deliver


class FakeSlack:
    def __init__(self):
        self.posts = []
        self.error_at = None
        self.timeout_at = None
        self.team = 'T1'

    def __call__(self, method, body):
        if method == 'auth.test':
            return {'ok': True, 'team_id': self.team, 'bot_id': 'B1'}
        index = len(self.posts)
        self.posts.append(body)
        if index == self.timeout_at:
            raise DeliveryError('timeout')
        if index == self.error_at:
            return {'ok': False, 'error': 'not_in_channel'}
        return {'ok': True, 'ts': f'100.{index}', 'channel': body['channel'], 'message': {'bot_id': 'B1'}}


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = Path(self.temp.name) / 'state.sqlite3'
        self.payload = {'workspace': 'T1', 'channel': 'C1', 'issue_id': '2026-09-15', 'messages': ['main', 'one', 'two', 'three']}
        self.api = FakeSlack()

    def run_delivery(self):
        return deliver(self.payload, self.ledger, self.api, pause=lambda _: None)

    def test_repeat_skips_and_replies_share_parent(self):
        self.run_delivery()
        result = self.run_delivery()
        self.assertEqual(len(self.api.posts), 4)
        self.assertTrue(all(r['status'] == 'skipped' for r in result))
        self.assertTrue(all(p['thread_ts'] == '100.0' for p in self.api.posts[1:]))

    def test_partial_rejection_resumes_only_missing_parts(self):
        self.api.error_at = 2
        with self.assertRaises(DeliveryError): self.run_delivery()
        self.api.error_at = None
        self.run_delivery()
        self.assertEqual([p['text'] for p in self.api.posts], ['main', 'one', 'two', 'two', 'three'])
        self.assertEqual(self.api.posts[-1]['thread_ts'], '100.0')

    def test_uncertain_response_blocks_retry(self):
        self.api.timeout_at = 1
        with self.assertRaises(DeliveryError): self.run_delivery()
        with self.assertRaises(DeliveryError): self.run_delivery()
        self.assertEqual(len(self.api.posts), 2)

    def test_changed_content_same_issue_blocks(self):
        self.run_delivery()
        self.payload['messages'][1] = 'edited'
        with self.assertRaises(DeliveryError): self.run_delivery()
        self.assertEqual(len(self.api.posts), 4)

    def test_wrong_workspace_and_user_token_block(self):
        self.api.team = 'T2'
        with self.assertRaises(DeliveryError): self.run_delivery()
        with self.assertRaises(DeliveryError): Slack('xoxp-test')
        self.assertFalse(self.api.posts)

    def test_overlapping_worker_cannot_send_pending_part(self):
        original = self.api
        def overlapping(method, body):
            if method == 'chat.postMessage':
                with self.assertRaises(DeliveryError):
                    deliver(self.payload, self.ledger, original, pause=lambda _: None)
            return original(method, body)
        deliver(self.payload, self.ledger, overlapping, pause=lambda _: None)
        self.assertEqual(len(original.posts), 4)

    def test_adopt_prior_delivery_prevents_posting(self):
        receipts = [{'index': i, 'ok': True, 'channel': 'C1', 'bot_id': 'B1', 'ts': f'90.{i}'} for i in range(4)]
        adopt_receipts(self.payload, self.ledger, receipts)
        self.run_delivery()
        self.assertFalse(self.api.posts)
        with self.assertRaises(DeliveryError): adopt_receipts(self.payload, self.ledger, receipts)


if __name__ == '__main__':
    unittest.main()
