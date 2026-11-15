import unittest
import io
import json
import urllib.error
from unittest.mock import patch
from al_results.nonecap.client import Client, ServiceError, NoRedirects
from al_results.nonecap.budget import Budget, LimitReached

KEY = 'nc_live_' + 'x' * 32


class ClientTests(unittest.TestCase):
    def test_client_sends_only_auth_and_minimal_challenge_fields(self):
        calls = []
        def transport(method, path, headers, body):
            calls.append((method, path, headers, body))
            return {'id': 'solve_test', 'status': 'pending'}
        client = Client(KEY, transport=transport)
        client.create('00000000-0000-0000-0000-000000000001', user_agent='test browser')
        method, path, headers, body = calls[0]
        self.assertEqual((method, path), ('POST', '/v1/solves'))
        self.assertEqual(headers['Authorization'], 'Bearer ' + KEY)
        self.assertEqual(set(body), {'type', 'sitekey', 'url', 'user_agent'})
        self.assertEqual(body['url'], 'https://www.doenets.lk/examresults')

    def test_invalid_job_ids_and_keys_are_rejected_without_leaking_key(self):
        with self.assertRaises(ServiceError) as error:
            Client(KEY + '\nsecret')
        self.assertNotIn(KEY, str(error.exception))
        client = Client(KEY, transport=lambda *args: self.fail('Should not call transport'))
        with self.assertRaises(ServiceError):
            client.get('../other-url')

    def test_account_response_never_returns_account_identity_to_ui(self):
        client = Client(KEY, transport=lambda *args: {'credits_balance': 50, 'email': 'private@example.test', 'plan': {'remaining_today': 3}})
        self.assertEqual(client.balance(), {'balance': 50, 'plan_remaining': 3})

    def test_http_errors_hide_server_messages_and_ambiguous_post_is_flagged(self):
        body = json.dumps({'error': {'code': 'service_error', 'message': KEY + ' echoed secret'}}).encode()
        error = urllib.error.HTTPError('https://api.nonecap.com/v1/solves', 503, 'Unavailable', {}, io.BytesIO(body))
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(ServiceError) as caught:
                Client(KEY).create('00000000-0000-0000-0000-000000000001')
        self.assertTrue(caught.exception.uncertain)
        self.assertNotIn(KEY, str(caught.exception))
        self.assertNotIn('echoed secret', str(caught.exception))

    def test_redirects_are_refused_instead_of_forwarding_authentication(self):
        self.assertIsNone(NoRedirects().redirect_request(None, None, 307, '', {}, 'https://other.example'))


class BudgetTests(unittest.TestCase):
    def test_limits_apply_across_attempts_and_charge_can_cross_soft_threshold(self):
        budget = Budget(credit_limit=5, max_attempts=3)
        budget.reserve(); budget.settle('solve_one', 3)
        budget.reserve(); budget.settle('solve_two', 3)
        self.assertEqual(budget.spent, 6)
        with self.assertRaises(LimitReached): budget.reserve()

    def test_uncertain_charge_blocks_further_spending(self):
        budget = Budget(credit_limit=50, max_attempts=3)
        budget.reserve(); budget.uncertain()
        with self.assertRaises(LimitReached): budget.reserve()

    def test_receipt_is_not_counted_twice_and_attempt_cap_counts_free_solves(self):
        budget = Budget(credit_limit=10, max_attempts=1)
        budget.reserve(); budget.settle('solve_one', 0); budget.settle('solve_one', 0)
        self.assertEqual(budget.spent, 0)
        with self.assertRaises(LimitReached): budget.reserve()
