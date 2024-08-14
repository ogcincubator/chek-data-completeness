import re


def is_xml(s: str) -> bool:
    return re.match(r'\s*<', s) is not None
