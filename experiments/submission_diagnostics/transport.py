"""Fixed-endpoint transport diagnostics. Never records headers, bodies or keys."""
import json
import socket
import ssl
import time
import urllib.error
import urllib.request

from al_results.nonecap.client import BASE, Client, MESSAGES, NoRedirects, ServiceError

KINDS = frozenset(('ok', 'http_error', 'timeout', 'dns_error', 'tls_error',
                   'connection_reset', 'connection_refused', 'network_error',
                   'invalid_json', 'invalid_shape', 'response_too_large'))
OPERATIONS = frozenset(('account', 'create', 'poll', 'cancel', 'connectivity'))
PROVIDER_CODES = frozenset(MESSAGES) | {'conflict', 'service_error', 'invalid_response'}


def error_kind(error):
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, (TimeoutError, socket.timeout)): return 'timeout'
    if isinstance(reason, socket.gaierror): return 'dns_error'
    if isinstance(reason, ssl.SSLError): return 'tls_error'
    if isinstance(reason, ConnectionResetError): return 'connection_reset'
    if isinstance(reason, ConnectionRefusedError): return 'connection_refused'
    return 'network_error'


def request(method, path, headers, body, record, operation, *, opener=None):
    """Match production's five-second request timeout; never retry a POST."""
    started = time.monotonic()
    status, size, kind, provider = 0, 0, 'ok', 'service_error'
    try:
        req = urllib.request.Request(BASE+path, method=method, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        with (opener or urllib.request.build_opener(NoRedirects())).open(req, timeout=5) as response:
            status = response.status
            raw = response.read(1048577)
            size = len(raw)
            if size > 1048576:
                kind = 'response_too_large'
                raise ServiceError('network_error', uncertain=method=='POST')
            try:
                data = json.loads(raw)
            except (ValueError, UnicodeError):
                kind = 'invalid_json'
                raise ServiceError('network_error', uncertain=method=='POST') from None
            if not isinstance(data,dict):
                kind = 'invalid_shape'
                raise ServiceError('network_error', uncertain=method=='POST')
            return data
    except urllib.error.HTTPError as exc:
        kind, status = 'http_error', exc.code
        try:
            raw = exc.read(65536)
            size = len(raw)
            code = json.loads(raw).get('error',{}).get('code','service_error')
            provider = code if type(code) is str and code in PROVIDER_CODES else 'service_error'
        except (ValueError, AttributeError):
            pass
        finally:
            exc.close()
        raise ServiceError(provider, uncertain=method=='POST' and status not in
                           (400,401,402,403,404,413,415,422,429)) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        kind = error_kind(exc)
        raise ServiceError('network_error', uncertain=method=='POST') from None
    finally:
        record('api_request', operation=operation, outcome=kind,
               http_status=status, bytes_received=size,
               elapsed=round(time.monotonic()-started,3), provider_code=provider if kind=='http_error' else None)


class DiagnosticClient(Client):
    def __init__(self, key, recorder):
        self.recorder = recorder
        super().__init__(key)

    def _http(self, method, path, headers, body):
        operation = 'account' if path=='/v1/me' else 'create' if method=='POST' else 'cancel' if method=='DELETE' else 'poll'
        return request(method,path,headers,body,self.recorder.write,operation)
