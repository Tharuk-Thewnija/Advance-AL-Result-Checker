from __future__ import annotations

import queue
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

try:
    import customtkinter as ctk
    from tkinter import filedialog, messagebox
except ImportError as exc:
    raise SystemExit(
        "CustomTkinter is required. Install dependencies with: "
        "pip install customtkinter selenium pandas openpyxl"
    ) from exc

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait


RESULTS_PAGE_URL = "https://www.doenets.lk/examresults"
DEFAULT_EXAM_NAME = "G.C.E.(A/L) EXAMINATION"
DEFAULT_OUTPUT_MODE = "Full Student Data"
DEFAULT_TIMEOUT_SECONDS = 180
THEME_GREEN = "#1D6F5F"
THEME_SURFACE = "#F5F7F7"
THEME_CARD = "#FFFFFF"
THEME_TEXT = "#18332E"


class SkipCurrentRow(Exception):
    """Raised when the user chooses to skip the currently pending NIC."""


class StopRequested(Exception):
    """Raised when the user stops the worker."""


@dataclass(slots=True)
class ScrapeConfig:
    input_path: Path
    subject_name: str
    output_mode: str
    exam_year: str
    captcha_timeout: int


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_subject_key(value: str) -> str:
    cleaned = normalize_spaces(value).upper().replace("&", " AND ")
    cleaned = re.sub(r"[^A-Z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_nic(value: object) -> str:
    if pd.isna(value):
        return ""

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    if isinstance(value, int):
        return str(value)

    cleaned = re.sub(r"[\s-]+", "", str(value or "")).upper()

    if re.fullmatch(r"\d+\.0+", cleaned):
        return cleaned.split(".", 1)[0]

    return cleaned


def is_valid_nic(nic: str) -> bool:
    return bool(re.fullmatch(r"(?:\d{9}[VX]|\d{12})", nic))


def normalize_lines(text: str) -> list[str]:
    return [normalize_spaces(line) for line in text.splitlines() if normalize_spaces(line)]


def find_labeled_value(lines: list[str], *labels: str) -> str | None:
    for label in labels:
        label_upper = label.upper()
        for index, line in enumerate(lines):
            line_upper = line.upper()
            if line_upper.startswith(label_upper):
                suffix = line[len(label):].strip(" :-\t")
                if label_upper == "DISTRICT" and suffix.upper().startswith("RANK"):
                    continue
                if suffix:
                    return suffix
                if index + 1 < len(lines):
                    return lines[index + 1]

            match = re.search(
                rf"^{re.escape(label)}(?:\s*[:\-]\s*|\s+)(.+)$",
                line,
                re.IGNORECASE,
            )
            if match:
                value = normalize_spaces(match.group(1))
                if label_upper == "DISTRICT" and value.upper().startswith("RANK"):
                    continue
                if value:
                    return value
    return None


GRADE_TOKEN_PATTERN = re.compile(r"^(?:[A-Z]{1,3}[+-]?|\d{1,4})$")
NON_SUBJECT_KEYS = {
    normalize_subject_key("Examination"),
    normalize_subject_key("Year"),
    normalize_subject_key("Name"),
    normalize_subject_key("Candidate Name"),
    normalize_subject_key("Index Number"),
    normalize_subject_key("NIC Number"),
    normalize_subject_key("District Rank"),
    normalize_subject_key("Island Rank"),
    normalize_subject_key("Z-Score"),
    normalize_subject_key("Z Score"),
    normalize_subject_key("Subject Stream"),
    normalize_subject_key("School"),
    normalize_subject_key("School Name"),
    normalize_subject_key("District"),
    normalize_subject_key("Medium"),
    normalize_subject_key("G.C.E.(A/L) EXAMINATION"),
}


def extract_grade(candidate: str) -> str | None:
    tokens = normalize_spaces(candidate).strip(" :-").split()
    if not tokens:
        return None

    if GRADE_TOKEN_PATTERN.fullmatch(tokens[0]):
        return tokens[0]
    if GRADE_TOKEN_PATTERN.fullmatch(tokens[-1]):
        return tokens[-1]
    return None


def strip_embedded_grade(candidate: str) -> str:
    tokens = normalize_spaces(candidate).strip(" :-").split()
    if not tokens:
        return ""

    if GRADE_TOKEN_PATTERN.fullmatch(tokens[0]):
        tokens = tokens[1:]
    if tokens and GRADE_TOKEN_PATTERN.fullmatch(tokens[-1]):
        tokens = tokens[:-1]
    return " ".join(tokens).strip()


def is_probable_subject_line(candidate: str) -> bool:
    cleaned = normalize_spaces(candidate)
    if not cleaned:
        return False

    if extract_grade(cleaned) == cleaned:
        return False

    key = normalize_subject_key(strip_embedded_grade(cleaned))
    if not key or key in NON_SUBJECT_KEYS:
        return False

    if re.fullmatch(r"[\d.\-]+", cleaned):
        return False

    return bool(re.search(r"[A-Z]", key))


def extract_subject_results(lines: list[str]) -> dict[str, str]:
    subject_results: dict[str, str] = {}
    anchor_index = -1

    for index, line in enumerate(lines):
        if normalize_subject_key(line).startswith(normalize_subject_key("Subject Stream")):
            anchor_index = index

    search_lines = lines[anchor_index + 1 :] if anchor_index >= 0 else lines

    index = 0
    while index < len(search_lines):
        current_line = search_lines[index]
        current_grade = extract_grade(current_line)

        if is_probable_subject_line(current_line):
            subject_text = strip_embedded_grade(current_line)
            subject_key = normalize_subject_key(subject_text)

            if current_grade and subject_key:
                subject_results[subject_key] = current_grade
                index += 1
                continue

            if index + 1 < len(search_lines):
                next_line = search_lines[index + 1]
                next_grade = extract_grade(next_line)
                if next_grade and not is_probable_subject_line(next_line):
                    subject_results[subject_key] = next_grade
                    index += 2
                    continue

        index += 1

    if subject_results:
        return subject_results

    subject_candidates: list[str] = []
    grade_candidates: list[str] = []

    for line in search_lines:
        if is_probable_subject_line(line):
            subject_candidates.append(strip_embedded_grade(line))
            continue

        grade = extract_grade(line)
        if grade:
            grade_candidates.append(grade)

    if subject_candidates and grade_candidates:
        for subject_text, grade in zip(subject_candidates, grade_candidates):
            subject_key = normalize_subject_key(subject_text)
            if subject_key:
                subject_results[subject_key] = grade

    return subject_results


def find_subject_grade(lines: list[str], subject_name: str) -> str | None:
    subject_key = normalize_subject_key(subject_name)
    subject_results = extract_subject_results(lines)

    if subject_key in subject_results:
        return subject_results[subject_key]

    for found_subject_key, grade in subject_results.items():
        if subject_key in found_subject_key or found_subject_key in subject_key:
            return grade

    return None


def parse_results(text: str, subject_name: str) -> dict[str, str | None]:
    lines = normalize_lines(text)

    return {
        "Candidate Name": find_labeled_value(lines, "Candidate Name", "Name"),
        "School": find_labeled_value(lines, "School Name", "School"),
        "District": find_labeled_value(lines, "District"),
        "Medium": find_labeled_value(lines, "Medium"),
        "Index Number": find_labeled_value(lines, "Index Number"),
        "District Rank": find_labeled_value(lines, "District Rank"),
        "Island Rank": find_labeled_value(lines, "Island Rank"),
        "Z-Score": find_labeled_value(lines, "Z-Score", "Z Score"),
        "Subject Stream": find_labeled_value(lines, "Subject Stream", "Stream"),
        "Selected Subject Result": find_subject_grade(lines, subject_name),
        "Raw Results Block": text.strip(),
    }


def build_output_columns(subject_name: str, output_mode: str) -> list[str]:
    subject_result_column = f"{subject_name} Result"
    base_columns = [
        "Scrape Status",
        "Scrape Notes",
        subject_result_column,
    ]

    if output_mode == "Results Only":
        return base_columns

    if output_mode == "Results + Ranks":
        return base_columns + ["District Rank", "Island Rank"]

    return base_columns + [
        "Candidate Name",
        "School",
        "District",
        "Medium",
        "Index Number",
        "District Rank",
        "Island Rank",
        "Z-Score",
        "Subject Stream",
        "Raw Results Block",
    ]


def ensure_output_columns(df: pd.DataFrame, subject_name: str, output_mode: str) -> str:
    subject_result_column = f"{subject_name} Result"
    for column in build_output_columns(subject_name, output_mode):
        if column not in df.columns:
            df[column] = None
        df[column] = df[column].astype(object)
    return subject_result_column


def apply_parsed_data(
    df: pd.DataFrame,
    row_index: int,
    parsed: dict[str, str | None],
    subject_result_column: str,
    output_mode: str,
) -> None:
    df.at[row_index, "Scrape Status"] = "Completed"
    df.at[row_index, "Scrape Notes"] = ""
    df.at[row_index, subject_result_column] = parsed["Selected Subject Result"]

    if output_mode == "Results Only":
        return

    df.at[row_index, "District Rank"] = parsed["District Rank"]
    df.at[row_index, "Island Rank"] = parsed["Island Rank"]

    if output_mode == "Results + Ranks":
        return

    df.at[row_index, "Candidate Name"] = parsed["Candidate Name"]
    df.at[row_index, "School"] = parsed["School"]
    df.at[row_index, "District"] = parsed["District"]
    df.at[row_index, "Medium"] = parsed["Medium"]
    df.at[row_index, "Index Number"] = parsed["Index Number"]
    df.at[row_index, "Z-Score"] = parsed["Z-Score"]
    df.at[row_index, "Subject Stream"] = parsed["Subject Stream"]
    df.at[row_index, "Raw Results Block"] = parsed["Raw Results Block"]


def create_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    return webdriver.Chrome(options=options)


def open_search_form(driver: webdriver.Chrome, exam_year: str) -> None:
    driver.get(RESULTS_PAGE_URL)
    wait = WebDriverWait(driver, 20)

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


def send_message(worker_queue: queue.Queue, message_type: str, **payload: object) -> None:
    worker_queue.put({"type": message_type, **payload})


def scraping_worker(
    config: ScrapeConfig,
    worker_queue: queue.Queue,
    stop_event: threading.Event,
    skip_event: threading.Event,
) -> None:
    start_time = time.perf_counter()
    driver: webdriver.Chrome | None = None

    try:
        df = pd.read_excel(config.input_path)
        if "NIC" not in df.columns:
            raise ValueError("The Excel file must contain a 'NIC' column.")

        subject_result_column = ensure_output_columns(
            df, config.subject_name, config.output_mode
        )
        total_rows = len(df.index)

        send_message(
            worker_queue,
            "status",
            text=f"Loaded {total_rows} rows from {config.input_path.name}.",
        )

        # Performance optimization:
        # - Validation happens before Selenium navigation, so bad NICs are rejected
        #   immediately without opening the site.
        # - One browser instance is reused for the entire batch instead of starting
        #   Chrome for every row, which cuts the slowest setup cost dramatically.
        driver = create_driver()
        processed = 0
        succeeded = 0
        skipped = 0
        failed = 0

        for row_index, row in df.iterrows():
            if stop_event.is_set():
                raise StopRequested("Stop requested before processing the next row.")

            nic = normalize_nic(row.get("NIC"))
            row_started = time.perf_counter()
            skip_event.clear()
            send_message(worker_queue, "current", nic=nic or "<blank>")

            if not is_valid_nic(nic):
                df.at[row_index, "Scrape Status"] = "Skipped"
                df.at[row_index, "Scrape Notes"] = "Invalid NIC format"
                skipped += 1
                processed += 1
                send_message(
                    worker_queue,
                    "log",
                    text=f"Skipped invalid NIC: {nic or '<blank>'}",
                )
                elapsed = time.perf_counter() - start_time
                send_message(
                    worker_queue,
                    "progress",
                    processed=processed,
                    total=total_rows,
                    succeeded=succeeded,
                    skipped=skipped,
                    failed=failed,
                    elapsed=elapsed,
                )
                continue

            try:
                open_search_form(driver, config.exam_year)
                nic_input = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, ".form-control.text-center")
                    )
                )
                nic_input.clear()
                nic_input.send_keys(nic)

                send_message(
                    worker_queue,
                    "log",
                    text=(
                        f"NIC {nic}: solve the captcha in Chrome, submit the form, "
                        f"or press 'Skip Current'."
                    ),
                )

                raw_text = wait_for_results_or_skip(
                    driver,
                    config.captcha_timeout,
                    stop_event,
                    skip_event,
                )
                parsed = parse_results(raw_text, config.subject_name)
                apply_parsed_data(
                    df,
                    row_index,
                    parsed,
                    subject_result_column,
                    config.output_mode,
                )

                succeeded += 1
                send_message(
                    worker_queue,
                    "log",
                    text=(
                        f"Completed {nic} | {subject_result_column}: "
                        f"{parsed['Selected Subject Result'] or 'Not found'}"
                    ),
                )

            except SkipCurrentRow as exc:
                df.at[row_index, "Scrape Status"] = "Skipped"
                df.at[row_index, "Scrape Notes"] = str(exc)
                skipped += 1
                send_message(worker_queue, "log", text=f"Skipped {nic}: {exc}")

            except StopRequested:
                raise

            except Exception as exc:
                df.at[row_index, "Scrape Status"] = "Error"
                df.at[row_index, "Scrape Notes"] = str(exc)
                failed += 1
                send_message(worker_queue, "log", text=f"Error for {nic}: {exc}")

            finally:
                processed += 1
                row_elapsed = time.perf_counter() - row_started
                elapsed = time.perf_counter() - start_time

                # Performance optimization:
                # - The worker posts compact progress snapshots into a queue instead
                #   of touching Tk widgets directly from the worker thread.
                # - The GUI remains responsive because the main thread only performs
                #   lightweight reads from the queue via after().
                send_message(
                    worker_queue,
                    "progress",
                    processed=processed,
                    total=total_rows,
                    succeeded=succeeded,
                    skipped=skipped,
                    failed=failed,
                    elapsed=elapsed,
                    last_row_seconds=row_elapsed,
                )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = config.input_path.with_name(f"completed_results_{timestamp}.xlsx")
        df.to_excel(output_path, index=False)

        send_message(
            worker_queue,
            "complete",
            output_path=str(output_path),
            processed=processed,
            total=total_rows,
            succeeded=succeeded,
            skipped=skipped,
            failed=failed,
            stopped=False,
        )

    except StopRequested as exc:
        output_path = None
        try:
            if "df" in locals():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = config.input_path.with_name(
                    f"partial_results_{timestamp}.xlsx"
                )
                df.to_excel(output_path, index=False)
        except Exception:
            output_path = None

        send_message(
            worker_queue,
            "complete",
            output_path=str(output_path) if output_path else "",
            processed=locals().get("processed", 0),
            total=locals().get("total_rows", 0),
            succeeded=locals().get("succeeded", 0),
            skipped=locals().get("skipped", 0),
            failed=locals().get("failed", 0),
            stopped=True,
            reason=str(exc),
        )

    except Exception as exc:
        send_message(worker_queue, "fatal", text=str(exc))

    finally:
        if driver is not None:
            driver.quit()


class ScraperApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AL Results Scraper")
        self.geometry("1080x760")
        self.minsize(980, 700)
        self.configure(fg_color=THEME_SURFACE)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")

        self.worker_thread: threading.Thread | None = None
        self.worker_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.skip_event = threading.Event()

        self.file_path_var = ctk.StringVar(value="")
        self.subject_var = ctk.StringVar(value="Combined Mathematics")
        self.output_mode_var = ctk.StringVar(value=DEFAULT_OUTPUT_MODE)
        self.exam_year_var = ctk.StringVar(value="2025")
        self.timeout_var = ctk.StringVar(value=str(DEFAULT_TIMEOUT_SECONDS))
        self.current_nic_var = ctk.StringVar(value="Current NIC: -")
        self.progress_var = ctk.DoubleVar(value=0)
        self.progress_label_var = ctk.StringVar(value="0 / 0 processed")
        self.eta_var = ctk.StringVar(value="ETA: --")
        self.summary_var = ctk.StringVar(value="Success: 0 | Skipped: 0 | Failed: 0")

        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(
            self,
            fg_color=THEME_CARD,
            corner_radius=18,
            border_color="#D8E2DF",
            border_width=1,
        )
        header.grid(row=0, column=0, padx=20, pady=(20, 12), sticky="nsew")
        header.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(
            header,
            text="Advanced AL Results Scraper",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=THEME_TEXT,
        )
        title.grid(row=0, column=0, columnspan=2, padx=22, pady=(18, 8), sticky="w")

        subtitle = ctk.CTkLabel(
            header,
            text=(
                "Load an Excel file, choose the subject exactly as it appears on the website, "
                "then process each NIC without freezing the desktop app."
            ),
            font=ctk.CTkFont(size=14),
            justify="left",
            text_color="#56736D",
            wraplength=880,
        )
        subtitle.grid(row=1, column=0, columnspan=2, padx=22, pady=(0, 16), sticky="w")

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        controls.grid_columnconfigure(0, weight=0)
        controls.grid_columnconfigure(1, weight=1)
        controls.grid_rowconfigure(1, weight=1)

        settings_card = ctk.CTkFrame(
            controls,
            fg_color=THEME_CARD,
            corner_radius=18,
            border_color="#D8E2DF",
            border_width=1,
            width=340,
        )
        settings_card.grid(row=0, column=0, rowspan=2, padx=(0, 12), sticky="nsew")
        settings_card.grid_columnconfigure(0, weight=1)

        settings_title = ctk.CTkLabel(
            settings_card,
            text="Run Settings",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=THEME_TEXT,
        )
        settings_title.grid(row=0, column=0, padx=18, pady=(18, 12), sticky="w")

        self._build_settings_form(settings_card)

        right_panel = ctk.CTkFrame(controls, fg_color="transparent")
        right_panel.grid(row=0, column=1, rowspan=2, sticky="nsew")
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(1, weight=1)

        progress_card = ctk.CTkFrame(
            right_panel,
            fg_color=THEME_CARD,
            corner_radius=18,
            border_color="#D8E2DF",
            border_width=1,
        )
        progress_card.grid(row=0, column=0, sticky="ew")
        progress_card.grid_columnconfigure(0, weight=1)

        progress_title = ctk.CTkLabel(
            progress_card,
            text="Progress",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=THEME_TEXT,
        )
        progress_title.grid(row=0, column=0, padx=18, pady=(18, 10), sticky="w")

        progress_bar = ctk.CTkProgressBar(
            progress_card,
            variable=self.progress_var,
            progress_color=THEME_GREEN,
            height=18,
            corner_radius=10,
        )
        progress_bar.grid(row=1, column=0, padx=18, pady=(0, 10), sticky="ew")

        progress_label = ctk.CTkLabel(
            progress_card,
            textvariable=self.progress_label_var,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=THEME_TEXT,
        )
        progress_label.grid(row=2, column=0, padx=18, pady=(0, 4), sticky="w")

        eta_label = ctk.CTkLabel(
            progress_card,
            textvariable=self.eta_var,
            font=ctk.CTkFont(size=14),
            text_color="#56736D",
        )
        eta_label.grid(row=3, column=0, padx=18, pady=(0, 4), sticky="w")

        current_label = ctk.CTkLabel(
            progress_card,
            textvariable=self.current_nic_var,
            font=ctk.CTkFont(size=14),
            text_color="#56736D",
        )
        current_label.grid(row=4, column=0, padx=18, pady=(0, 4), sticky="w")

        summary_label = ctk.CTkLabel(
            progress_card,
            textvariable=self.summary_var,
            font=ctk.CTkFont(size=14),
            text_color="#56736D",
        )
        summary_label.grid(row=5, column=0, padx=18, pady=(0, 18), sticky="w")

        log_card = ctk.CTkFrame(
            right_panel,
            fg_color=THEME_CARD,
            corner_radius=18,
            border_color="#D8E2DF",
            border_width=1,
        )
        log_card.grid(row=1, column=0, pady=(12, 0), sticky="nsew")
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)

        log_title = ctk.CTkLabel(
            log_card,
            text="Run Log",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=THEME_TEXT,
        )
        log_title.grid(row=0, column=0, padx=18, pady=(18, 10), sticky="w")

        self.log_text = ctk.CTkTextbox(
            log_card,
            fg_color="#F8FAFA",
            border_color="#D8E2DF",
            border_width=1,
            corner_radius=14,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=13),
        )
        self.log_text.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")
        self.log_text.insert("end", "Application ready.\n")
        self.log_text.configure(state="disabled")

    def _build_settings_form(self, parent: ctk.CTkFrame) -> None:
        label_color = "#4D6661"

        file_label = ctk.CTkLabel(
            parent,
            text="Excel File",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=label_color,
        )
        file_label.grid(row=1, column=0, padx=18, pady=(4, 6), sticky="w")

        file_frame = ctk.CTkFrame(parent, fg_color="transparent")
        file_frame.grid(row=2, column=0, padx=18, pady=(0, 12), sticky="ew")
        file_frame.grid_columnconfigure(0, weight=1)

        self.file_entry = ctk.CTkEntry(
            file_frame,
            textvariable=self.file_path_var,
            placeholder_text="Select the input Excel file",
            height=40,
            corner_radius=12,
        )
        self.file_entry.grid(row=0, column=0, padx=(0, 8), sticky="ew")

        self.browse_button = ctk.CTkButton(
            file_frame,
            text="Browse",
            command=self.browse_file,
            width=96,
            height=40,
            corner_radius=12,
            fg_color=THEME_GREEN,
            hover_color="#175A4D",
        )
        self.browse_button.grid(row=0, column=1, sticky="e")

        subject_label = ctk.CTkLabel(
            parent,
            text="Subject Name",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=label_color,
        )
        subject_label.grid(row=3, column=0, padx=18, pady=(4, 6), sticky="w")

        self.subject_entry = ctk.CTkEntry(
            parent,
            textvariable=self.subject_var,
            placeholder_text="Example: Combined Mathematics",
            height=40,
            corner_radius=12,
        )
        self.subject_entry.grid(row=4, column=0, padx=18, pady=(0, 12), sticky="ew")

        output_label = ctk.CTkLabel(
            parent,
            text="Output Type",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=label_color,
        )
        output_label.grid(row=5, column=0, padx=18, pady=(4, 6), sticky="w")

        self.output_menu = ctk.CTkOptionMenu(
            parent,
            values=["Results Only", "Results + Ranks", "Full Student Data"],
            variable=self.output_mode_var,
            height=40,
            corner_radius=12,
            fg_color=THEME_GREEN,
            button_color="#175A4D",
            button_hover_color="#12443A",
            dropdown_fg_color=THEME_CARD,
            dropdown_hover_color="#EAF1EF",
            text_color="#FFFFFF",
        )
        self.output_menu.grid(row=6, column=0, padx=18, pady=(0, 12), sticky="ew")

        compact_row = ctk.CTkFrame(parent, fg_color="transparent")
        compact_row.grid(row=7, column=0, padx=18, pady=(0, 12), sticky="ew")
        compact_row.grid_columnconfigure(0, weight=1)
        compact_row.grid_columnconfigure(1, weight=1)

        year_label = ctk.CTkLabel(
            compact_row,
            text="Exam Year",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=label_color,
        )
        year_label.grid(row=0, column=0, padx=(0, 6), pady=(0, 6), sticky="w")

        timeout_label = ctk.CTkLabel(
            compact_row,
            text="Captcha Timeout (s)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=label_color,
        )
        timeout_label.grid(row=0, column=1, padx=(6, 0), pady=(0, 6), sticky="w")

        self.year_entry = ctk.CTkEntry(
            compact_row,
            textvariable=self.exam_year_var,
            height=40,
            corner_radius=12,
        )
        self.year_entry.grid(row=1, column=0, padx=(0, 6), sticky="ew")

        self.timeout_entry = ctk.CTkEntry(
            compact_row,
            textvariable=self.timeout_var,
            height=40,
            corner_radius=12,
        )
        self.timeout_entry.grid(row=1, column=1, padx=(6, 0), sticky="ew")

        helper = ctk.CTkLabel(
            parent,
            text=(
                "NIC validation runs before Selenium starts. Invalid values are marked "
                "as skipped automatically to save time."
            ),
            font=ctk.CTkFont(size=13),
            justify="left",
            wraplength=280,
            text_color="#6A827D",
        )
        helper.grid(row=8, column=0, padx=18, pady=(0, 18), sticky="w")

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=9, column=0, padx=18, pady=(0, 18), sticky="ew")
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=1)
        actions.grid_columnconfigure(2, weight=1)

        self.start_button = ctk.CTkButton(
            actions,
            text="Start Scraping",
            command=self.start_scraping,
            height=42,
            corner_radius=12,
            fg_color=THEME_GREEN,
            hover_color="#175A4D",
        )
        self.start_button.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.stop_button = ctk.CTkButton(
            actions,
            text="Stop",
            command=self.stop_scraping,
            state="disabled",
            height=42,
            corner_radius=12,
            fg_color="#C75450",
            hover_color="#AA4341",
        )
        self.stop_button.grid(row=0, column=1, padx=6, sticky="ew")

        self.skip_button = ctk.CTkButton(
            actions,
            text="Skip Current",
            command=self.skip_current,
            state="disabled",
            height=42,
            corner_radius=12,
            fg_color="#D2A63F",
            hover_color="#B78B29",
        )
        self.skip_button.grid(row=0, column=2, padx=(6, 0), sticky="ew")

    def browse_file(self) -> None:
        selected_file = filedialog.askopenfilename(
            title="Select Excel file",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")],
        )
        if selected_file:
            self.file_path_var.set(selected_file)

    def append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def start_scraping(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("Scraper Running", "A scraping job is already in progress.")
            return

        file_path = Path(self.file_path_var.get().strip())
        subject_name = normalize_spaces(self.subject_var.get())
        exam_year = self.exam_year_var.get().strip()

        try:
            captcha_timeout = int(self.timeout_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Timeout", "Captcha timeout must be a whole number.")
            return

        if not file_path.exists():
            messagebox.showerror("Missing File", "Select a valid Excel file before starting.")
            return

        if not subject_name:
            messagebox.showerror(
                "Missing Subject",
                "Enter the subject name exactly as it appears on the website.",
            )
            return

        if not exam_year.isdigit():
            messagebox.showerror("Invalid Year", "Exam year must be numeric.")
            return

        if captcha_timeout <= 0:
            messagebox.showerror(
                "Invalid Timeout",
                "Captcha timeout must be greater than zero seconds.",
            )
            return

        config = ScrapeConfig(
            input_path=file_path,
            subject_name=subject_name,
            output_mode=self.output_mode_var.get(),
            exam_year=exam_year,
            captcha_timeout=captcha_timeout,
        )

        self.worker_queue = queue.Queue()
        self.stop_event.clear()
        self.skip_event.clear()
        self.progress_var.set(0)
        self.progress_label_var.set("0 / 0 processed")
        self.eta_var.set("ETA: --")
        self.summary_var.set("Success: 0 | Skipped: 0 | Failed: 0")
        self.current_nic_var.set("Current NIC: -")
        self.append_log(
            f"Starting run for subject '{subject_name}' with output mode '{config.output_mode}'."
        )

        self.set_running_state(True)
        self.worker_thread = threading.Thread(
            target=scraping_worker,
            args=(config, self.worker_queue, self.stop_event, self.skip_event),
            daemon=True,
        )
        self.worker_thread.start()
        self.after(150, self.process_worker_messages)

    def set_running_state(self, is_running: bool) -> None:
        running_state = "disabled" if is_running else "normal"
        control_state = "normal" if is_running else "disabled"

        self.start_button.configure(state=running_state)
        self.file_entry.configure(state=running_state)
        self.browse_button.configure(state=running_state)
        self.subject_entry.configure(state=running_state)
        self.output_menu.configure(state=running_state)
        self.year_entry.configure(state=running_state)
        self.timeout_entry.configure(state=running_state)
        self.stop_button.configure(state=control_state)
        self.skip_button.configure(state=control_state)

    def stop_scraping(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            self.stop_event.set()
            self.append_log("Stop requested. The current run will finish its current polling cycle.")

    def skip_current(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            self.skip_event.set()
            self.append_log("Skip requested for the current NIC.")

    def process_worker_messages(self) -> None:
        try:
            while True:
                message = self.worker_queue.get_nowait()
                message_type = message["type"]

                if message_type == "log":
                    self.append_log(str(message["text"]))

                elif message_type == "status":
                    self.append_log(str(message["text"]))

                elif message_type == "current":
                    self.current_nic_var.set(f"Current NIC: {message['nic']}")

                elif message_type == "progress":
                    self.update_progress(
                        processed=int(message["processed"]),
                        total=int(message["total"]),
                        succeeded=int(message["succeeded"]),
                        skipped=int(message["skipped"]),
                        failed=int(message["failed"]),
                        elapsed=float(message["elapsed"]),
                    )

                elif message_type == "complete":
                    self.finish_run(message)

                elif message_type == "fatal":
                    self.set_running_state(False)
                    self.append_log(f"Fatal error: {message['text']}")
                    messagebox.showerror("Scraping Failed", str(message["text"]))

        except queue.Empty:
            pass

        if self.worker_thread and self.worker_thread.is_alive():
            self.after(150, self.process_worker_messages)

    def update_progress(
        self,
        processed: int,
        total: int,
        succeeded: int,
        skipped: int,
        failed: int,
        elapsed: float,
    ) -> None:
        ratio = (processed / total) if total else 0
        self.progress_var.set(ratio)
        self.progress_label_var.set(f"{processed} / {total} processed")
        self.summary_var.set(
            f"Success: {succeeded} | Skipped: {skipped} | Failed: {failed}"
        )

        if processed > 0 and total > processed:
            average_seconds = elapsed / processed
            remaining_seconds = int(average_seconds * (total - processed))
            minutes, seconds = divmod(remaining_seconds, 60)
            hours, minutes = divmod(minutes, 60)
            if hours:
                self.eta_var.set(f"ETA: {hours}h {minutes}m {seconds}s")
            elif minutes:
                self.eta_var.set(f"ETA: {minutes}m {seconds}s")
            else:
                self.eta_var.set(f"ETA: {seconds}s")
        elif processed == total and total:
            self.eta_var.set("ETA: 0s")
        else:
            self.eta_var.set("ETA: --")

    def finish_run(self, message: dict[str, object]) -> None:
        self.set_running_state(False)
        self.current_nic_var.set("Current NIC: -")

        output_path = str(message.get("output_path") or "")
        succeeded = int(message.get("succeeded", 0))
        skipped = int(message.get("skipped", 0))
        failed = int(message.get("failed", 0))
        stopped = bool(message.get("stopped"))

        if stopped:
            reason = str(message.get("reason") or "Stopped by user.")
            self.append_log(reason)
            if output_path:
                self.append_log(f"Partial results saved to: {output_path}")
                messagebox.showinfo(
                    "Scraping Stopped",
                    f"{reason}\n\nPartial results saved to:\n{output_path}",
                )
            else:
                messagebox.showinfo("Scraping Stopped", reason)
            return

        self.append_log(
            f"Completed run. Success: {succeeded}, Skipped: {skipped}, Failed: {failed}"
        )
        if output_path:
            self.append_log(f"Results saved to: {output_path}")
            messagebox.showinfo(
                "Scraping Complete",
                f"Run completed successfully.\n\nSaved file:\n{output_path}",
            )

    def on_close(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            should_close = messagebox.askyesno(
                "Close Application",
                "A scraping job is still running. Stop it and close the application?",
            )
            if not should_close:
                return
            self.stop_event.set()

        self.destroy()


if __name__ == "__main__":
    app = ScraperApp()
    app.mainloop()
