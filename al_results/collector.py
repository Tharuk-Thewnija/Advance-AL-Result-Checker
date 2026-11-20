from __future__ import annotations
import threading
import time
from selenium import webdriver
from selenium.common.exceptions import (TimeoutException, StaleElementReferenceException,
                                        InvalidSessionIdException, NoSuchWindowException, WebDriverException)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait
from .parsing import normalize_spaces

RESULTS_PAGE_URL = "https://www.doenets.lk/examresults"
SITE_NOTICE_TEXT = 'sorry for the inconvenience, please try again'
SITE_NOTICE_SCRIPT = r"""
(() => {
    window.__alSiteNoticeSeen = false;
    const visible = node => {
        if (!node.getClientRects().length) return false;
        for (let element=node; element; element=element.parentElement) {
            const style=getComputedStyle(element);
            if (style.display==='none' || style.visibility==='hidden' || Number(style.opacity)===0) return false;
        }
        return true;
    };
    const inspect = () => {
        if (window.__alSiteNoticeSeen) return;
        for (const node of document.querySelectorAll('.toast-message,[role="alertdialog"],[role="alert"],.alert')) {
            const text=(node.innerText || '').replace(/\s+/g,' ').trim().toLowerCase();
            if (text.includes('sorry for the inconvenience, please try again') && visible(node)) {
                window.__alSiteNoticeSeen = true;
                return;
            }
        }
    };
    new MutationObserver(inspect).observe(document, {subtree:true,childList:true,characterData:true,attributes:true});
    inspect();
})();
"""

class SkipCurrentRow(Exception):
    pass

class SiteNoResults(SkipCurrentRow):
    """The site returned its unavailable-result notice for this lookup."""


def check_site_notice(driver):
    execute = getattr(driver, 'execute_script', None)
    if execute is not None and execute('return window.__alSiteNoticeSeen === true;') is True:
        raise SiteNoResults("Site returned 'Sorry for the inconvenience'; no results collected.")
    # Select the deepest matching node, including messages split across spans.
    # Check displayed text too: hidden templates must never skip a student.
    phrase = SITE_NOTICE_TEXT
    match = f"contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{phrase}')"
    selector = f'//*[not(self::script or self::style) and {match} and not(.//*[{match}])]'
    # Direct toast lookup also handles Unicode whitespace that XPath 1.0's
    # normalize-space does not normalize (for example a nonbreaking space).
    elements = driver.find_elements(By.CSS_SELECTOR, '.toast-message,[role="alertdialog"],[role="alert"],.alert')
    elements += driver.find_elements(By.XPATH, selector)
    for element in elements:
        try:
            if element.is_displayed() and phrase in normalize_spaces(element.text).casefold():
                raise SiteNoResults("Site returned 'Sorry for the inconvenience'; no results collected.")
        except StaleElementReferenceException:
            continue


class StopRequested(Exception):
    pass

def check_controls(stop_event=None, skip_event=None):
    if stop_event is not None and stop_event.is_set():
        raise StopRequested('Stopped. Progress has been saved.')
    if skip_event is not None and skip_event.is_set():
        skip_event.clear()
        raise SkipCurrentRow('Skipped by user')

def browser_closed_error(error) -> bool:
    if isinstance(error, (InvalidSessionIdException, NoSuchWindowException)):
        return True
    message = (getattr(error, 'msg', '') or '').lower()
    return isinstance(error, WebDriverException) and any(text in message for text in
        ('not connected to devtools', 'chrome not reachable', 'disconnected', 'target window already closed'))


def create_driver(*, headless=False) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument('--headless=new')
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    options.page_load_strategy = 'eager'
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(20)
    return driver


def open_search_form(driver: webdriver.Chrome, exam_year: str,
                     stop_event: threading.Event | None = None,
                     skip_event: threading.Event | None = None) -> None:
    check_controls(stop_event, skip_event)
    driver.get(RESULTS_PAGE_URL)
    wait = WebDriverWait(driver, 20, poll_frequency=0.2,
                         ignored_exceptions=(StaleElementReferenceException,))

    select_selector = ".form-control.flex-grow-1.h5"

    def exam_ready(current_driver):
        check_controls(stop_event, skip_event)
        selects = current_driver.find_elements(By.CSS_SELECTOR, select_selector)
        if not selects:
            return False
        exam_select = Select(selects[0])
        # The API supplies the label, which can include "After Rescrutiny".
        # Wait for that API data before triggering the dependent year dropdown.
        return exam_select if any(
            option.get_attribute("value") == "al" and normalize_spaces(option.text)
            for option in exam_select.options
        ) else False

    wait.until(exam_ready).select_by_value("al")

    def year_ready(current_driver):
        check_controls(stop_event, skip_event)
        selects = current_driver.find_elements(By.CSS_SELECTOR, select_selector)
        if len(selects) < 2:
            return False
        year_select = Select(selects[1])
        return year_select if any(
            normalize_spaces(option.text) == exam_year
            for option in year_select.options
        ) else False

    wait.until(year_ready).select_by_visible_text(exam_year)

    def nic_ready(current_driver):
        check_controls(stop_event, skip_event)
        return EC.element_to_be_clickable((By.CSS_SELECTOR, ".custom-option.form-control"))(current_driver)
    nic_type_element = wait.until(nic_ready)
    Select(nic_type_element).select_by_value("nic")


