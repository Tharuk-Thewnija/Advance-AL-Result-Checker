"""Concurrent scheduling with real SQLite, no browser or provider requests."""
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from al_results import collector as core
from al_results.checkpoints import CheckpointStore
from al_results.models import InputWorkbook, RunConfig
from experiments.nonecap.parallel import collect_parallel
from experiments.nonecap.budget import Budget, LimitReached
from experiments.nonecap.collector import PrototypeCollector, DRIVER_STARTUP_LOCK
from experiments.nonecap.solver import Solver, Interrupted
from tests.test_parsing import CARD


class ParallelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {'LOCALAPPDATA': str(self.root)})
        env.start(); self.addCleanup(env.stop)
        self.book = InputWorkbook(self.root/'fictional.xlsx', 'local-only', 'Sheet1',
                                  pd.DataFrame({'NIC':['200000000001','200000000002','200000000003','200000000004']}))
        self.config = RunConfig(self.book.path, ('20',), (), '2025', 5, self.root)
        self.stop = threading.Event(); self.skips = [threading.Event(), threading.Event()]
        self.events = []; self.pause = threading.Event(); self.reason = ''
        self.active = self.peak = self.closed = self.created = 0
        self.lock = threading.Lock()

    def factory(self, worker):
        owner = self
        with self.lock: self.created += 1
        class Session:
            def fetch(self, nic, config, stop, skip, ready):
                with owner.lock:
                    owner.active += 1; owner.peak = max(owner.peak, owner.active)
                try:
                    if stop.wait(.03): raise core.StopRequested()
                    if skip.is_set(): skip.clear(); raise core.SkipCurrentRow('Selected worker skipped')
                    return CARD
                finally:
                    with owner.lock: owner.active -= 1
            def close(self):
                with owner.lock: owner.closed += 1
        return Session()

    def run_collection(self, factory=None):
        collect_parallel(self.config, self.book, CheckpointStore.open(self.book,self.config),
                         self.events.append,self.stop,self.skips,factory or self.factory,core,
                         self.pause,lambda:self.reason,2)

    def test_two_workers_overlap_and_single_writer_saves_each_row_once(self):
        self.run_collection()
        self.assertEqual((self.peak,self.closed),(2,2))
        self.assertEqual(self.events[-1].kind,'finished')
        store=CheckpointStore.open(self.book,self.config)
        try:
            self.assertEqual([r.position for r in store.results()],[0,1,2,3])
            self.assertTrue(all(r.values['subject:20']=='A' for r in store.results()))
        finally: store.close()

    def test_limit_pause_preserves_unsaved_rows_for_resume(self):
        def factory(worker):
            session=self.factory(worker)
            def paused(*args):
                self.reason='Session automatic-attempt limit reached.'
                self.pause.set()
                raise core.StopRequested()
            session.fetch=paused
            return session
        self.run_collection(factory)
        self.assertEqual(self.events[-1].kind,'stopped')
        self.assertEqual(self.events[-1].payload['reason'],'automatic_limit')
        store=CheckpointStore.open(self.book,self.config)
        try: self.assertEqual(store.pending_positions(),[0,1,2,3])
        finally: store.close()

    def test_stop_joins_workers_and_preserves_pending_rows(self):
        def factory(worker):
            session=self.factory(worker)
            def stopped(*args): self.stop.set(); raise core.StopRequested()
            session.fetch=stopped
            return session
        self.run_collection(factory)
        self.assertEqual(self.events[-1].kind,'stopped')
        self.assertEqual(self.events[-1].payload['processed'],0)
        self.assertGreater(self.created,0)
        self.assertEqual(self.closed,self.created)

    def test_skip_is_scoped_to_one_worker(self):
        def factory(worker):
            session=self.factory(worker)
            original=session.fetch
            first=True
            def fetch(*args):
                nonlocal first
                if worker==1 and first:
                    first=False; self.skips[0].set()
                return original(*args)
            session.fetch=fetch
            return session
        self.run_collection(factory)
        self.assertEqual(self.events[-1].payload['skipped'],1)
        self.assertEqual(self.events[-1].payload['completed'],3)

    def test_late_skip_for_finished_row_does_not_skip_next_student(self):
        def factory(worker):
            session=self.factory(worker)
            original=session.fetch
            def fetch(*args):
                result=original(*args)
                self.skips[worker-1].set()  # Arrives after this row's final controls check.
                return result
            session.fetch=fetch
            return session
        self.run_collection(factory)
        self.assertEqual(self.events[-1].payload['skipped'],0)
        self.assertEqual(self.events[-1].payload['completed'],4)

    def test_error_in_one_worker_stops_the_run_after_cleanup(self):
        def factory(worker):
            session=self.factory(worker)
            def fail(*args): raise RuntimeError('local worker failure')
            session.fetch=fail
            return session
        self.run_collection(factory)
        self.assertEqual(self.events[-1].kind,'fatal')
        self.assertGreater(self.created,0)
        self.assertEqual(self.closed,self.created)

    def test_shared_attempt_limit_allows_inflight_job_to_finish_and_keeps_other_rows_pending(self):
        budget=Budget(100,1)
        def factory(worker):
            session=self.factory(worker)
            def fetch(*args):
                try: budget.reserve()
                except LimitReached as exc:
                    self.reason=str(exc); self.pause.set()
                    raise core.StopRequested()
                time.sleep(.05)
                budget.settle('solve_one',12)
                return CARD
            session.fetch=fetch
            return session
        self.run_collection(factory)
        self.assertEqual((budget.attempts,budget.spent),(1,12))
        self.assertEqual(self.events[-1].payload['completed'],1)
        self.assertEqual(self.events[-1].payload['reason'],'automatic_limit')
        store=CheckpointStore.open(self.book,self.config)
        try: self.assertEqual(len(store.pending_positions()),3)
        finally: store.close()

    def test_exhausted_budget_precedes_previous_service_manual_fallback(self):
        adapter=PrototypeCollector(lambda data:None)
        adapter.disabled=True
        budget=Budget(10,1); budget.reserve()
        solver=Solver(None,budget,lambda data:None)
        class Base:
            def __init__(self): self.driver=SimpleNamespace(execute_cdp_cmd=lambda *args:None)
            def fetch(self,nic,config,stop,skip,ready): ready(); return CARD
        fake_core=SimpleNamespace(BrowserSession=Base,StopRequested=core.StopRequested,
                                  SkipCurrentRow=core.SkipCurrentRow)
        session=adapter.session_type(fake_core,solver,self.events.append)()
        manual=[]
        with self.assertRaises(core.StopRequested):
            session.fetch('200000000001',self.config,self.stop,self.skips[0],lambda:manual.append(True))
        self.assertFalse(manual)
        self.assertTrue(adapter.pause.is_set())

    def test_stop_cancels_two_pending_paid_jobs_before_workers_finish(self):
        barrier=threading.Barrier(2)
        budget=Budget(100,2)
        lock=threading.Lock()
        creates=[]; cancels=[]
        owner=self
        class Client:
            def balance(self): return {'balance':100,'plan_remaining':0}
            def create(self,*args,**kwargs):
                with lock:
                    job=f'solve_pending{len(creates)+1}'; creates.append(job)
                barrier.wait(timeout=2)
                owner.stop.set()
                return {'id':job,'status':'pending'}
            def cancel(self,job):
                with lock: cancels.append(job)
                return {'id':job,'status':'cancelled','credits_charged':0}
        client=Client()
        def factory(worker):
            session=self.factory(worker)
            solver=Solver(client,budget,lambda data:None)
            def fetch(nic,config,stop,skip,ready):
                try: solver.solve({'sitekey':'00000000-0000-0000-0000-000000000001'},stop,skip)
                except Interrupted: raise core.StopRequested()
                return CARD
            session.fetch=fetch
            return session
        self.run_collection(factory)
        self.assertEqual(sorted(cancels),sorted(creates))
        self.assertEqual(len(cancels),2)
        self.assertEqual((budget.attempts,budget.spent),(2,0))
        self.assertEqual(self.closed,2)
        self.assertEqual(self.events[-1].kind,'stopped')
        self.assertEqual(self.events[-1].payload['processed'],0)

    def test_stop_while_waiting_for_browser_startup_lock_does_not_open_browser(self):
        adapter=PrototypeCollector(lambda data:None); adapter.run_stop=self.stop
        opened=[]; interrupted=[]
        class Base:
            def __init__(self): opened.append(True)
        fake_core=SimpleNamespace(BrowserSession=Base,StopRequested=core.StopRequested)
        session_type=adapter.session_type(fake_core,None,self.events.append)
        def start():
            try: session_type()
            except core.StopRequested: interrupted.append(True)
        DRIVER_STARTUP_LOCK.acquire()
        try:
            thread=threading.Thread(target=start); thread.start()
            self.stop.set(); thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        finally: DRIVER_STARTUP_LOCK.release()
        self.assertEqual(interrupted,[True])
        self.assertFalse(opened)

    def test_stop_during_session_startup_is_not_reported_as_fatal(self):
        def factory(worker): self.stop.set(); raise core.StopRequested()
        self.run_collection(factory)
        self.assertEqual(self.events[-1].kind,'stopped')
        self.assertEqual(self.events[-1].payload['processed'],0)
