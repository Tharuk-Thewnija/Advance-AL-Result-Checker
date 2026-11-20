"""Unauthenticated account-endpoint probe. No key, student or solve is sent."""
from datetime import datetime
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from al_results.nonecap.client import ServiceError
from .collector import Recorder
from .transport import request


def main():
    root = Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.local'/'share')
    report = root/'ALResultsCollectorSubmissionDiagnostics'/'ALResultsCollector'/'reports'/f'connectivity-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}.jsonl'
    recorder = Recorder(report)
    print('Checking NoneCAP connectivity without an API key. No solves or student lookups.',flush=True)
    # Three samples catch short outages; never send Authorization or POST.
    for sample in range(3):
        try:
            request('GET','/v1/me',{},None,recorder.write,'connectivity')
        except ServiceError:
            pass
        record = json.loads(report.read_text(encoding='utf-8').splitlines()[-1])
        print(f"Sample {sample+1}: {record.get('outcome')} · HTTP {record.get('http_status')} · {record.get('elapsed')}s",flush=True)
        if sample<2: time.sleep(2)
    print('HTTP 401 is expected without a key and confirms the API answered; it does not verify a solve or explain an earlier outage.')
    print(f'Report: {report}')
    return 0
