"""Sourced subject catalogue; stable IDs are examination subject codes."""
from dataclasses import dataclass
from functools import lru_cache
import json
import re
from pathlib import Path

CATALOGUE_PATH = Path(__file__).parent / 'data' / 'subjects.json'


@dataclass(frozen=True)
class Subject:
    id: str
    name: str
    code: str | None
    aliases: tuple[str, ...]


@lru_cache(maxsize=1)
def catalogue_metadata() -> dict:
    return json.loads(CATALOGUE_PATH.read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def load_subjects() -> tuple[Subject, ...]:
    return tuple(Subject(s['id'], s['name'], s['code'], tuple(s['aliases']))
                 for s in catalogue_metadata()['subjects'])


def search_subjects(query: str) -> tuple[Subject, ...]:
    query = query.strip().casefold()
    if re.fullmatch(r'\d{1,2}[abc]?', query):
        code = query.upper().zfill(2)
        exact = tuple(s for s in load_subjects() if s.code == code)
        return exact or tuple(s for s in load_subjects() if (s.code or '').startswith(code))
    words = re.findall(r'[a-z0-9]+', query.replace('&', ' and '))
    return tuple(s for s in load_subjects() if all(word in
                 ' '.join((s.name, s.code or '', *s.aliases)).casefold() for word in words))


FIELDS = ('Candidate Name', 'Index Number',
          'District Rank', 'Island Rank', 'Z-Score', 'Subject Stream')
