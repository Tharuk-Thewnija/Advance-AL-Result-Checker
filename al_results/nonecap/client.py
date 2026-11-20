"""Small NoneCAP HTTPS client. No key in URLs, redirects, logs or error messages."""
import json
from http.client import HTTPException, IncompleteRead
import re
import socket
import ssl
import time
import urllib.error
import urllib.request
from uuid import UUID

from al_results.failure_report import record_failure

BASE = 'https://api.nonecap.com'
FORM_URL = 'https://www.doenets.lk/examresults'
MESSAGES = {
    'unauthorized': 'NoneCAP rejected the API key.',
    'insufficient_credits': 'NoneCAP credits or daily allowance are exhausted.',
    'key_credit_limit_exceeded': 'The NoneCAP key reached its provider-side credit cap.',
    'rate_limited': 'NoneCAP rate limit reached.',
    'validation_error': 'NoneCAP rejected the challenge details.',
    'widget_unavailable': 'No supported hCaptcha widget was found. No solve was requested.',
    'solve_failed': 'NoneCAP did not return a usable token.',
    'solve_timeout': 'The automatic solve timed out; cancellation was requested.',
    'token_not_applied': 'The page could not accept the automatic token.',
    'submit_unavailable': 'No unambiguous submit action was found.',
    'network_error': 'NoneCAP could not be reached or its response could not be read.',
}


class ServiceError(Exception):
    def __init__(self, code, *, uncertain=False, operation=None, outcome=None, http_status=None):
        self.operation = operation
        self.outcome = outcome
        self.http_status = http_status
        self.code = code if isinstance(code, str) else 'service_error'
        self.uncertain = uncertain
        super().__init__(MESSAGES.get(self.code, 'NoneCAP is unavailable or returned an unexpected response.'))


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def network_outcome(error):
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    for error_type, name in ((TimeoutError, 'timeout'), (socket.gaierror, 'dns_error'),
                             (ssl.SSLError, 'tls_error'), (ConnectionResetError, 'connection_reset'),
                             (ConnectionRefusedError, 'connection_refused'), (IncompleteRead, 'incomplete_response')):
        if isinstance(reason, error_type):
            return name
    return 'network_error'


class Client:
    def __init__(self, key, *, transport=None):
        key = key.strip()
        if not re.fullmatch(r'nc_live_[A-Za-z0-9_-]{32}', key):
            raise ServiceError('unauthorized')
        self._key = key
        self._transport = transport or self._http

    def _http(self, method, path, headers, body):
        request = urllib.request.Request(BASE + path, method=method, headers=headers,
                                        data=json.dumps(body).encode() if body is not None else None)
        status = None
        try:
            with urllib.request.build_opener(NoRedirects()).open(request, timeout=5) as response:
                status = response.status
                raw = response.read(1048577)
                try:
                    data = json.loads(raw)
                except ValueError:
                    outcome = 'response_read_limit' if len(raw) == 1048577 else 'invalid_json'
                    raise ServiceError('network_error', uncertain=method == 'POST', outcome=outcome, http_status=status) from None
                if not isinstance(data, dict):
                    raise ServiceError('network_error', uncertain=method == 'POST', outcome='invalid_shape', http_status=status)
                return data
        except urllib.error.HTTPError as exc:
            code = 'service_error'
            try:
                code = json.loads(exc.read(65536)).get('error', {}).get('code', code)
            except (ValueError, AttributeError, OSError, HTTPException):
                pass
            finally:
                exc.close()
            # Never surface the service's raw message: it could echo a key/token.
            raise ServiceError(code, outcome='http_error', http_status=exc.code, uncertain=method == 'POST' and exc.code not in
                               (400, 401, 402, 403, 404, 413, 415, 422, 429)) from None
        except (OSError, ValueError, HTTPException) as exc:
            raise ServiceError('network_error', uncertain=method == 'POST',
                               outcome=network_outcome(exc), http_status=status) from None

    def _request(self, method, path, body=None, *, operation):
        started = time.monotonic()
        try:
            return self._transport(method, path, {'Authorization': 'Bearer ' + self._key,
                                                  'Content-Type': 'application/json'}, body)
        except ServiceError as exc:
            exc.operation = operation
            record_failure(operation, exc.outcome or exc.code, http_status=exc.http_status,
                           elapsed_ms=round((time.monotonic() - started) * 1000))
            raise

    def balance(self):
        data = self._request('GET', '/v1/me', operation='balance check')
        value = data.get('credits_balance')
        if type(value) is not int or value < 0: raise ServiceError('invalid_response', operation='balance check')
        plan = data.get('plan')
        remaining = plan.get('remaining_today', 0) if isinstance(plan, dict) else 0
        return {'balance': value, 'plan_remaining': remaining if type(remaining) is int and remaining >= 0 else 0}

    def create(self, sitekey, *, rqdata='', enterprise=False, user_agent=''):
        try:
            UUID(sitekey)
        except (ValueError, TypeError, AttributeError):
            raise ServiceError('validation_error') from None
        body = dict(type='hcaptcha_enterprise' if rqdata or enterprise else 'hcaptcha', sitekey=sitekey, url=FORM_URL)
        if rqdata: body['rqdata'] = rqdata
        if user_agent: body['user_agent'] = user_agent
        return self._request('POST', '/v1/solves', body, operation='solve creation')

    def _job_path(self, job):
        if not isinstance(job, str) or not re.fullmatch(r'solve_[A-Za-z0-9_-]{1,96}', job):
            raise ServiceError('invalid_response', uncertain=True)
        return '/v1/solves/' + job

    def get(self, job):
        return self._request('GET', self._job_path(job), operation='solve status check')

    def cancel(self, job):
        return self._request('DELETE', self._job_path(job), operation='cancellation')