def wait_for_results_or_skip(
    driver: webdriver.Chrome,
    timeout_seconds: int,
    stop_event: threading.Event,
    skip_event: threading.Event,
) -> str:
    deadline = time.perf_counter() + timeout_seconds

    while time.perf_counter() < deadline:
        if stop_event.is_set():
            raise StopRequested("Stop requested from the GUI.")

        if skip_event.is_set():
            skip_event.clear()
            raise SkipCurrentRow("Skipped from the GUI while waiting for captcha/submit.")

        check_site_notice(driver)
        try:
            for card in driver.find_elements(By.CSS_SELECTOR, ".card.border-info.watermark"):
                if card.is_displayed():
                    text = card.text
                    if text.strip():
                        return text
        except StaleElementReferenceException:
            pass  # The page replaced the card while its contents were loading.
        stop_event.wait(min(.2, max(0, deadline - time.perf_counter())))

    raise TimeoutException(
        f"No results card was detected within {timeout_seconds} seconds."
    )


class BrowserSession:
    def __init__(self):
        self.driver = create_driver()
        try:
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source':SITE_NOTICE_SCRIPT})
        except WebDriverException:
            self.driver.quit()
            raise

    def fetch(self, nic, config, stop_event, skip_event, captcha_ready):
        try:
            open_search_form(self.driver, config.exam_year, stop_event, skip_event)
        except TimeoutException as exc:
            raise RuntimeError(
                f'The A/L form or year {config.exam_year} is unavailable. '
                'Check the website and exam year, then resume.'
            ) from exc
        def input_ready(driver):
            check_controls(stop_event, skip_event)
            return EC.element_to_be_clickable((By.CSS_SELECTOR, '.form-control.text-center'))(driver)
        try:
            element = WebDriverWait(self.driver, 20, poll_frequency=0.2).until(input_ready)
        except TimeoutException as exc:
            raise RuntimeError('The NIC input could not be loaded. Check the website, then resume.') from exc
        element.clear()
        element.send_keys(nic)
        captcha_ready()
        return wait_for_results_or_skip(self.driver, config.captcha_timeout, stop_event, skip_event)

    def close(self):
        self.driver.quit()


def collect(config, workbook, store, emit, stop_event, skip_event):
    """Own browser and store on this worker thread; terminal events follow cleanup."""
    from .models import RowResult, WorkerEvent
    from .parsing import parse_results
    from .excel_io import validate_rows
    browser = None
    terminal = 'finished'
    reason = ''
    error = ''
    counts = {'total': len(workbook.frame), 'processed': 0, 'completed': 0, 'skipped': 0, 'failed': 0}
    status_keys = {'Completed': 'completed', 'Skipped': 'skipped', 'Error': 'failed'}
    try:
        for result in store.results():
            counts['processed'] += 1
            counts[status_keys[result.status]] += 1
        pending = set(store.pending_positions())
        for position, nic, validation_error in validate_rows(workbook):
            if position not in pending:
                continue
            check_controls(stop_event)
            skip_event.clear()
            emit(WorkerEvent('current', {'position': position, 'nic': nic}))
            if validation_error:
                result = RowResult(position, 'Skipped', {}, validation_error)
            else:
                if browser is None:
                    browser = BrowserSession()
                try:
                    text = browser.fetch(nic, config, stop_event, skip_event,
                                         lambda: emit(WorkerEvent('log', {'text':
                                             f'Row {position + 1}: complete CAPTCHA in Chrome and submit, or choose Skip current.'})))
                    values = parse_results(text, config.subject_ids, config.fields)
                    missing = [sid for sid in config.subject_ids if values.get(f'subject:{sid}') is None]
                    note = 'Selected subject result not present: ' + ', '.join(missing) if missing else ''
                    result = RowResult(position, 'Completed', values, note)
                except SkipCurrentRow as exc:
                    result = RowResult(position, 'Skipped', {}, str(exc))
                except TimeoutException:
                    check_controls(stop_event)
                    result = RowResult(position, 'Error', {}, 'Timed out waiting for submitted results')
            # If this fails, abort rather than telling the GUI the row was saved.
            store.save(result)
            counts['processed'] += 1
            counts[status_keys[result.status]] += 1
            emit(WorkerEvent('progress', dict(counts)))
            emit(WorkerEvent('log', {'text': f'Row {position + 1}: {result.status}' + (f' — {result.note}' if result.note else '')}))
    except StopRequested:
        terminal = 'stopped'
    except WebDriverException as exc:
        if browser_closed_error(exc):
            terminal = 'stopped'
            reason = 'browser_closed'
        elif stop_event.is_set():
            terminal = 'stopped'
        else:
            terminal = 'fatal'
            error = exc.msg or 'Chrome could not complete the operation.'
    except Exception as exc:
        terminal = 'fatal'
        error = str(exc)
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        store.close()
    emit(WorkerEvent(terminal, {**counts, 'error': error, 'reason': reason}))


