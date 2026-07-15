"""Dump PDF text. Usage: python read_pdf.py file.pdf [pages e.g. 1-5]"""
import sys

# Windows pipes default to a legacy code page; documents contain
# arbitrary Unicode, so never let printing crash the read.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import re

from pypdf import PdfReader

MAX_CHARS = 8000


def main(path, pages=None):
    reader = PdfReader(path)
    n = len(reader.pages)
    start, end = 1, n
    if pages:
        match = re.fullmatch(r"\s*(\d+)(?:\s*-\s*(\d+))?\s*", pages)
        if not match:
            sys.exit("Error: page selection must be a number or range like 1-5")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start < 1 or end < start or start > n:
            sys.exit(f"Error: page selection {pages!r} is outside this {n}-page PDF")
        end = min(end, n)
    out = []
    for i in range(start - 1, end):
        out.append(f"--- page {i + 1} of {n} ---")
        out.append(reader.pages[i].extract_text() or "(no extractable text)")
    text = "\n".join(out)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + f"\n...[truncated; ask for specific pages of {n}]"
    print(text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python read_pdf.py file.pdf [1-5]")
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
