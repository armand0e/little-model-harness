---
name: spreadsheets
description: Create, edit, or read Excel (.xlsx) spreadsheets and CSV files
category: office
hint: Excel .xlsx and CSV: create, read, edit
---
Create Excel files by writing a small JSON spec, then converting with the helper script. Do NOT write openpyxl code yourself.

## Create an .xlsx
1. Write a JSON spec file with write_file (e.g. `budget.json`):
```json
{"sheets": [{
  "name": "Budget",
  "headers": ["Item", "Qty", "Unit Price", "Total"],
  "rows": [
    ["Laptop", 2, 1200, "=B2*C2"],
    ["Monitor", 4, 300, "=B3*C3"],
    ["TOTAL", "", "", "=SUM(D2:D3)"]
  ],
  "number_formats": {"C": "$#,##0.00", "D": "$#,##0.00"}
}]}
```
2. Convert: `run("python \"{dir}\scripts\make_xlsx.py\" budget.json budget.xlsx")`

Rules:
- Strings starting with `=` become live Excel formulas. Row 1 is the header, so data starts at row 2 — use that in formula references.
- `number_formats` (optional) maps column letters to Excel formats (`"0.0%"`, `"$#,##0.00"`, `"yyyy-mm-dd"`).
- Headers are styled and columns auto-sized automatically.
- Multiple sheets: add more objects to the `sheets` array.

## Read an .xlsx
`run("python \"{dir}\scripts\read_xlsx.py\" file.xlsx")` — shows all sheets. Add a sheet name and/or max rows: `read_xlsx.py file.xlsx Sheet1 50`.

## CSV files
Read/write CSVs directly with read_file / write_file.

## Edit an .xlsx
Read it, rebuild the full JSON spec with changes, convert to a new .xlsx file.
