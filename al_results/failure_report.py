"""Keep the first observed failure for each input row in a single local batch report."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
from threading import Lock
from uuid import uuid4

from .checkpoints import app_data_dir
from .models import WorkerEvent


_current = ContextVar('failure_report_row', default=None)
_operations = {'balance check', 'solve creation', 'solve status check', 'cancellation',
               'verification', 'result wait', 'billing'}
_outcomes = {'timeout', 'dns_error', 'tls_error', 'connection_reset', 'connection_refused',
             'incomplete_response', 'network_error', 'http_error', 'invalid_json', 'invalid_shape',
             'response_read_limit', 'invalid_response', 'solve_timeout', 'solve_failed', 'expired',
             'failed', 'cancelled', 'result_timeout', 'billing_unconfirmed', 'browser_error',
             'unauthorized', 'rate_limited', 'insufficient_credits', 'key_credit_limit_exceeded',
             'validation_error', 'widget_unavailable', 'token_not_applied', 'submit_unavailable'}


class _BatchReport:
    def __init__(self, emit):
        self.emit = emit
        self.path = app_data_dir() / 'diagnostics' / f'failure-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.jsonl'
        self.lock = Lock()
        self.seen = set()

    def observe(self, event):
        # Both collectors emit current on the thread that will process that row.
        if event.kind == 'current':
            _current.set((self, event.payload['position'] + 1, event.payload.get('worker', 1)))
        self.emit(event)

    def write(self, row, worker, operation, outcome, **numbers):
        with self.lock:
            if row in self.seen:
                return
            self.seen.add(row)
            operation = operation if operation in _operations else 'unknown'
            outcome = outcome if outcome in _outcomes else 'unclassified'
            record = dict(utc=datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
                          row=row, worker=worker, operation=operation, outcome=outcome)
            record.update({key: value for key, value in numbers.items() if type(value) is int})
            summary = f'Worker {worker}, row {row}: {operation} — {outcome}'
            if 'http_status' in record:
                summary += f" (HTTP {record['http_status']})"
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open('a', encoding='utf-8') as target:
                    target.write(json.dumps(record) + '\n')
                summary += f'. Failure report: {self.path}'
            except OSError:
                summary += '. The diagnostic file could not be saved.'
            self.emit(WorkerEvent('log', {'text': summary}))


@contextmanager
def capture_failures(emit):
    report = _BatchReport(emit)
    token = _current.set(None)
    try:
        yield report.observe
    finally:
        _current.reset(token)


def record_failure(operation, outcome, *, elapsed_ms=None, http_status=None, wait_limit_s=None):
    current = _current.get()
    if current is not None:
        report, row, worker = current
        report.write(row, worker, operation, outcome, elapsed_ms=elapsed_ms,
                     http_status=http_status, wait_limit_s=wait_limit_s)
