from dataclasses import dataclass
from pathlib import Path
import pandas as pd


@dataclass(frozen=True)
class RunConfig:
    input_path: Path
    subject_ids: tuple[str, ...]
    fields: tuple[str, ...]
    exam_year: str
    captcha_timeout: int
    output_dir: Path


@dataclass(frozen=True)
class InputWorkbook:
    path: Path
    content_hash: str
    sheet_name: str
    frame: pd.DataFrame


@dataclass(frozen=True)
class RowResult:
    position: int
    status: str
    values: dict[str, str | None]
    note: str = ''


@dataclass(frozen=True)
class WorkerEvent:
    kind: str
    payload: dict
