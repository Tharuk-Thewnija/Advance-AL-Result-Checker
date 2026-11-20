"""Local Chrome scenarios; synthetic NICs, fake tokens, no provider/site calls."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import quote

import pandas as pd
from selenium.common.exceptions import TimeoutException

from al_results import collector as production
from al_results.checkpoints import CheckpointStore
from al_results.excel_io import load_workbook
from al_results.models import RunConfig
from al_results.nonecap.budget import Budget
from al_results.nonecap.collector import AutomaticCollector, private_core
from al_results.nonecap.solver import Solver
from tests.nonecap.test_browser import HTML, LocalClient
from .collector import DiagnosticCollector, Recorder


class Scenarios(unittest.TestCase):
    def run_scenario(self, diagnostic, delay=False, workers=1):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOCALAPPDATA': directory}):
            root = Path(directory)
            source = root/'fictional.xlsx'
            pd.DataFrame({'NIC': [f'20000000000{i}' for i in range(1, 5)]}).to_excel(source, index=False)
            before = source.read_bytes()
            book = load_workbook(source)
            config = RunConfig(source, ('20',), ('Candidate Name',), '2025', 1, root/'exports')
            recorder = Recorder(root/'report.jsonl')
            adapter = DiagnosticCollector(lambda data: None, recorder, cutoff=.2, observation=.8) if diagnostic else AutomaticCollector(lambda data: None)
            core = adapter.diagnostic_core() if diagnostic else private_core()
            if not diagnostic:
                # Accelerate the baseline's long waits, preserving its control flow.
                ordinary = core.wait_for_results_or_skip
                def wait(driver, timeout, stop, skip):
                    return ordinary(driver, .2, stop, skip)
                core.wait_for_results_or_skip = wait
            action = "setTimeout(()=>document.getElementById('result').style.display='block',350)" if delay else "document.body.insertAdjacentHTML('beforeend','<div role=alert>CAPTCHA verification failed: private-student-name secret-token 200000000002</div>')"
            page = HTML.replace("if(window.verified) document.getElementById('result').style.display='block'",
                                "if(document.querySelector('input').value.endsWith('2')){" + action + "}else{document.getElementById('result').style.display='block'}")
            core.RESULTS_PAGE_URL = 'data:text/html;charset=utf-8,' + quote(page)
            core.create_driver = lambda: production.create_driver(headless=True)
            adapter.core_factory = lambda: core
            adapter.workers = workers
            client = LocalClient()
            adapter.solver = Solver(client, Budget(2000, 200), lambda data: None)
            events = []
            adapter(config, book, CheckpointStore.open(book, config), events.append, threading.Event(), threading.Event())
            terminal = next(e for e in reversed(events) if e.kind in ('finished', 'stopped', 'fatal'))
            store = CheckpointStore.open(book, config)
            try:
                statuses = [row.status for row in store.results()]
                pending = len(store.pending_positions())
            finally:
                store.close()
            self.assertEqual(source.read_bytes(), before)
            self.assertLessEqual(client.creates, 4)
            if diagnostic:
                raw = recorder.path.read_text(encoding='utf-8')
                for secret in ('private-student-name', 'secret-token', 'local-token', '200000000002', 'nc_live_'):
                    self.assertNotIn(secret, raw)
                records = [json.loads(line) for line in raw.splitlines()]
                self.assertTrue(any(r.get('row') == 2 for r in records))
                if delay:
                    self.assertEqual(statuses, ['Completed']*4)
                    self.assertTrue(any(r['stage']=='late_result' for r in records))
                    self.assertEqual(client.creates, 4)  # No second paid solve for the delayed row.
                else:
                    self.assertEqual(terminal.kind, 'stopped', terminal)
                    self.assertEqual(terminal.payload['reason'], 'submission_timeout')
                    self.assertNotIn('Error', statuses)
                    self.assertGreater(pending, 0)
                    self.assertTrue(any(r.get('captcha_message') for r in records))
                    self.assertTrue(any(r['stage']=='original_cutoff' for r in records))
                    self.assertTrue(any(r.get('reason')=='result_timeout' for r in records))
                    self.assertFalse(any('MANUAL ACTION REQUIRED' in e.payload.get('text','') for e in events))
            else:
                self.assertFalse(adapter.disabled)
                self.assertEqual(statuses, ['Completed'])
                self.assertEqual(terminal.payload['reason'], 'submission_timeout')
                self.assertEqual(client.creates, 2)  # Remaining rows never reach the API.
                self.assertEqual(pending, 3)

    def test_production_submission_timeout_keeps_pending_rows(self):
        self.run_scenario(False)

    def test_diagnostics_pause_and_keep_pending_rows(self):
        self.run_scenario(True)

    def test_delayed_results_without_another_solve(self):
        self.run_scenario(True, delay=True)

    def test_parallel_failure_keeps_unfinished_rows_pending(self):
        self.run_scenario(True, workers=2)

    def test_recorder_drops_unknown_and_string_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = Recorder(Path(directory)/'report.jsonl')
            recorder.write('waiting', token='secret', http_2xx='secret', pending_requests=2)
            recorder.write('paused', reason='secret-student-name')
            record, pause = [json.loads(line) for line in recorder.path.read_text().splitlines()]
            self.assertNotIn('token', record)
            self.assertNotIn('http_2xx', record)
            self.assertEqual(record['pending_requests'], 2)
            self.assertNotIn('reason', pause)

    def test_network_probe_distinguishes_status_reset_abort_and_error(self):
        driver = production.create_driver(headless=True)
        try:
            driver.get('data:text/html,<title>Local diagnostic probe</title>')
            # Fake XHR exercises event ordering without any website/API requests.
            driver.execute_script('''
                window.XMLHttpRequest = class extends EventTarget {
                    status = 0; readyState = 0;
                    send() {
                        if (this.kind === 'success') {
                            this.status = 200; this.readyState = 4;
                            this.dispatchEvent(new Event('readystatechange'));
                            this.status = 0; // Model client cleanup before loadend.
                            this.dispatchEvent(new Event('load'));
                        } else {
                            this.dispatchEvent(new Event(this.kind));
                        }
                        this.dispatchEvent(new Event('loadend'));
                    }
                };
            ''')
            driver.execute_script((Path(__file__).parent/'network.js').read_text())
            state = driver.execute_script('''
                for (const kind of ['success','abort','error','timeout']) {
                    const xhr = new XMLHttpRequest(); xhr.kind=kind; xhr.send();
                }
                return window.__submissionDiagnostic;
            ''')
            self.assertEqual(state['started'], 4)
            self.assertEqual(state['finished'], 4)
            self.assertEqual(state['http_2xx'], 1)
            self.assertEqual(state['network_errors'], 1)
            self.assertEqual(state['aborted_requests'], 1)
            self.assertEqual(state['request_timeouts'], 1)
        finally:
            driver.quit()


if __name__ == '__main__':
    unittest.main()
