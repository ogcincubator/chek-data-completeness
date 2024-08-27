import re
from pathlib import Path
from typing import Any


def is_xml(s: str) -> bool:
    return re.match(r'\s*<', s) is not None


def concat_files(input_files: list[str | Path], output_file: str | Path):
    with open(output_file, 'wb') as o:
        for fn in input_files:
            with open(fn, 'rb') as i:
                while chunk := i.read(1024 * 1024 * 10):  # 10MB chunks
                    o.write(chunk)


def match_media_type(a: list[str], b: list[str]):
    return (a[0] == '*' or b[0] == '*' or a[0] == b[0]) and (a[1] == '*' or b[1] == '*' or a[1] == b[1])


def parse_accept_entries(header: str) -> dict[str, Any]:
    entries = {}
    for e in header.split(','):
        parts = e.strip().split(';')
        if not parts:
            continue
        entry = {
            'q': 1.0
        }
        for part in parts[1:]:
            kv = part.split('=', 1)
            if kv[0] == 'q':
                kv[1] = float(kv[1])
            entry[kv[0]] = kv[1]
        entries[parts[0]] = entry
    return entries


def match_accept_header(header: str, options: list[str], def_value=None) -> str:
    if not header:
        return def_value

    options = [o.strip().lower().split('/') for o in options]
    entries = parse_accept_entries(header)
    for entry in sorted(entries.items(), key=lambda e: -e[1]['q']):
        parts = entry[0].split('/')
        for option in options:
            if match_media_type(option, parts):
                return '/'.join(option)

    return def_value
