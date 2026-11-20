"""Private collector copy: production globals and source files stay untouched."""
import importlib.util
from pathlib import Path
import time
import threading
from types import SimpleNamespace

from selenium.common.exceptions import TimeoutException, JavascriptException

from al_results import collector as production
from al_results.failure_report import record_failure
from al_results.models import WorkerEvent
from .budget import LimitReached, ChargeUnconfirmed
from .client import ServiceError
from .solver import Interrupted
from .solver import Solver
from .parallel import collect_parallel, MAX_WORKERS

HERE = Path(__file__).parent
DRIVER_STARTUP_LOCK = threading.Lock()


def script(name):
    return (HERE / name).read_text(encoding='utf-8')


def private_core():
    # The build includes this source as data because the private collector must
    # have independent globals. Frozen imports may identify their path as .pyc.
    source = Path(production.__file__).with_suffix('.py')
    spec = importlib.util.spec_from_file_location('al_results._nonecap_prototype_core', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def visible_results(driver, timeout, stop, skip):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            module.check_controls(stop,skip)
            module.check_site_notice(driver)
            try:
                for card in driver.find_elements(module.By.CSS_SELECTOR,'.card.border-info.watermark'):
                    if card.is_displayed() and card.text.strip(): return card.text
            except module.StaleElementReferenceException:
                pass
            stop.wait(.2)
        raise TimeoutException('Timed out waiting for visible submitted results.')
    module.wait_for_results_or_skip = visible_results
    return module


class AutomaticCollector:
    def __init__(self, notify):
        self.notify = notify
        self.solver = None
        self.disabled = False
        self.workers = 1
        self.worker_skips = [threading.Event() for _ in range(MAX_WORKERS)]
        self.pause = threading.Event()
        self.pause_reason = ''
        self.pause_kind = 'automatic_limit'
        self.pause_lock = threading.Lock()
        self.run_stop = None
        self.core_factory = None

    def pause_at_limit(self, reason, emit):
        kind = 'billing_unconfirmed' if isinstance(reason,ChargeUnconfirmed) else 'automatic_limit'
        self.pause_collection(str(reason),kind,emit)

    def pause_collection(self, reason, kind, emit):
        with self.pause_lock:
            priority = {'automatic_limit':1,'automatic_timeout':2,'submission_timeout':2,
                        'service_connection':2,'billing_unconfirmed':3}
            if not self.pause.is_set() or priority[kind]>priority.get(self.pause_kind,0):
                self.pause_reason = reason
                self.pause_kind = kind
                self.pause.set()
                emit(WorkerEvent('log',{'text':reason+' Automatic collection paused. Pending rows are kept; no manual timeout is started.'}))

    def pause_for_timeout(self, budget, emit):
        # Solver has already attempted cancellation and receipt reconciliation.
        # An unknown charge must keep its stronger billing block on Resume.
        if budget.snapshot()['blocked']:
            self.pause_at_limit(ChargeUnconfirmed('The solve timed out and its final charge could not be confirmed. Check NoneCAP history before further automatic requests.'),emit)
        else:
            self.pause_collection('NoneCAP did not return a token before the solve timeout. Cancellation was requested; no automatic retry was made.',
                                  'automatic_timeout',emit)

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
                        if owner.pause.is_set():
                            raise core.StopRequested()
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
                        if isinstance(exc, ChargeUnconfirmed):
                            record_failure('billing', 'billing_unconfirmed')
                        owner.pause_at_limit(exc,emit)
                        raise core.StopRequested()
                    except (ServiceError, JavascriptException) as exc:
                        if isinstance(exc, ServiceError):
                            record_failure(exc.operation or 'verification', exc.code)
                        else:
                            record_failure('verification', 'browser_error')
                        if isinstance(exc, ServiceError) and exc.code in ('network_error', 'invalid_response'):
                            operation = exc.operation or 'request'
                            message = f'NoneCAP {operation} failed to return a usable response.'
                            if solver.budget.snapshot()['blocked']:
                                owner.pause_at_limit(ChargeUnconfirmed(message + ' The final charge is unknown.'), emit)
                            else:
                                owner.pause_collection(message, 'service_connection', emit)
                            raise core.StopRequested()
                        if isinstance(exc,ServiceError) and exc.code=='solve_timeout':
                            owner.pause_for_timeout(solver.budget,emit)
                            raise core.StopRequested()
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
                    record_failure('result wait', 'result_timeout', wait_limit_s=local.captcha_timeout)
                    # A paid token was already received. The missing result is
                    # an unknown submission outcome, not an absent student and
                    # not permission to launch a chain of manual timeouts.
                    owner.pause_collection('The site did not return results after automatic submission. The student remains pending; no resubmission or new paid solve was requested.',
                                           'submission_timeout',emit)
                    raise core.StopRequested()

        return Session

    def __call__(self, config, workbook, store, emit, stop, skip):
        if self.solver is None:
            return production.collect(config, workbook, store, emit, stop, skip)
        if type(self.workers) is not int or not 1<=self.workers<=MAX_WORKERS:
            store.close()
            raise ValueError(f'Choose between 1 and {MAX_WORKERS} workers.')
        self.pause.clear(); self.pause_reason = ''; self.pause_kind = 'automatic_limit'
        self.run_stop = stop
        core = (self.core_factory or private_core)()
        if self.workers > 1:
            for event in self.worker_skips: event.clear()
            def factory(number):
                def notify(data):
                    if data.get('status'): data = dict(data,status=f"Worker {number}: {data['status']}")
                    self.notify(data)
                solver = Solver(self.solver.client,self.solver.budget,notify)
                return self.session_type(core,solver,emit,f'Worker {number}')()
            metrics = collect_parallel(config,workbook,store,emit,stop,self.worker_skips,factory,core,
                                       self.pause,lambda:self.pause_reason,self.workers,pause_kind=lambda:self.pause_kind)
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
                    event = WorkerEvent('stopped',dict(event.payload,reason=self.pause_kind,error=self.pause_reason))
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


# Kept for the isolated launcher's existing imports and regression tests.
PrototypeCollector = AutomaticCollector
