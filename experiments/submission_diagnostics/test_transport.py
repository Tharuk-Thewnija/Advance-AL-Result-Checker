"""Transport classification with simulated sockets and replies; zero live requests."""
import io
import json
from pathlib import Path
import socket
import ssl
import tempfile
import unittest
import urllib.error

from al_results.nonecap.client import ServiceError
from .collector import Recorder
from .transport import request


class Response:
    status = 200
    def __init__(self, raw): self.raw=raw
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self, size): return self.raw[:size]


class Opener:
    def __init__(self, reply): self.reply=reply; self.calls=0
    def open(self, req, timeout):
        self.calls+=1
        if isinstance(self.reply,Exception): raise self.reply
        return Response(self.reply)


class TransportTests(unittest.TestCase):
    def check(self, reply, expected, method='GET'):
        with tempfile.TemporaryDirectory() as directory:
            recorder=Recorder(Path(directory)/'report.jsonl')
            opener=Opener(reply)
            with self.assertRaises(ServiceError) as error:
                request(method,'/v1/solves/solve_private',{'Authorization':'Bearer secret-key'},
                        {'token':'private-token'},recorder.write,'poll',opener=opener)
            self.assertEqual(error.exception.uncertain,method=='POST')
            self.assertEqual(opener.calls,1)
            raw=recorder.path.read_text()
            for secret in ('secret-key','private-token','solve_private','secret-student'):
                self.assertNotIn(secret,raw)
            self.assertEqual(json.loads(raw)['outcome'],expected)

    def test_dns_error(self): self.check(urllib.error.URLError(socket.gaierror(-1,'secret-student')),'dns_error')
    def test_tls_error(self): self.check(urllib.error.URLError(ssl.SSLError('secret-student')),'tls_error')
    def test_socket_timeout(self): self.check(TimeoutError('secret-student'),'timeout')
    def test_reset(self): self.check(ConnectionResetError('secret-student'),'connection_reset')
    def test_invalid_json(self): self.check(b'<html>secret-student private-token</html>','invalid_json')
    def test_invalid_shape(self): self.check(b'[]','invalid_shape')
    def test_ambiguous_post_is_not_retried(self): self.check(TimeoutError(),'timeout',method='POST')

    def test_http_error_only_logs_status_and_allowed_code(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder=Recorder(Path(directory)/'report.jsonl')
            error=urllib.error.HTTPError('https://api.nonecap.com/v1/me',429,'private-message',{},io.BytesIO(b'{"error":{"code":"private-secret-code","message":"secret-key"}}'))
            with self.assertRaises(ServiceError):
                request('GET','/v1/me',{},None,recorder.write,'account',opener=Opener(error))
            record=json.loads(recorder.path.read_text())
            self.assertEqual(record['http_status'],429)
            self.assertEqual(record['provider_code'],'service_error')
            self.assertNotIn('secret',recorder.path.read_text())

    def test_success_does_not_record_response_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder=Recorder(Path(directory)/'report.jsonl')
            reply=request('GET','/v1/me',{},None,recorder.write,'account',opener=Opener(b'{"credits_balance":100,"private":"secret-key"}'))
            self.assertEqual(reply['credits_balance'],100)
            self.assertEqual(json.loads(recorder.path.read_text())['outcome'],'ok')
            self.assertNotIn('secret-key',recorder.path.read_text())
