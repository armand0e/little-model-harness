"""Build an .xlsx from a JSON spec.

Usage: python make_xlsx.py spec.json output.xlsx
Spec: {"sheets": [{"name", "headers", "rows", "number_formats"?, "widths"?}]}
"""
import json
import re
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill("solid", fgColor="4472C4")
HEADER_FONT = Font(bold=True, color="FFFFFF")
MAX_SHEETS = 100
MAX_ROWS = 100_000
MAX_COLUMNS = 500
XML_INVALID_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def _sheet_name(value, used):
    name = re.sub(r"[\\/*?:\[\]]", "_", str(value or "Sheet")).strip("'")[:31]
    name = name or "Sheet"
    base = name
    suffix = 2
    while name.casefold() in used:
        marker = f" ({suffix})"
        name = base[:31 - len(marker)] + marker
        suffix += 1
    used.add(name.casefold())
    return name


def _clean_cell(value):
    return XML_INVALID_RE.sub("", value) if isinstance(value, str) else value


def build(spec_path, out_path):
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    if not isinstance(spec, dict) or not isinstance(spec.get("sheets", []), list):
        sys.exit("Error: spec must be an object with a 'sheets' array")
    if len(spec.get("sheets", [])) > MAX_SHEETS:
        sys.exit(f"Error: at most {MAX_SHEETS} sheets are supported")
    wb = Workbook()
    wb.remove(wb.active)
    used_names = set()
    for sheet in spec.get("sheets", []):
        if not isinstance(sheet, dict):
            sys.exit("Error: each sheet must be an object")
        ws = wb.create_sheet(title=_sheet_name(sheet.get("name"), used_names))
        headers = sheet.get("headers") or []
        rows = sheet.get("rows") or []
        if not isinstance(headers, list) or not isinstance(rows, list) \
                or not all(isinstance(row, list) for row in rows):
            sys.exit("Error: sheet headers and rows must be arrays")
        if len(rows) > MAX_ROWS:
            sys.exit(f"Error: a sheet may contain at most {MAX_ROWS:,} rows")
        if max([len(headers), *(len(row) for row in rows)], default=0) > MAX_COLUMNS:
            sys.exit(f"Error: a sheet may contain at most {MAX_COLUMNS} columns")
        if any(isinstance(value, (dict, list))
               for row in [headers, *rows] for value in row):
            sys.exit("Error: spreadsheet cells must be scalar JSON values")
        if headers:
            ws.append([_clean_cell(value) for value in headers])
            for cell in ws[1]:
                cell.fill = HEADER_FILL
                cell.font = HEADER_FONT
                cell.alignment = Alignment(horizontal="center")
            ws.freeze_panes = "A2"
        for row in rows:
            ws.append([_clean_cell(value) for value in row])
        # number formats per column letter
        number_formats = sheet.get("number_formats") or {}
        widths = sheet.get("widths") or {}
        if not isinstance(number_formats, dict) or not isinstance(widths, dict):
            sys.exit("Error: number_formats and widths must be objects")
        for col, fmt in number_formats.items():
            if not re.fullmatch(r"[A-Za-z]{1,3}", str(col)) or not isinstance(fmt, str):
                sys.exit("Error: number_formats must map column letters to strings")
            for cell in ws[col]:
                if cell.row > 1:
                    cell.number_format = fmt
        # column widths: explicit or auto-fit from content
        ncols = max([len(headers)] + [len(r) for r in rows] or [1])
        for idx in range(1, ncols + 1):
            letter = get_column_letter(idx)
            if letter in widths:
                try:
                    width = float(widths[letter])
                except (TypeError, ValueError):
                    sys.exit(f"Error: width for column {letter} must be numeric")
                ws.column_dimensions[letter].width = min(max(width, 1), 255)
            else:
                longest = max((len(str(c.value)) for c in ws[letter]
                               if c.value is not None), default=8)
                ws.column_dimensions[letter].width = min(max(longest + 2, 9), 45)
    if not wb.sheetnames:
        wb.create_sheet("Sheet1")
    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    print(f"Saved {out_path} ({len(wb.sheetnames)} sheet(s): {', '.join(wb.sheetnames)})")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python make_xlsx.py spec.json output.xlsx")
    build(sys.argv[1], sys.argv[2])
