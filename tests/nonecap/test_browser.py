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
from al_results.nonecap.budget import Budget
from al_results.nonecap.client import ServiceError
from al_results.nonecap.collector import PrototypeCollector, private_core
from al_results.nonecap.solver import Solver
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
    def test_site_notice_skips_and_missing_ict_stays_blank_with_one_and_two_workers(self, transient=False):
        page = HTML + '''<script>
        document.querySelector('button').onclick = function() {
            const nic = document.querySelector('input').value;
            if (nic.endsWith('1')) {
                document.body.insertAdjacentHTML('beforeend', '<div toast-component="" class="toast-error toast ng-trigger ng-trigger-flyInOut" style="display: inherit; opacity: 1;"><button aria-label="Close" class="toast-close-button ng-tns-c14-2 ng-star-inserted"><span class="ng-tns-c14-2" aria-hidden="true">×</span></button><div aria-live="polite" role="alertdialog" class="toast-message ng-star-inserted" aria-label=" Sorry for the inconvenience, Please try again">  Sorry for the inconvenience, Please try again </div><div class="ng-tns-c14-2 ng-star-inserted"><div class="toast-progress" style="width: 0%;"></div></div></div>');
            } else {
                const card = document.getElementById('result');
                if (nic.endsWith('2')) card.textContent = 'Name\\nSAMPLE STUDENT\\nSubject Stream\\nCOMMERCE\\nBUSINESS STUDIES\\nA';
                card.style.display = 'block';
            }
        };
        </script>'''
        if transient:
            # Angular toasts can disappear before the first WebDriver poll.
            page = page.replace('Sorry for the inconvenience,', 'Sorry&nbsp;for the inconvenience,')
            page = page.replace('} else {', "setTimeout(()=>document.querySelector('.toast-error').remove(), 50); } else {")
        for workers in (1, 2):
            with self.subTest(workers=workers), tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOCALAPPDATA': directory}):
                root = Path(directory)
                path = root/'fictional.xlsx'
                pd.DataFrame({'NIC':['200000000001','200000000002','200000000003']}).to_excel(path, index=False)
                book = load_workbook(path)
                config = RunConfig(path, ('20',), ('Candidate Name',), '2025', 3, root/'out')
                core = private_core()
                if transient:
                    ordinary_wait = core.wait_for_results_or_skip
                    def late_poll(driver, timeout, stop, skip):
                        stop.wait(.3)
                        return ordinary_wait(driver, timeout, stop, skip)
                    core.wait_for_results_or_skip = late_poll
                core.RESULTS_PAGE_URL = 'data:text/html;charset=utf-8,'+quote(page)
                core.create_driver = lambda: production.create_driver(headless=True)
                adapter = PrototypeCollector(lambda data: None)
                adapter.workers = workers
                adapter.core_factory = lambda: core
                client = LocalClient()
                adapter.solver = Solver(client, Budget(100, 10), lambda data: None)
                events = []
                adapter(config, book, CheckpointStore.open(book, config), events.append, threading.Event(), threading.Event())
                self.assertEqual(events[-1].kind, 'finished', events[-1])
                self.assertFalse(adapter.disabled)
                self.assertEqual(client.creates, 3)
                store = CheckpointStore.open(book, config)
                try:
                    rows = store.results()
                    self.assertEqual([r.status for r in rows], ['Skipped','Completed','Completed'])
                    self.assertIn('Site returned', rows[0].note)
                    self.assertIsNone(rows[1].values['subject:20'])
                    self.assertEqual(rows[1].note, 'Selected subject result not present: 20')
                    self.assertEqual(rows[2].values['subject:20'], 'A')
                    output = export_results(book, config, rows)
                finally:
                    store.close()
                exported = pd.read_excel(output)
                grades = exported['Information & Communication Technology Result']
                self.assertTrue(pd.isna(grades[0]) and pd.isna(grades[1]))
                self.assertEqual(grades[2], 'A')

    def test_transient_site_toast_with_nonbreaking_spaces_is_not_lost(self):
        self.test_site_notice_skips_and_missing_ict_stays_blank_with_one_and_two_workers(transient=True)

    def test_notice_observer_does_not_latch_hidden_template(self):
        driver = production.create_driver(headless=True)
        try:
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source':production.SITE_NOTICE_SCRIPT})
            page = '<div class="toast-message" style="display:none">Sorry for the inconvenience, Please try again</div><div class="card border-info watermark">Valid result</div>'
            driver.get('data:text/html;charset=utf-8,'+quote(page))
            self.assertEqual(private_core().wait_for_results_or_skip(driver, 1, threading.Event(), threading.Event()), 'Valid result')
            self.assertIs(driver.execute_script('return window.__alSiteNoticeSeen;'), False)
        finally:
            driver.quit()

    def run_local(self, *, failure=False, workers=1):
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
            drivers = []
            gets = []
            def create_driver():
                driver=production.create_driver(headless=True)
                drivers.append(driver)
                original_get=driver.get
                def get(url): gets.append(url); original_get(url)
                driver.get=get
                return driver
            core.create_driver = create_driver
            adapter = PrototypeCollector(lambda data: None)
            adapter.workers=workers
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
                with patch('al_results.nonecap.collector.private_core', return_value=core):
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
                    logs = '\n'.join(event.payload['text'] for event in events if event.kind == 'log')
                    self.assertIn('NoneCAP token received. Reported charge: 2 credits.', logs)
                    if workers==1: self.assertIn('Session: 2/3 credits; attempts: 1/3.', logs)
                    self.assertIn('Token delivered through the site CAPTCHA callback.', logs)
                    self.assertIn('Automatic form submission triggered.', logs)
                    self.assertIn('Results received after automatic submission.', logs)
            finally:
                for driver in drivers:
                    try: driver.quit()
                    except Exception: pass

    def test_automatic_callback_and_excel_export_using_local_page(self): self.run_local()
    def test_automatic_failure_falls_back_without_reloading_or_skipping(self): self.run_local(failure=True)
    def test_two_real_chrome_workers_keep_tokens_and_excel_results_separate(self): self.run_local(workers=2)
