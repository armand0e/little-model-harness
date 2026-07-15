"""Dump a .docx as readable text. Usage: python read_docx.py file.docx"""
import sys

# Windows pipes default to a legacy code page; documents contain
# arbitrary Unicode, so never let printing crash the read.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

MAX_CHARS = 8000


def iter_blocks(doc):
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, doc)
        elif child.tag.endswith("}tbl"):
            yield Table(child, doc)


def main(path):
    doc = Document(path)
    out = []
    for block in iter_blocks(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                continue
            style = (block.style.name if block.style is not None else "").lower()
            if style.startswith("heading"):
                level = "".join(c for c in style if c.isdigit()) or "1"
                out.append("#" * int(level) + " " + text)
            elif "list" in style:
                out.append("- " + text)
            else:
                out.append(text)
        else:  # table
            for row in block.rows:
                out.append(" | ".join(c.text.strip() for c in row.cells))
            out.append("")
    text = "\n".join(out)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + f"\n...[truncated, {len(text):,} chars total]"
    print(text or "(empty document)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python read_docx.py file.docx")
    main(sys.argv[1])
