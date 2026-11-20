"""Opt-in diagnostic collector. No paid retry, raw page capture or production edits."""
import json
from pathlib import Path
import threading
import time

from selenium.common.exceptions import TimeoutException, WebDriverException

from al_results.models import WorkerEvent
from al_results.nonecap.collector import AutomaticCollector, private_core, script
from al_results.nonecap.client import ServiceError
from .transport import KINDS, OPERATIONS, PROVIDER_CODES

HERE = Path(__file__).parent
FIELDS = frozenset('result_visible captcha_message no_result_message busy_message alert_visible '
                   'response_present site_notice_latched site_notice_visible pending_requests network_errors aborted_requests request_timeouts '
                   'opaque_responses unknown_status http_2xx http_3xx http_4xx http_5xx'.split())
REASONS = frozenset(('result_timeout', 'solve_timeout', 'solve_failed', 'widget_unavailable',
                     'token_not_applied', 'submit_unavailable', 'insufficient_credits', 'network_error',
                     'unauthorized', 'rate_limited', 'other_automatic_failure', 'automatic_limit', 'billing_unconfirmed'))
STAGES = frozenset(('row_started', 'token_applied', 'submit', 'waiting', 'original_cutoff',
                    'late_result', 'result', 'observation_timeout', 'paused', 'snapshot_unavailable', 'api_request'))


class Recorder:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.started = time.monotonic()
        self.context = threading.local()

    def write(self, stage, **values):
        if stage not in STAGES:
            raise ValueError('Unknown diagnostic stage')
        record = dict(stage=stage, seconds=round(time.monotonic()-self.started, 3),
                      row=getattr(self.context, 'row', 0), worker=getattr(self.context, 'worker', 1))
        if type(values.get('reason')) is str and values['reason'] in REASONS:
            record['reason'] = values['reason']
        for key, allowed in (('operation',OPERATIONS), ('outcome',KINDS), ('provider_code',PROVIDER_CODES)):
            if type(values.get(key)) is str and values[key] in allowed:
                record[key] = values[key]
        for key, value in values.items():
            # An explicit schema prevents accidental logging of secrets/page text.
            if key in FIELDS | {'elapsed', 'callback', 'applied', 'already_verified', 'http_status', 'bytes_received'} and type(value) in (int, float, bool):
                record[key] = value
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('a', encoding='utf-8') as target:
                target.write(json.dumps(record) + '\n')


class DiagnosticCollector(AutomaticCollector):
    def __init__(self, notify, recorder, *, cutoff=20, observation=60):
        super().__init__(notify)
        if not 0 < cutoff < observation <= 120:
            raise ValueError('Expected 0 < cutoff < observation <= 120 seconds')
        self.recorder = recorder
        self.cutoff, self.observation = cutoff, observation
        self.core_factory = self.diagnostic_core

    def pause_collection(self, reason, kind, emit):
        code = {'service_connection':'network_error', 'submission_timeout':'result_timeout', 'automatic_timeout':'solve_timeout',
                'automatic_limit':'automatic_limit', 'billing_unconfirmed':'billing_unconfirmed'}.get(kind, 'other_automatic_failure')
        self.recorder.write('paused', reason=code)
        super().pause_collection(reason, kind, emit)

    def diagnostic_core(self):
        core = private_core()
        self.core = core
        ordinary_wait = core.wait_for_results_or_skip

        def capture(driver, stage, elapsed):
            try:
                state = driver.execute_script((HERE/'snapshot.js').read_text(encoding='utf-8'))
                self.recorder.write(stage, elapsed=round(elapsed, 3), **state)
            except WebDriverException:
                self.recorder.write('snapshot_unavailable', elapsed=round(elapsed, 3))

        def wait(driver, timeout, stop, skip):
            # Manual mode retains its ordinary behavior. Only automatic submission
            # passes the collector's shortened (<=20 second) timeout here.
            if self.solver is None:
                return ordinary_wait(driver, timeout, stop, skip)
            started = time.monotonic()
            late = False
            next_sample = 0
            while True:
                core.check_controls(stop, skip)
                elapsed = time.monotonic()-started
                if elapsed >= self.cutoff and not late:
                    late = True
                    capture(driver, 'original_cutoff', elapsed)
                if elapsed >= next_sample:
                    capture(driver, 'waiting', elapsed)
                    next_sample = elapsed + 2
                try:
                    text = ordinary_wait(driver, min(.2, self.observation-elapsed), stop, skip)
                    capture(driver, 'late_result' if late else 'result', time.monotonic()-started)
                    return text
                except TimeoutException:
                    if time.monotonic()-started >= self.observation:
                        capture(driver, 'observation_timeout', time.monotonic()-started)
                        raise
        core.wait_for_results_or_skip = wait
        return core

    def fallback(self, emit, reason):
        # In this experiment one failure pauses instead of starting a chain of
        # manual timeouts. Already-admitted workers can finish their current row.
        with self.pause_lock:
            self.pause_reason = 'Diagnostic pause: automatic submission could not finish. Review the diagnostic report.'
            self.pause_kind = 'diagnostic_failure'
            self.pause.set()
        code = 'other_automatic_failure'
        if reason == 'The site did not return results after automatic submission.':
            code = 'result_timeout'
        else:
            for candidate in REASONS - {'result_timeout', 'other_automatic_failure', 'automatic_limit', 'billing_unconfirmed'}:
                if reason == str(ServiceError(candidate)):
                    code = candidate
                    break
        self.recorder.write('paused', reason=code)
        emit(WorkerEvent('log', {'text': reason + ' Diagnostic collection paused; unfinished rows stay pending.'}))
        raise self.core.StopRequested()

    def session_type(self, core, solver, emit, label=''):
        base = super().session_type(core, solver, emit, label)
        recorder = self.recorder

        class Session(base):
            def __init__(self):
                recorder.context.worker = int(label.rsplit(' ', 1)[-1]) if label else 1
                super().__init__()
                self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                    'source': (HERE/'network.js').read_text(encoding='utf-8')})
                execute = self.driver.execute_script
                apply_source, submit_source = script('apply_token.js'), script('submit.js')

                def tracked(source, *args):
                    result = execute(source, *args)
                    if source == apply_source:
                        recorder.write('token_applied', **(result or {}))
                    elif source == submit_source:
                        recorder.write('submit', applied=bool(result))
                    return result
                self.driver.execute_script = tracked

            def fetch(self, *args, **kwargs):
                recorder.write('row_started')
                return super().fetch(*args, **kwargs)
        return Session

    def __call__(self, config, workbook, store, emit, stop, skip):
        def observed(event):
            if event.kind == 'current':
                self.recorder.context.row = event.payload['position'] + 1
            emit(event)
        return super().__call__(config, workbook, store, observed, stop, skip)
