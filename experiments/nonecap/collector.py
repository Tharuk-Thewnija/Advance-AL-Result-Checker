"""Private collector copy: production globals and source files stay untouched."""
import importlib.util
from pathlib import Path
import time
import threading
from types import SimpleNamespace

from selenium.common.exceptions import TimeoutException, JavascriptException

from al_results import collector as production
from al_results.models import WorkerEvent
from .budget import LimitReached
from .client import ServiceError
from .solver import Interrupted
from .solver import Solver
from .parallel import collect_parallel

HERE = Path(__file__).parent
DRIVER_STARTUP_LOCK = threading.Lock()


def script(name):
    return (HERE / name).read_text(encoding='utf-8')


def private_core():
    spec = importlib.util.spec_from_file_location('al_results._nonecap_prototype_core', production.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def visible_results(driver, timeout, stop, skip):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            module.check_controls(stop,skip)
            try:
                for card in driver.find_elements(module.By.CSS_SELECTOR,'.card.border-info.watermark'):
                    if card.is_displayed() and card.text.strip(): return card.text
            except module.StaleElementReferenceException:
                pass
            stop.wait(.2)
        raise TimeoutException('Timed out waiting for visible submitted results.')
    module.wait_for_results_or_skip = visible_results
    return module


class PrototypeCollector:
    def __init__(self, notify):
        self.notify = notify
        self.solver = None
        self.disabled = False
        self.workers = 1
        self.worker_skips = [threading.Event(),threading.Event()]
        self.pause = threading.Event()
        self.pause_reason = ''
        self.pause_lock = threading.Lock()
        self.run_stop = None

    def pause_at_limit(self, reason, emit):
        with self.pause_lock:
            if not self.pause.is_set():
                self.pause_reason = str(reason)
                self.pause.set()
                emit(WorkerEvent('log',{'text':str(reason)+' Automatic collection paused. Pending rows are kept; no manual timeout is started.'}))

    def fallback(self, emit, reason):
        # No raw browser, network, token or response text reaches the activity log.
        self.disabled = True
        text = reason + ' Complete CAPTCHA and submit in Chrome. Automatic mode is disabled for this window.'
        emit(WorkerEvent('log', {'text': text}))
        self.notify(dict(status=text))

    def session_type(self, core, solver, emit, label=''):
        owner = self
        base = core.BrowserSession
        original_emit = emit
        def emit(event):
            if label and event.kind == 'log':
                event = WorkerEvent('log',{'text':label+': '+event.payload['text']})
            original_emit(event)

        class Session(base):
            def __init__(self):
                # Selenium Manager updates a shared cache while resolving Chrome.
                # Serialize startup only; page requests and solves remain parallel.
                while not DRIVER_STARTUP_LOCK.acquire(timeout=.2):
                    if owner.run_stop is not None and owner.run_stop.is_set(): raise core.StopRequested()
                try:
                    if owner.run_stop is not None and owner.run_stop.is_set(): raise core.StopRequested()
                    super().__init__()
                except Exception:
                    if hasattr(self,'driver'):
                        try: self.driver.quit()
                        except Exception: pass
                    raise
                finally:
                    DRIVER_STARTUP_LOCK.release()
                try:
                    self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': script('browser_hook.js')})
                    if label:
                        import json
                        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source':
                            'document.addEventListener("DOMContentLoaded",()=>{document.title='+json.dumps(label+' · ')+'+document.title;});'})
                except Exception:
                    # A missing hook is recoverable through the normal manual flow.
                    owner.fallback(emit, 'The browser hook could not be installed.')

            def fetch(self, nic, config, stop_event, skip_event, captcha_ready):
                local = SimpleNamespace(**vars(config))
                automatic = False

                def log(text):
                    emit(WorkerEvent('log', {'text': text}))

                def ready():
                    nonlocal automatic
                    try:
                        # Budget exhaustion takes precedence over an earlier service
                        # fallback, so later rows stay pending instead of timing out.
                        solver.budget.check()
                        if owner.disabled:
                            captcha_ready()
                            return
                        widget = None
                        deadline = time.monotonic() + 12
                        while time.monotonic() < deadline:
                            core.check_controls(stop_event, skip_event)
                            widget = self.driver.execute_script(script('challenge.js'))
                            if widget: break
                            stop_event.wait(.25)
                        if not widget:
                            raise ServiceError('widget_unavailable')
                        log('Automatic CAPTCHA: checking session limits and account before requesting a token. Leave the checkbox untouched.')
                        token = solver.solve(widget, stop_event, skip_event, timeout=min(120, config.captcha_timeout))
                        usage = solver.budget.snapshot()
                        log(f"NoneCAP token received. Reported charge: {solver.last_charge} credits. "
                            f"Session: {usage['spent']}/{usage['credit_limit']} credits; "
                            f"attempts: {usage['attempts']}/{usage['max_attempts']}.")
                        core.check_controls(stop_event, skip_event)
                        meta = solver.solution_meta
                        if meta.get('user_agent') and meta['user_agent'] != widget['user_agent']:
                            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {'userAgent': meta['user_agent']})
                        applied = self.driver.execute_script(script('apply_token.js'), token, meta.get('resp_key', ''))
                        token = None
                        if not applied or not applied.get('applied'): raise ServiceError('token_not_applied')
                        if applied.get('already_verified'):
                            log('The page already contained a CAPTCHA response before token delivery; browser verification may have overlapped the automatic attempt.')
                        log('Token delivered through the site CAPTCHA callback.' if applied.get('callback') else
                            'Token written into response fields; no site CAPTCHA callback was found. Site acceptance is not confirmed.')
                        stop_event.wait(.3)
                        core.check_controls(stop_event, skip_event)
                        cards = self.driver.find_elements(core.By.CSS_SELECTOR, '.card.border-info.watermark')
                        if not any(card.is_displayed() and card.text.strip() for card in cards):
                            if not self.driver.execute_script(script('submit.js')):
                                raise ServiceError('submit_unavailable')
                            log('Automatic form submission triggered. Waiting for student results; token acceptance is not yet confirmed.')
                        automatic = True
                        local.captcha_timeout = min(20, config.captcha_timeout)
                    except Interrupted as exc:
                        if exc.kind == 'stop': raise core.StopRequested()
                        raise core.SkipCurrentRow('Skipped from the GUI.')
                    except LimitReached as exc:
                        owner.pause_at_limit(exc,emit)
                        raise core.StopRequested()
                    except (ServiceError, JavascriptException) as exc:
                        reason = str(exc) if isinstance(exc, ServiceError) else 'The form could not accept the token.'
                        owner.fallback(emit, reason)
                        captcha_ready()

                try:
                    text = super().fetch(nic, local, stop_event, skip_event, ready)
                    if automatic and text.strip():
                        log('Results received after automatic submission.')
                    return text
                except TimeoutException:
                    if not automatic: raise
                    owner.fallback(emit, 'The site did not return results after automatic submission.')
                    captcha_ready()
                    return core.wait_for_results_or_skip(self.driver, config.captcha_timeout, stop_event, skip_event)

        return Session

    def __call__(self, config, workbook, store, emit, stop, skip):
        if self.solver is None:
            return production.collect(config, workbook, store, emit, stop, skip)
        self.pause.clear(); self.pause_reason = ''
        self.run_stop = stop
        core = private_core()
        if self.workers == 2:
            for event in self.worker_skips: event.clear()
            def factory(number):
                def notify(data):
                    if data.get('status'): data = dict(data,status=f"Worker {number}: {data['status']}")
                    self.notify(data)
                solver = Solver(self.solver.client,self.solver.budget,notify)
                return self.session_type(core,solver,emit,f'Worker {number}')()
            metrics = collect_parallel(config,workbook,store,emit,stop,self.worker_skips,factory,core,
                                       self.pause,lambda:self.pause_reason,2)
        else:
            started = time.perf_counter()
            rows = 0
            terminal_event = None
            try: previously_saved = len(store.results())
            except Exception:
                store.close()
                raise
            def observe(event):
                nonlocal rows,terminal_event
                if event.kind == 'progress': rows = event.payload['processed']-previously_saved
                if event.kind == 'stopped' and self.pause.is_set():
                    event = WorkerEvent('stopped',dict(event.payload,reason='automatic_limit',error=self.pause_reason))
                if event.kind in ('finished','stopped','fatal'):
                    terminal_event=event
                    return
                emit(event)
            core.BrowserSession = self.session_type(core,self.solver,observe)
            core.collect(config,workbook,store,observe,stop,skip)
            elapsed = time.perf_counter()-started
            metrics = dict(workers=1,rows=rows,elapsed_seconds=elapsed,rows_per_minute=rows*60/elapsed if elapsed else 0)
            emit(WorkerEvent('log',{'text':f'Batch: 1 worker, {rows} newly saved rows in {elapsed:.1f}s ({metrics["rows_per_minute"]:.1f} rows/min).'}))
            if terminal_event: emit(terminal_event)
        self.notify({'performance':f"{metrics['workers']} worker(s) · {metrics['rows']} rows · {metrics['elapsed_seconds']:.1f}s · {metrics['rows_per_minute']:.1f} rows/min"})
        return metrics
