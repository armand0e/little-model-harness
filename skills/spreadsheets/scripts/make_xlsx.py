"""Build an .xlsx from a JSON spec.

Usage: python make_xlsx.py spec.json output.xlsx
Spec: {"sheets": [{"name", "headers", "rows", "number_formats"?, "widths"?}]}
"""
import json
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill("solid", fgColor="4472C4")
HEADER_FONT = Font(bold=True, color="FFFFFF")


def build(spec_path, out_path):
    spec = json.load(open(spec_path, encoding="utf-8"))
    wb = Workbook()
    wb.remove(wb.active)
    for sheet in spec.get("sheets", []):
        ws = wb.create_sheet(title=str(sheet.get("name", "Sheet"))[:31])
        headers = sheet.get("headers") or []
        rows = sheet.get("rows") or []
        if headers:
            ws.append(headers)
            for cell in ws[1]:
                cell.fill = HEADER_FILL
                cell.font = HEADER_FONT
                cell.alignment = Alignment(horizontal="center")
            ws.freeze_panes = "A2"
        for row in rows:
            ws.append(row)
        # number formats per column letter
        for col, fmt in (sheet.get("number_formats") or {}).items():
            for cell in ws[col]:
                if cell.row > 1:
                    cell.number_format = fmt
        # column widths: explicit or auto-fit from content
        widths = sheet.get("widths") or {}
        ncols = max([len(headers)] + [len(r) for r in rows] or [1])
        for idx in range(1, ncols + 1):
            letter = get_column_letter(idx)
            if letter in widths:
                ws.column_dimensions[letter].width = widths[letter]
            else:
                longest = max((len(str(c.value)) for c in ws[letter]
                               if c.value is not None), default=8)
                ws.column_dimensions[letter].width = min(max(longest + 2, 9), 45)
    if not wb.sheetnames:
        wb.create_sheet("Sheet1")
    wb.save(out_path)
    print(f"Saved {out_path} ({len(wb.sheetnames)} sheet(s): {', '.join(wb.sheetnames)})")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python make_xlsx.py spec.json output.xlsx")
    build(sys.argv[1], sys.argv[2])
