"""Private collector copy: production globals and source files stay untouched."""
import importlib.util
from pathlib import Path
import time
from types import SimpleNamespace

from selenium.common.exceptions import TimeoutException, JavascriptException

from al_results import collector as production
from al_results.models import WorkerEvent
from .budget import LimitReached
from .client import ServiceError
from .solver import Interrupted

HERE = Path(__file__).parent


def script(name):
    return (HERE / name).read_text(encoding='utf-8')


def private_core():
    spec = importlib.util.spec_from_file_location('al_results._nonecap_prototype_core', production.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PrototypeCollector:
    def __init__(self, notify):
        self.notify = notify
        self.solver = None
        self.disabled = False

    def fallback(self, emit, reason):
        # No raw browser, network, token or response text reaches the activity log.
        self.disabled = True
        text = reason + ' Complete CAPTCHA and submit in Chrome. Automatic mode is disabled for this window.'
        emit(WorkerEvent('log', {'text': text}))
        self.notify(dict(status=text))

    def __call__(self, config, workbook, store, emit, stop, skip):
        if self.solver is None:
            return production.collect(config, workbook, store, emit, stop, skip)
        core = private_core()
        owner = self
        base = core.BrowserSession

        class Session(base):
            def __init__(self):
                super().__init__()
                try:
                    self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': script('browser_hook.js')})
                except Exception:
                    # A missing hook is recoverable through the normal manual flow.
                    owner.fallback(emit, 'The browser hook could not be installed.')

            def fetch(self, nic, config, stop_event, skip_event, captcha_ready):
                local = SimpleNamespace(**vars(config))
                automatic = False

                def ready():
                    nonlocal automatic
                    if owner.disabled:
                        captcha_ready()
                        return
                    try:
                        widget = None
                        deadline = time.monotonic() + 12
                        while time.monotonic() < deadline:
                            core.check_controls(stop_event, skip_event)
                            widget = self.driver.execute_script(script('challenge.js'))
                            if widget: break
                            stop_event.wait(.25)
                        if not widget:
                            raise ServiceError('widget_unavailable')
                        token = owner.solver.solve(widget, stop_event, skip_event, timeout=min(120, config.captcha_timeout))
                        core.check_controls(stop_event, skip_event)
                        meta = owner.solver.solution_meta
                        if meta.get('user_agent') and meta['user_agent'] != widget['user_agent']:
                            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {'userAgent': meta['user_agent']})
                        applied = self.driver.execute_script(script('apply_token.js'), token, meta.get('resp_key', ''))
                        token = None
                        if not applied: raise ServiceError('token_not_applied')
                        stop_event.wait(.3)
                        core.check_controls(stop_event, skip_event)
                        cards = self.driver.find_elements(core.By.CSS_SELECTOR, '.card.border-info.watermark')
                        if not any(card.is_displayed() and card.text.strip() for card in cards):
                            if not self.driver.execute_script(script('submit.js')):
                                raise ServiceError('submit_unavailable')
                        automatic = True
                        local.captcha_timeout = min(20, config.captcha_timeout)
                    except Interrupted as exc:
                        if exc.kind == 'stop': raise core.StopRequested()
                        raise core.SkipCurrentRow('Skipped from the GUI.')
                    except (ServiceError, LimitReached, JavascriptException) as exc:
                        reason = str(exc) if isinstance(exc, (ServiceError, LimitReached)) else 'The form could not accept the token.'
                        owner.fallback(emit, reason)
                        captcha_ready()

                try:
                    return super().fetch(nic, local, stop_event, skip_event, ready)
                except TimeoutException:
                    if not automatic: raise
                    owner.fallback(emit, 'The site did not return results after automatic submission.')
                    captcha_ready()
                    return core.wait_for_results_or_skip(self.driver, config.captcha_timeout, stop_event, skip_event)

        core.BrowserSession = Session
        return core.collect(config, workbook, store, emit, stop, skip)
