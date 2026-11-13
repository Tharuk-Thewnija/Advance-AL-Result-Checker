"""Release diagnostic: real headless Chrome, local content only, no result-site lookup."""
import json
from pathlib import Path
import threading
from urllib.parse import quote

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from al_results import __version__
from al_results.collector import create_driver, wait_for_results_or_skip, browser_closed_error
from al_results.parsing import parse_results


def run(report: Path) -> int:
    driver = None
    result = dict(version=__version__, checks='failed')
    try:
        driver = create_driver(headless=True)
        result['browser_version'] = driver.capabilities.get('browserVersion', '')
        html = '''<!doctype html><input id="nic"><button id="submit"
        onclick="document.getElementById('result').style.display='block'">Show local result</button>
        <div id="result" class="card border-info watermark" style="display:none;white-space:pre-line">Candidate Name
LOCAL TEST STUDENT
Subject Stream
LOCAL TEST
INFORMATION &amp; COMMUNICATION TECHNOLOGY
A</div>'''
        driver.get('data:text/html;charset=utf-8,' + quote(html))
        driver.find_element(By.ID, 'nic').send_keys('MOCK-LOCAL-ONLY')
        driver.find_element(By.ID, 'submit').click()
        text = wait_for_results_or_skip(driver, 5, threading.Event(), threading.Event())
        result['local_result'] = parse_results(text, ('20',), ('Candidate Name',))
        if result['local_result'] != {'subject:20': 'A', 'Candidate Name': 'LOCAL TEST STUDENT'}:
            raise RuntimeError('Local browser result could not be read correctly.')
        # Closing the last window invalidates the real session just as closing
        # the application's Chrome window does. Verify the production classifier.
        driver.close()
        try:
            driver.title
        except WebDriverException as exc:
            result['closed_session_detected'] = browser_closed_error(exc)
        if not result.get('closed_session_detected'):
            raise RuntimeError('Closed Chrome session was not detected.')
        result['checks'] = 'passed'
    except Exception as exc:
        result['error'] = getattr(exc, 'msg', None) or str(exc)
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
    report = Path(report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return 0 if result['checks'] == 'passed' else 1
