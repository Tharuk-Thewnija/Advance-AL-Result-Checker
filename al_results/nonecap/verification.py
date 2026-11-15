"""Exercise the installed automatic path using local pages and simulated replies."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from urllib.parse import quote

import pandas as pd

from al_results.checkpoints import CheckpointStore
from al_results.excel_io import load_workbook,export_results
from al_results.models import RunConfig
from .budget import Budget
from .client import Client
from .collector import AutomaticCollector,private_core
from .solver import Solver

CARD='Name\nLOCAL FICTIONAL STUDENT\nINFORMATION & COMMUNICATION TECHNOLOGY\nA'
HTML='''<!doctype html><meta charset="utf-8">
<select class="form-control flex-grow-1 h5"><option value="al">G.C.E.(A/L) EXAMINATION</option></select>
<select class="form-control flex-grow-1 h5"><option>2025</option></select>
<select class="custom-option form-control"><option value="nic">NIC</option></select>
<input class="form-control text-center"><div id="widget" style="width:100px;height:50px">Local widget</div>
<textarea name="h-captcha-response" hidden></textarea>
<script>
window.hcaptcha={render(container,options){return 0;}};
hcaptcha.render('widget',{sitekey:'00000000-0000-0000-0000-000000000001',
callback(token){window.verified=token==='local-token';}});
</script>
<button type="submit" onclick="if(window.verified) document.getElementById('result').style.display='block'">Submit</button>
<div id="result" class="card border-info watermark" style="display:none;white-space:pre-line">CARD</div>'''.replace('CARD',CARD)


def run(report):
    result={'checks':'failed','mode':'local HTML and simulated API; no paid requests'}
    previous=os.environ.get('LOCALAPPDATA')
    drivers=[]
    try:
        with tempfile.TemporaryDirectory(prefix='al-nonecap-check-') as directory:
            root=Path(directory); os.environ['LOCALAPPDATA']=str(root/'appdata')
            path=root/'fictional.xlsx'
            pd.DataFrame({'NIC':['200000000001','200000000002']}).to_excel(path,index=False)
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            book=load_workbook(path)
            config=RunConfig(path,('20',),('Candidate Name',),'2025',10,root/'exports')
            core=private_core(); core.RESULTS_PAGE_URL='data:text/html;charset=utf-8,'+quote(HTML)
            create=core.create_driver
            def create_local():
                driver=create(headless=True); drivers.append(driver)
                return driver
            core.create_driver=create_local
            lock=threading.Lock(); calls=Counter(); jobs={}
            def transport(method,url,headers,body):
                with lock:
                    calls[method]+=1
                    if method=='GET' and url=='/v1/me': return {'credits_balance':1000}
                    if method=='POST' and url=='/v1/solves':
                        job=f'solve_local{len(jobs)+1}'
                        jobs[job]=dict(id=job,status='solved',token='local-token',credits_charged=12)
                        reply=dict(jobs[job])
                        if len(jobs)==1: reply['credits_charged']=None
                        return reply
                    if method=='GET' and url.startswith('/v1/solves/'): return dict(jobs[url.rsplit('/',1)[-1]])
                    raise RuntimeError('Unexpected simulated request.')
            client=Client('nc_live_'+'x'*32,transport=transport)
            adapter=AutomaticCollector(lambda data:None)
            adapter.solver=Solver(client,Budget(24,2),lambda data:None)
            adapter.workers=2; adapter.core_factory=lambda:core
            events=[]
            adapter(config,book,CheckpointStore.open(book,config),events.append,threading.Event(),threading.Event())
            terminal=next(e for e in reversed(events) if e.kind in ('finished','stopped','fatal'))
            if terminal.kind!='finished' or terminal.payload['completed']!=2:
                raise RuntimeError('Automatic local collection did not finish both rows: '+terminal.payload.get('error',''))
            store=CheckpointStore.open(book,config)
            try: output=export_results(book,config,store.results())
            finally: store.close()
            exported=pd.read_excel(output)
            if exported['Information & Communication Technology Result'].tolist()!=['A','A']:
                raise RuntimeError('Automatic local Excel results did not match.')
            if before!=hashlib.sha256(path.read_bytes()).hexdigest(): raise RuntimeError('Input workbook changed.')
            if calls['POST']!=2 or calls['GET']!=3 or adapter.solver.budget.spent!=24:
                raise RuntimeError('Simulated receipt/accounting checks did not match.')
            result.update(checks='passed',workers=2,completed=2,reported_credits=24,
                          simulated_create_requests=calls['POST'],same_job_receipt_rechecks=calls['GET']-2,
                          input_unchanged=True,export_rows=len(exported),
                          browser_versions=sorted({d.capabilities.get('browserVersion','') for d in drivers}))
    except Exception as exc:
        result['error']=getattr(exc,'msg',None) or str(exc)
    finally:
        for driver in drivers:
            try: driver.quit()
            except Exception: pass
        if previous is None: os.environ.pop('LOCALAPPDATA',None)
        else: os.environ['LOCALAPPDATA']=previous
    report=Path(report); report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    if __import__('sys').stdout is not None: print(json.dumps(result,indent=2))
    return 0 if result['checks']=='passed' else 1
