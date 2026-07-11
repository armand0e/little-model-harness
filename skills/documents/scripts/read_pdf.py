"""Dump PDF text. Usage: python read_pdf.py file.pdf [pages e.g. 1-5]"""
import sys

from pypdf import PdfReader

MAX_CHARS = 8000


def main(path, pages=None):
    reader = PdfReader(path)
    n = len(reader.pages)
    start, end = 1, n
    if pages:
        if "-" in pages:
            a, b = pages.split("-", 1)
            start, end = int(a), min(int(b), n)
        else:
            start = end = int(pages)
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
