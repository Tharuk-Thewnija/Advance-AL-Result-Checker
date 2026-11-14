"""Real Chrome and Excel/SQLite; all content is local, API entirely simulated."""
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import quote

import pandas as pd

from al_results import collector as production
from al_results.checkpoints import CheckpointStore
from al_results.excel_io import load_workbook, export_results
from al_results.models import RunConfig
from experiments.nonecap.budget import Budget
from experiments.nonecap.client import ServiceError
from experiments.nonecap.collector import PrototypeCollector, private_core
from experiments.nonecap.solver import Solver
from tests.test_parsing import CARD


HTML = '''<!doctype html><meta charset="utf-8">
<select class="form-control flex-grow-1 h5"><option value="al">G.C.E.(A/L) EXAMINATION</option></select>
<select class="form-control flex-grow-1 h5"><option>2025</option></select>
<select class="custom-option form-control"><option value="nic">NIC</option></select>
<input class="form-control text-center"><div id="widget" style="width:100px;height:50px">Local widget</div>
<textarea name="h-captcha-response" hidden></textarea>
<script>
window.hcaptcha = {render(container, options) {return 0;}};
hcaptcha.render('widget', {sitekey:'00000000-0000-0000-0000-000000000001',
    rqdata:'local-rqdata', callback(token, responseKey) {window.verified = token === 'local-token';}});
</script>
<button type="submit" onclick="if(window.verified) document.getElementById('result').style.display='block'">Submit</button>
<div id="result" class="card border-info watermark" style="display:none;white-space:pre-line">CARD</div>'''.replace('CARD', CARD)


class LocalClient:
    def __init__(self): self.creates = 0
    def balance(self): return dict(balance=100, plan_remaining=0)
    def create(self, sitekey, **kwargs):
        self.creates += 1
        assert kwargs['rqdata'] == 'local-rqdata'
        return dict(id=f'solve_local{self.creates}', status='solved', token='local-token', credits_charged=2)


class BrowserTests(unittest.TestCase):
    def run_local(self, *, failure=False):
        original_session = production.BrowserSession
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOCALAPPDATA': directory}):
            root = Path(directory)
            path = root / 'fictional.xlsx'
            pd.DataFrame({'NIC': ['900000000V', '200000000001']}).to_excel(path, index=False)
            before = path.read_bytes()
            config = RunConfig(path, ('20',), ('Candidate Name',), '2025', 5, root / 'out')
            book = load_workbook(path)
            core = private_core()
            core.RESULTS_PAGE_URL = 'data:text/html;charset=utf-8,' + quote(HTML)
            driver = production.create_driver(headless=True)
            core.create_driver = lambda: driver
            gets = []
            original_get = driver.get
            def get(url): gets.append(url); original_get(url)
            driver.get = get
            adapter = PrototypeCollector(lambda data: None)
            client = LocalClient()
            budget = Budget(3, 3)
            adapter.solver = Solver(client, budget, lambda data: None)
            manual = []
            if failure:
                def reject(*a, **kw): raise ServiceError('solve_failed')
                client.create = reject
                original_wait = core.wait_for_results_or_skip
                def user_completes(current, *args):
                    manual.append(True)
                    current.execute_script("window.verified=true;document.querySelector('button').click()")
                    return original_wait(current, *args)
                core.wait_for_results_or_skip = user_completes
            events = []
            try:
                with patch('experiments.nonecap.collector.private_core', return_value=core):
                    adapter(config, book, CheckpointStore.open(book, config), events.append,
                            threading.Event(), threading.Event())
                self.assertEqual(events[-1].kind, 'finished', events[-1])
                self.assertEqual(events[-1].payload['completed'], 2)
                if not failure:
                    self.assertFalse(adapter.disabled, events)
                self.assertIs(production.BrowserSession, original_session)
                self.assertEqual(len(gets), 2)  # No reload on fallback.
                store = CheckpointStore.open(book, config)
                try:
                    output = export_results(book, config, store.results())
                finally: store.close()
                self.assertEqual(pd.read_excel(output)['Information & Communication Technology Result'].tolist(), ['A', 'A'])
                self.assertEqual(path.read_bytes(), before)
                self.assertNotIn('local-token', str(events))
                if failure:
                    self.assertTrue(adapter.disabled)
                    self.assertEqual(len(manual), 2)
                else:
                    self.assertEqual((client.creates, budget.spent), (2, 4))
            finally:
                try: driver.quit()
                except Exception: pass

    def test_automatic_callback_and_excel_export_using_local_page(self): self.run_local()
    def test_automatic_failure_falls_back_without_reloading_or_skipping(self): self.run_local(failure=True)
