import threading
import unittest
from experiments.nonecap.budget import Budget, LimitReached, ChargeUnconfirmed
from experiments.nonecap.client import ServiceError
from experiments.nonecap.solver import Solver, Interrupted

WIDGET = dict(sitekey='00000000-0000-0000-0000-000000000001', rqdata='', user_agent='test')


class FakeClient:
    def __init__(self):
        self.creates = self.cancels = 0
        self.response = dict(id='solve_test', status='solved', token='fake-token', credits_charged=2)
        self.on_create = lambda: None
        self.cancel_response = dict(id='solve_test', status='cancelled', credits_charged=0)
    def balance(self): return dict(balance=100, plan_remaining=0)
    def create(self, *args, **kwargs):
        self.creates += 1; self.on_create()
        return dict(self.response)
    def get(self, job): return dict(self.response)
    def cancel(self, job):
        self.cancels += 1
        if isinstance(self.cancel_response, Exception): raise self.cancel_response
        return dict(self.cancel_response)


class SolverTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient(); self.budget = Budget(5, 3)
        self.stop = threading.Event(); self.skip = threading.Event()
        self.solver = Solver(self.client, self.budget, lambda data: None)
    def solve(self): return self.solver.solve(WIDGET, self.stop, self.skip, timeout=.1)

    def test_one_paid_attempt_and_exact_reported_charge(self):
        self.assertEqual(self.solve(), 'fake-token')
        self.assertEqual((self.client.creates, self.budget.spent), (1, 2))

    def test_budget_checked_before_creating_another_solve(self):
        self.budget.spent = 5
        with self.assertRaises(LimitReached): self.solve()
        self.assertEqual(self.client.creates, 0)

    def test_stop_cancels_pending_job_without_retrying(self):
        self.client.response['status'] = 'pending'
        self.client.on_create = self.stop.set
        with self.assertRaises(Interrupted): self.solve()
        self.assertEqual((self.client.creates, self.client.cancels, self.budget.spent), (1, 1, 0))

    def test_cancellation_race_records_already_completed_charge(self):
        self.client.response['status'] = 'pending'
        def complete_and_stop():
            self.stop.set()
            # Initial reply pending, but subsequent receipt is solved.
        self.client.on_create = complete_and_stop
        self.client.cancel_response = dict(id='solve_test', status='solved', token='fake-token', credits_charged=2)
        with self.assertRaises(Interrupted): self.solve()
        self.assertEqual(self.budget.spent, 2)

    def test_unconfirmed_cancel_blocks_future_automatic_calls(self):
        self.client.response['status'] = 'pending'; self.client.on_create = self.stop.set
        self.client.cancel_response = ServiceError('network_error')
        with self.assertRaises(Interrupted): self.solve()
        self.assertTrue(self.budget.blocked)

    def test_missing_charge_is_not_assumed_free(self):
        self.client.response.pop('credits_charged')
        with self.assertRaises(LimitReached): self.solve()
        self.assertTrue(self.budget.blocked)

    def test_missing_charge_rechecks_existing_job_without_another_paid_solve(self):
        self.client.response['credits_charged']=None
        reads=[]
        def receipt(job):
            reads.append(job)
            return dict(self.client.response,credits_charged=2)
        self.client.get=receipt
        self.assertEqual(self.solve(),'fake-token')
        self.assertEqual((self.client.creates,len(reads),self.budget.spent),(1,1,2))
        self.assertFalse(self.budget.blocked)

    def test_unconfirmed_charge_is_distinct_from_exhausted_limit(self):
        self.client.response['credits_charged']=None
        reads=[]
        def missing(job): reads.append(job); return dict(self.client.response)
        self.client.get=missing
        with self.assertRaises(ChargeUnconfirmed) as error: self.solve()
        self.assertIn('solved',str(error.exception))
        self.assertEqual(len(reads),1)
        with self.assertRaises(ChargeUnconfirmed): self.budget.check()

    def test_ambiguous_post_failure_is_never_retried(self):
        def fail(*args, **kwargs):
            self.client.creates += 1
            raise ServiceError('network_error', uncertain=True)
        self.client.create = fail
        with self.assertRaises(ServiceError): self.solve()
        self.assertEqual(self.client.creates, 1)
        self.assertTrue(self.budget.blocked)

    def test_skip_cancels_pending_job_and_consumes_skip_signal(self):
        self.client.response['status'] = 'pending'; self.client.on_create = self.skip.set
        with self.assertRaises(Interrupted) as error: self.solve()
        self.assertEqual(error.exception.kind, 'skip')
        self.assertFalse(self.skip.is_set())
        self.assertEqual(self.client.cancels, 1)

    def test_cancel_conflict_reads_final_receipt_once(self):
        self.client.response['status'] = 'pending'; self.client.on_create = self.stop.set
        self.client.cancel_response = ServiceError('conflict')
        gets = []
        def receipt(job):
            gets.append(job)
            return dict(id=job, status='solved', token='fake-token', credits_charged=3)
        self.client.get = receipt
        with self.assertRaises(Interrupted): self.solve()
        self.assertEqual((self.budget.spent, len(gets)), (3, 1))

    def test_exhausted_account_never_creates_a_solve(self):
        self.client.balance = lambda: dict(balance=0, plan_remaining=0)
        with self.assertRaises(ServiceError): self.solve()
        self.assertEqual(self.client.creates, 0)

    def test_solution_metadata_is_available_to_browser_but_not_notifications(self):
        updates = []
        self.solver.notify = updates.append
        self.client.response.update(resp_key='secret-response-key', user_agent='browser UA')
        self.solve()
        self.assertEqual(self.solver.solution_meta['resp_key'], 'secret-response-key')
        self.assertNotIn('fake-token', str(updates))
        self.assertNotIn('secret-response-key', str(updates))
