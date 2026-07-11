"""Convert Markdown to a styled .docx.

Usage: python md2docx.py input.md output.docx
"""
import re
import sys

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

BOLD_RE = re.compile(r"(\*\*.+?\*\*|\*.+?\*|`.+?`)")


def add_runs(paragraph, text):
    """Render **bold**, *italic* and `code` inline."""
    for part in BOLD_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            paragraph.add_run(part[2:-2]).bold = True
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            paragraph.add_run(part[1:-1]).italic = True
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            run = paragraph.add_run(part[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(10)
        else:
            paragraph.add_run(part)


def is_table_sep(line):
    return bool(re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", line)) and "-" in line


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def convert(md_path, docx_path):
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    lines = open(md_path, encoding="utf-8").read().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # fenced code block
        if stripped.startswith("```"):
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            p = doc.add_paragraph()
            run = p.add_run("\n".join(code))
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
            continue

        # table
        if stripped.startswith("|") and i + 1 < len(lines) and is_table_sep(lines[i + 1]):
            headers = split_row(stripped)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            table = doc.add_table(rows=1, cols=len(headers))
            table.style = "Light Grid Accent 1"
            for j, h in enumerate(headers):
                cell = table.rows[0].cells[j]
                cell.text = ""
                add_runs(cell.paragraphs[0], f"**{h.strip('*')}**")
            for row in rows:
                cells = table.add_row().cells
                for j, val in enumerate(row[:len(headers)]):
                    cells[j].text = ""
                    add_runs(cells[j].paragraphs[0], val)
            continue

        # explicit page break
        if stripped == "\\newpage":
            doc.add_page_break()
            i += 1
            continue

        # horizontal rule
        if stripped in ("---", "***", "___"):
            p = doc.add_paragraph()
            pPr = p._p.get_or_add_pPr()
            from docx.oxml.ns import qn
            pBdr = pPr.makeelement(qn("w:pBdr"), {})
            bottom = pPr.makeelement(qn("w:bottom"), {
                qn("w:val"): "single", qn("w:sz"): "6",
                qn("w:space"): "1", qn("w:color"): "auto"})
            pBdr.append(bottom)
            pPr.append(pBdr)
            i += 1
            continue

        # heading
        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            doc.add_heading(m.group(2).strip(), level=len(m.group(1)))
            i += 1
            continue

        # block quote
        if stripped.startswith(">"):
            p = doc.add_paragraph(style="Intense Quote")
            add_runs(p, stripped.lstrip("> ").strip())
            i += 1
            continue

        # bullet / numbered list (2-space indent nests one level)
        m = re.match(r"^(\s*)([-*]|\d+[.)])\s+(.*)$", line)
        if m:
            indent = len(m.group(1)) // 2
            numbered = m.group(2)[0].isdigit()
            base = "List Number" if numbered else "List Bullet"
            style_name = base + ("" if indent == 0 else f" {min(indent + 1, 3)}")
            try:
                p = doc.add_paragraph(style=style_name)
            except KeyError:
                p = doc.add_paragraph(style=base)
            add_runs(p, m.group(3))
            i += 1
            continue

        # plain paragraph (merge soft-wrapped lines)
        para = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(\s*([-*]|\d+[.)])\s|#{1,4}\s|\||>|```)", lines[i]):
            para.append(lines[i].strip())
            i += 1
        p = doc.add_paragraph()
        add_runs(p, " ".join(para))

    doc.save(docx_path)
    print(f"Saved {docx_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python md2docx.py input.md output.docx")
    convert(sys.argv[1], sys.argv[2])
