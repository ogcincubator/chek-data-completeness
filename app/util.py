import re
from pathlib import Path


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


def match_accept_header(header: str, options: list[str], def_value=None) -> str:
    if not header:
        return def_value

    options = [o.strip().lower().split('/') for o in options]
    for entry in sorted((e.strip().lower().split(';') for e in header.split(',')
                         if e.strip()), key=lambda e: float(e[1][2:]) if len(e) > 1 else 1.0):
        parts = entry[0].split('/')
        for option in options:
            if match_media_type(option, parts):
                return '/'.join(option)

    return def_value
