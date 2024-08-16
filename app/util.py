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
