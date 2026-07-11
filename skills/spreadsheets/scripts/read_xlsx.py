"""Dump .xlsx contents as text tables.

Usage: python read_xlsx.py file.xlsx [sheet_name] [max_rows]
"""
import sys

from openpyxl import load_workbook

MAX_CHARS = 8000


def main(path, sheet=None, max_rows=40):
    wb = load_workbook(path, data_only=False)
    names = [sheet] if sheet else wb.sheetnames
    out = []
    for name in names:
        if name not in wb.sheetnames:
            out.append(f"(no sheet named {name}; sheets: {', '.join(wb.sheetnames)})")
            continue
        ws = wb[name]
        out.append(f"=== Sheet: {name} ({ws.max_row} rows x {ws.max_column} cols) ===")
        for r, row in enumerate(ws.iter_rows(values_only=True), 1):
            if r > max_rows:
                out.append(f"...[{ws.max_row - max_rows} more rows]")
                break
            out.append(" | ".join("" if v is None else str(v) for v in row))
        out.append("")
    text = "\n".join(out)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n...[truncated; pass a sheet name / smaller max_rows]"
    print(text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python read_xlsx.py file.xlsx [sheet] [max_rows]")
    main(sys.argv[1],
         sys.argv[2] if len(sys.argv) > 2 else None,
         int(sys.argv[3]) if len(sys.argv) > 3 else 40)
