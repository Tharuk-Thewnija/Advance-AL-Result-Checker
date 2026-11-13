from __future__ import annotations
import re
import pandas as pd

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
    boundaries = ('Examination', 'Year', 'Candidate Name', 'Name', 'Index Number',
                  'NIC Number', 'NIC', 'School Name', 'School', 'District Rank',
                  'Island Rank', 'District', 'Z-Score', 'Z Score', 'Subject Stream',
                  'Stream', 'Medium', 'Subject Results', 'Subject', 'Results', 'Result')

    def is_label(value):
        return any(re.match(rf"^{re.escape(label)}(?=$|[\s:\-])", value, re.I)
                   for label in boundaries)

    for label in labels:
        for index, line in enumerate(lines):
            match = re.match(rf"^{re.escape(label)}(?=$|[\s:\-])(.*)$", line, re.I)
            if not match:
                continue
            suffix = match.group(1).strip(' :-\t')
            if label.upper() == 'DISTRICT' and suffix.upper().startswith('RANK'):
                continue
            if suffix:
                return suffix
            if index + 1 < len(lines) and not is_label(lines[index + 1]):
                return lines[index + 1]
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


def parse_legacy_results(text: str, subject_name: str) -> dict[str, str | None]:
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


def parse_results(text: str, subject_ids: tuple[str, ...] | str,
                  fields: tuple[str, ...] = ()) -> dict[str, str | None]:
    # Temporary compatibility for the original window during extraction.
    if isinstance(subject_ids, str):
        return parse_legacy_results(text, subject_ids)
    from .subjects import load_subjects, FIELDS
    subjects = {s.id: s for s in load_subjects()}
    if set(subject_ids) - subjects.keys() or set(fields) - set(FIELDS):
        raise ValueError('Unknown subject or output field')
    lines = normalize_lines(text)
    aliases = {}
    for subject in subjects.values():
        for label in (subject.name, *subject.aliases):
            aliases[normalize_subject_key(label)] = subject.id
    metadata_labels = {normalize_subject_key(field) for field in FIELDS}
    metadata_labels.update({'NAME', 'SCHOOL NAME', 'STREAM', 'EXAMINATION', 'YEAR', 'NIC', 'NIC NUMBER'})
    metadata_values = {i + 1 for i, line in enumerate(lines)
                       if normalize_subject_key(line.strip(' :-')) in metadata_labels}
    matches = []
    found = {}

    def valid_grade(subject_id, value):
        if re.fullmatch(r'A|B|C|S|F|W|AB|ABS|ABSENT|WITHHELD', value, re.I):
            return True
        return subject_id == '12' and bool(re.fullmatch(r'\d{1,3}', value)) and int(value) <= 100

    for index, line in enumerate(lines):
        if index in metadata_values:
            continue
        clean = re.sub(r'^\(?\d{1,2}[ABC]?\)?[.\s:-]+', '', line)
        subject_id = aliases.get(normalize_subject_key(clean))
        if subject_id:
            matches.append((index, subject_id))
            continue
        parts = clean.rsplit(' ', 1)
        if len(parts) == 2:
            subject_id = aliases.get(normalize_subject_key(parts[0]))
            if subject_id and valid_grade(subject_id, parts[1]):
                found[subject_id] = parts[1]
    # Handle each contiguous label group independently. Never attach the first
    # grade of an incomplete group to its last subject.
    cursor = 0
    while cursor < len(matches):
        end = cursor + 1
        while end < len(matches) and matches[end][0] == matches[end - 1][0] + 1:
            end += 1
        group = matches[cursor:end]
        grade_start = group[-1][0] + 1
        grades = lines[grade_start:grade_start + len(group)]
        if len(grades) == len(group) and all(valid_grade(sid, grade) for (_, sid), grade in zip(group, grades)):
            found.update((sid, grade) for (_, sid), grade in zip(group, grades))
        cursor = end
    result = {f'subject:{sid}': found.get(sid) for sid in subject_ids}
    labels = {'Candidate Name': ('Candidate Name', 'Name'), 'School': ('School Name', 'School'),
              'Z-Score': ('Z-Score', 'Z Score'), 'Subject Stream': ('Subject Stream', 'Stream')}
    result.update({field: find_labeled_value(lines, *labels.get(field, (field,))) for field in fields})
    return result


