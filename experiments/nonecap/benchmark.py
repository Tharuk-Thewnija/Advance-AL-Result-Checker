"""Repeatable worker comparison: synthetic records and simulated API latency only."""
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import threading
import time

import pandas as pd

from al_results.checkpoints import CheckpointStore
from al_results.models import InputWorkbook, RunConfig
from .budget import Budget
from .collector import PrototypeCollector, MAX_WORKERS
from .solver import Solver, Interrupted

CARD = 'Name\nFICTIONAL BENCHMARK STUDENT\nINFORMATION & COMMUNICATION TECHNOLOGY\nA'
WIDGET = {'sitekey':'00000000-0000-0000-0000-000000000001'}


class SimulatedClient:
    def __init__(self, delay):
        self.delay, self.counter, self.active, self.peak = delay,0,0,0
        self.lock = threading.Lock()

    def balance(self): return {'balance':100000,'plan_remaining':0}

    def create(self,*args,**kwargs):
        with self.lock:
            self.counter += 1; number = self.counter
            self.active += 1; self.peak = max(self.peak,self.active)
        try:
            time.sleep(self.delay)
            return dict(id=f'solve_mock{number}',status='solved',token='local-token',credits_charged=12)
        finally:
            with self.lock: self.active -= 1


def run(report, *, rows=20, delay=.25):
    comparisons, outputs = [], []
    original = os.environ.get('LOCALAPPDATA')
    try:
        with tempfile.TemporaryDirectory(prefix='nonecap-workers-') as directory:
            root = Path(directory)
            frame = pd.DataFrame({'NIC':[str(200000000001+i) for i in range(rows)]})
            book = InputWorkbook(root/'fictional.xlsx','mock-only','Sheet1',frame)
            config = RunConfig(book.path,('20',),('Candidate Name',),'2025',180,root)
            for workers in range(1,MAX_WORKERS+1):
                os.environ['LOCALAPPDATA'] = str(root/f'workers-{workers}')
                client = SimulatedClient(delay)
                adapter = PrototypeCollector(lambda data:None)
                adapter.solver = Solver(client,Budget(100000,1000),lambda data:None)
                adapter.workers = workers
                def session_type(core,solver,emit,label=''):
                    class Session:
                        def fetch(self,nic,config,stop,skip,ready):
                            try: solver.solve(WIDGET,stop,skip)
                            except Interrupted as exc:
                                if exc.kind=='skip': raise core.SkipCurrentRow()
                                raise core.StopRequested()
                            return CARD
                        def close(self): pass
                    return Session
                adapter.session_type = session_type
                events = []
                metrics = adapter(config,book,CheckpointStore.open(book,config),events.append,
                                  threading.Event(),threading.Event())
                terminal = next(e for e in reversed(events) if e.kind in ('finished','stopped','fatal'))
                if terminal.kind!='finished' or terminal.payload['completed']!=rows:
                    raise RuntimeError('Offline comparison did not complete every synthetic row.')
                store = CheckpointStore.open(book,config)
                try: results=store.results()
                finally: store.close()
                outputs.append([(r.position,r.status,r.values) for r in results])
                comparisons.append(dict(metrics,peak_simultaneous_solves=client.peak,
                                        simulated_credits=adapter.solver.budget.snapshot()['spent']))
    finally:
        if original is None: os.environ.pop('LOCALAPPDATA',None)
        else: os.environ['LOCALAPPDATA']=original
    if any(output!=outputs[0] for output in outputs[1:]): raise RuntimeError('Worker comparison produced different saved results.')
    for metrics in comparisons:
        metrics['speedup_vs_single']=comparisons[0]['elapsed_seconds']/metrics['elapsed_seconds']
    result = dict(kind='OFFLINE SIMULATION; no browser or provider requests',created_at=datetime.now().isoformat(),
                  rows=rows,simulated_solve_delay_seconds=delay,results_identical=True,
                  speedup=comparisons[-1]['speedup_vs_single'],runs=comparisons)
    report = Path(report); report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
    print(f'Offline comparison saved to {report}')
    return result
