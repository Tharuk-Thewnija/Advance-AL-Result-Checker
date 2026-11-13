"""Small, validated preferences. Student data is never stored here."""
import json
import os
from pathlib import Path
import tempfile
from .checkpoints import app_data_dir
from .models import RunConfig
from .subjects import FIELDS, load_subjects


def preferences_path() -> Path:
    return app_data_dir() / 'preferences.json'


def _clean(value: dict) -> dict:
    defaults = {'appearance': 'System', 'subjects': ['20'], 'fields': [], 'year': '2025', 'timeout': 180}
    if not isinstance(value, dict):
        return defaults
    if value.get('appearance') in ('Light', 'Dark', 'System'):
        defaults['appearance'] = value['appearance']
    ids = {subject.id for subject in load_subjects()}
    for key, allowed in [('subjects', ids), ('fields', set(FIELDS))]:
        choices = value.get(key)
        if isinstance(choices, list) and all(isinstance(x, str) and x in allowed for x in choices):
            defaults[key] = list(dict.fromkeys(choices))
    if isinstance(value.get('year'), str) and value['year'].isdigit():
        defaults['year'] = value['year']
    if type(value.get('timeout')) is int and value['timeout'] > 0:
        defaults['timeout'] = value['timeout']
    return defaults


def load_preferences() -> dict:
    try:
        return _clean(json.loads(preferences_path().read_text(encoding='utf-8')))
    except (OSError, ValueError):
        return _clean({})


def save_preferences(preferences: dict) -> None:
    path = preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.preferences-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(_clean(preferences), stream, indent=2)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def validate_config(config: RunConfig) -> None:
    if not config.subject_ids:
        raise ValueError('Select at least one subject.')
    if set(config.subject_ids) - {s.id for s in load_subjects()}:
        raise ValueError('Unknown subject selection.')
    if set(config.fields) - set(FIELDS):
        raise ValueError('Unknown output field selection.')
    if not config.exam_year.isdigit():
        raise ValueError('Enter a numeric examination year.')
    if config.captcha_timeout <= 0:
        raise ValueError('CAPTCHA timeout must be greater than zero.')
    if not config.input_path.is_file():
        raise ValueError('Choose an existing Excel file.')
