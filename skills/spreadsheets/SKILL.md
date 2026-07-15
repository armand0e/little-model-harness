---
name: spreadsheets
description: Create, edit, or read Excel (.xlsx) spreadsheets and CSV files
category: office
hint: Excel .xlsx and CSV: create, read, edit
---
Create polished Excel workbooks by writing a small JSON spec, then
converting with the helper script. The script produces real Excel tables
(filters, banded rows), styled headers, totals, and charts. Do NOT write
openpyxl code yourself.

## Create an .xlsx
1. Write a JSON spec file with write_file (e.g. `budget.json`):
```json
{"sheets": [{
  "name": "Budget",
  "title": "2026 Personal Budget",
  "headers": ["Category", "Monthly", "Annual"],
  "rows": [
    ["Rent", 1800, "=B4*12"],
    ["Groceries", 520, "=B5*12"],
    ["Transport", 210, "=B6*12"]
  ],
  "totals": true,
  "number_formats": {"B": "$#,##0", "C": "$#,##0"},
  "chart": {"type": "bar", "labels": "A", "values": ["B"],
            "title": "Monthly spend by category"}
}]}
```
2. Convert: `run("python \"{dir}\scripts\make_xlsx.py\" budget.json budget.xlsx")`

Spec reference (per sheet — only name/headers/rows required):
- `title` — bold title block above the table (data then starts at row 3;
  with a title, the header is row 3 and data begins at row 4 — use those
  row numbers in `=` formulas).
- Strings starting with `=` become live Excel formulas.
- `totals: true` — appends a bold Total row that SUMs numeric columns.
- `number_formats` — column letter → Excel format (`"0.0%"`, `"$#,##0.00"`,
  `"yyyy-mm-dd"`).
- `chart` — `type` bar|line|pie, `labels` column letter, `values` list of
  column letters, optional `title`. Anchored beside the data.
- Headers, banding, filters, freeze panes, and column widths are automatic.

Make it genuinely good:
- Always set `title`, and put units in headers ("Revenue ($k)").
- Use live `=` formulas for anything derived — never precompute totals.
- Give every quantitative sheet `totals: true` and a `chart` when the data
  has one obvious story.
- Match `number_formats` to the data (currency, percent, dates).

## Read an .xlsx
`run("python \"{dir}\scripts\read_xlsx.py\" file.xlsx")` — shows all
sheets. Add a sheet name and/or max rows: `read_xlsx.py file.xlsx Sheet1 50`.

## CSV files
Read/write CSVs directly with read_file / write_file.

## Edit an .xlsx
Read it, rebuild the full JSON spec with changes, convert to a new .xlsx.
