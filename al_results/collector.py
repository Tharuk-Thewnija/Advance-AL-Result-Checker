from __future__ import annotations
import threading
import time
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait
from .parsing import normalize_spaces

RESULTS_PAGE_URL = "https://www.doenets.lk/examresults"

class SkipCurrentRow(Exception):
    pass

class StopRequested(Exception):
    pass

def create_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    return webdriver.Chrome(options=options)


def open_search_form(driver: webdriver.Chrome, exam_year: str) -> None:
    driver.get(RESULTS_PAGE_URL)
    wait = WebDriverWait(driver, 20, ignored_exceptions=(StaleElementReferenceException,))

    select_selector = ".form-control.flex-grow-1.h5"

    def exam_ready(current_driver):
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
        selects = current_driver.find_elements(By.CSS_SELECTOR, select_selector)
        if len(selects) < 2:
            return False
        year_select = Select(selects[1])
        return year_select if any(
            normalize_spaces(option.text) == exam_year
            for option in year_select.options
        ) else False

    wait.until(year_ready).select_by_visible_text(exam_year)

    nic_type_element = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".custom-option.form-control"))
    )
    Select(nic_type_element).select_by_value("nic")


def wait_for_results_or_skip(
    driver: webdriver.Chrome,
    timeout_seconds: int,
    stop_event: threading.Event,
    skip_event: threading.Event,
) -> str:
    deadline = time.perf_counter() + timeout_seconds
    wait = WebDriverWait(driver, 1)

    while time.perf_counter() < deadline:
        if stop_event.is_set():
            raise StopRequested("Stop requested from the GUI.")

        if skip_event.is_set():
            skip_event.clear()
            raise SkipCurrentRow("Skipped from the GUI while waiting for captcha/submit.")

        try:
            result_card = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".card.border-info.watermark")
                )
            )
            return result_card.text
        except TimeoutException:
            continue

    raise TimeoutException(
        f"No results card was detected within {timeout_seconds} seconds."
    )


