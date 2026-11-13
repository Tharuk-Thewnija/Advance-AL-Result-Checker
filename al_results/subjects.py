"""Sourced subject catalogue; stable IDs are examination subject codes."""
from dataclasses import dataclass
from functools import lru_cache
import json
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
    return tuple(s for s in load_subjects() if query in
                 ' '.join((s.name, s.code or '', *s.aliases)).casefold())


FIELDS = ('Candidate Name', 'School', 'District', 'Medium', 'Index Number',
          'District Rank', 'Island Rank', 'Z-Score', 'Subject Stream')
