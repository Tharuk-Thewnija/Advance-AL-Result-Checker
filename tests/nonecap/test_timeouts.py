"""Timeout control flow with simulated API, browsers and real checkpoints."""
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import pandas as pd
from selenium.common.exceptions import TimeoutException

from al_results.checkpoints import CheckpointStore
from al_results.models import InputWorkbook, RunConfig, RowResult
from al_results.nonecap.budget import Budget, ChargeUnconfirmed, LimitReached
from al_results.nonecap.client import Client, ServiceError
from al_results.nonecap.collector import AutomaticCollector, private_core
from al_results.nonecap.solver import Solver
from tests.test_parsing import CARD


class TimeoutTests(unittest.TestCase):
    def test_simultaneous_connection_failures_pause_once_and_preserve_checkpoint(self):
        for stage, reason in [('balance check', 'service_connection'), ('solve creation', 'billing_unconfirmed')]:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOCALAPPDATA':directory}):
                root = Path(directory)
                book = InputWorkbook(root/'test.xlsx', 'hash', 'Sheet1', pd.DataFrame({'NIC':[str(200000000000+i) for i in range(100)]}))
                config = RunConfig(book.path, ('20',), (), '2025', 120, root)
                store = CheckpointStore.open(book, config)
                saved = RowResult(0, 'Completed', {'subject:20':'A'})
                store.save(saved)
                core = private_core()
                class Session:
                    def __init__(self):
                        self.driver = Mock()
                        self.driver.execute_script.return_value = {'sitekey':'00000000-0000-0000-0000-000000000001'}
                    def fetch(self, nic, config, stop, skip, ready):
                        ready()
                        raise AssertionError('Worker continued after the failed request')
                    def close(self): pass
                core.BrowserSession = Session
                barrier = threading.Barrier(5)
                def transport(method, path, headers, body):
                    if stage == 'solve creation' and method == 'GET':
                        return {'credits_balance':100}
                    barrier.wait(timeout=5)
                    raise ServiceError('network_error', uncertain=method=='POST')
                adapter = AutomaticCollector(lambda update: None)
                adapter.core_factory = lambda: core
                adapter.workers = 5
                budget = Budget(2000,200)
                adapter.solver = Solver(Client('nc_live_'+'x'*32, transport=transport), budget, lambda update: None)
                events = []
                adapter(config, book, store, events.append, threading.Event(), threading.Event())
                self.assertEqual(events[-1].kind, 'stopped')
                self.assertEqual(events[-1].payload['reason'], reason)
                self.assertIn(stage, events[-1].payload['error'])
                messages = [e.payload['text'] for e in events if e.kind=='log']
                self.assertEqual(sum('Automatic collection paused.' in m for m in messages), 1)
                self.assertFalse(any('MANUAL ACTION REQUIRED' in m for m in messages))
                self.assertEqual(budget.attempts, 5 if stage=='solve creation' else 0)
                self.assertEqual(budget.blocked, stage=='solve creation')
                reader = CheckpointStore.open(book, config)
                try:
                    self.assertEqual(reader.results(), [saved])
                    self.assertEqual(reader.pending_positions(), list(range(1,100)))
                finally:
                    reader.close()

    def scenario(self, workers=1, uncertain=False, resume=False, submission=False):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOCALAPPDATA': directory}):
            root = Path(directory)
            count = workers+2
            book = InputWorkbook(root/'fictional.xlsx', 'hash', 'Sheet1', pd.DataFrame({'NIC':[str(200000000001+i) for i in range(count)]}))
            config = RunConfig(book.path, ('20',), (), '2025', 120, root)
            context = threading.local()
            barrier = threading.Barrier(workers)
            adapter = AutomaticCollector(lambda update: None)
            core = private_core()
            class Driver:
                def execute_cdp_cmd(self, *args): pass
                def execute_script(self, source, *args):
                    if '__alSiteNoticeSeen' in source: return False
                    if 'Return challenge metadata' in source:
                        return dict(sitekey='00000000-0000-0000-0000-000000000001', user_agent='test')
                    return dict(applied=True, callback=True) if args else True
                def find_elements(self, *args): return []
            class Session:
                def __init__(self): self.driver = Driver()
                def fetch(self, nic, config, stop, skip, ready):
                    context.nic = nic
                    ready()
                    if submission and client.fail and nic.endswith('1'):
                        raise TimeoutException('Simulated missing result after submission')
                    if submission and client.fail:
                        adapter.pause.wait(2)  # Hold successful in-flight rows until the failing row pauses.
                    return CARD
                def close(self): pass
            core.BrowserSession = Session
            core.wait_for_results_or_skip = lambda *args: CARD
            adapter.core_factory = lambda: core
            class Client:
                creates = cancels = 0
                fail = True
                def balance(self): return dict(balance=1000, plan_remaining=0)
                def create(self, *args, **kwargs):
                    self.creates += 1
                    job = 'solve_'+context.nic+'_'+str(self.creates)
                    barrier.wait(timeout=5)
                    return dict(id=job, status='pending' if not submission and self.fail and context.nic.endswith('1') else 'solved', token='fake-token', credits_charged=1)
                def cancel(self, job):
                    self.cancels += 1
                    if uncertain: raise ServiceError('network_error')
                    return dict(id=job, status='cancelled', credits_charged=0)
            client = Client()
            budget = Budget(2000, 200)
            adapter.workers = workers
            adapter.solver = Solver(client, budget, lambda update: None)
            original = Solver.solve
            def immediate(self, widget, stop, skip, **kwargs):
                return original(self, widget, stop, skip, timeout=0)
            events = []
            with patch.object(Solver, 'solve', immediate):
                adapter(config, book, CheckpointStore.open(book, config), events.append, threading.Event(), threading.Event())
            terminal = events[-1]
            self.assertEqual(terminal.kind, 'stopped', terminal)
            self.assertEqual(terminal.payload['reason'], 'billing_unconfirmed' if uncertain else 'submission_timeout' if submission else 'automatic_timeout')
            self.assertEqual((client.creates, client.cancels), (workers, 0 if submission else 1))
            self.assertFalse(adapter.disabled)
            self.assertEqual(budget.blocked, uncertain)
            self.assertFalse(any('MANUAL ACTION REQUIRED' in e.payload.get('text','') or 'complete CAPTCHA in Chrome' in e.payload.get('text','') for e in events))
            store = CheckpointStore.open(book, config)
            try:
                self.assertEqual(len(store.results()), workers-1)
                self.assertTrue(all(row.status=='Completed' for row in store.results()))
                self.assertIn(0, store.pending_positions())
                self.assertEqual(len(store.pending_positions()), 3)
            finally: store.close()
            if resume:
                client.fail = False
                events.clear()
                # Production builds a fresh private module on every run. Reusing
                # one here would nest Session classes/startup locks artificially.
                resumed_core = private_core()
                resumed_core.BrowserSession = Session
                adapter.core_factory = lambda: resumed_core
                with patch.object(Solver, 'solve', immediate):
                    adapter(config, book, CheckpointStore.open(book, config), events.append, threading.Event(), threading.Event())
                self.assertEqual(events[-1].kind, 'finished')
                self.assertEqual(events[-1].payload['completed'], count)
                self.assertEqual((client.creates, client.cancels, budget.attempts, budget.spent),
                                 (count+1, 0 if submission else 1, count+1, count+1 if submission else count))

    def test_single_worker_timeout_pauses_without_marking_error(self): self.scenario()
    def test_two_worker_timeout_allows_inflight_result(self): self.scenario(workers=2)
    def test_five_worker_timeout_allows_inflight_results(self): self.scenario(workers=5)
    def test_uncertain_cancellation_uses_billing_pause(self): self.scenario(uncertain=True)
    def test_explicit_resume_retries_pending_rows_without_resetting_usage(self): self.scenario(resume=True)
    def test_submission_timeout_keeps_single_worker_row_pending(self): self.scenario(submission=True)
    def test_submission_timeout_keeps_two_workers_from_manual_cascade(self): self.scenario(submission=True,workers=2)
    def test_submission_timeout_keeps_five_workers_from_manual_cascade(self): self.scenario(submission=True,workers=5)
    def test_submission_timeout_resume_preserves_paid_token_charge(self): self.scenario(submission=True,resume=True)

    def test_timeout_does_not_replace_billing_pause(self):
        adapter = AutomaticCollector(lambda update: None)
        adapter.pause_at_limit(ChargeUnconfirmed('Missing receipt'), lambda event: None)
        adapter.pause_for_timeout(Budget(100,10), lambda event: None)
        adapter.pause_collection('Site result did not arrive', 'submission_timeout', lambda event: None)
        adapter.pause_at_limit(LimitReached('Attempt limit'), lambda event: None)
        self.assertEqual(adapter.pause_kind, 'billing_unconfirmed')
