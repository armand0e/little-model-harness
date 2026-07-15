---
name: documents
description: Create, edit, or read Word (.docx) documents and read PDFs
category: office
hint: Word .docx and PDF files: create, read, edit
---
Create professionally styled Word documents by writing Markdown, then
converting with the helper script. The script owns the design (cover page,
heading system, table styling, page numbers); you own the content. Do NOT
write python-docx code yourself.

## Create a .docx
1. Write the content as a Markdown file with write_file (e.g. `report.md`).
2. Convert: `run("python \"{dir}\scripts\md2docx.py\" report.md report.docx")`

Optional front-matter at the very top (any subset, order-free):
```
Title: Q2 Operations Review        ← generates a designed cover page
Subtitle: Prepared for the leadership team
Author: Jordan Alvarez
Date: July 15, 2026                ← defaults to today when omitted
Accent: #1F4E79                    ← heading/rule color (hex)
```

Supported Markdown: `#`..`####` headings, paragraphs, `-` bullets (2-space
indent nests), `1.` numbered lists, `**bold**`, `*italic*`, `` `code` ``,
tables (`| a | b |` + `|---|---|`), `>` block quotes (accent-ruled), fenced
code blocks (shaded), `---` horizontal rule, `\newpage` page break.
Tables get an accent header row and banded body rows; every page is
numbered automatically.

Make it genuinely good:
- Use front-matter for anything longer than a memo — the cover page reads
  as finished work.
- Open with a 2-4 sentence executive summary under the first `##`.
- Keep a real heading hierarchy (## sections, ### subsections); never skip
  levels. One idea per paragraph, 3-5 sentences.
- Put comparisons and figures in tables; put caveats in a block quote.
- Close with a "Next steps" or "Recommendations" section with a numbered
  list.

## Read a .docx
`run("python \"{dir}\scripts\read_docx.py\" file.docx")`

## Read a PDF
`run("python \"{dir}\scripts\read_pdf.py\" file.pdf")` — add a page range
like `1-5` as a second argument for long PDFs.

## Edit a .docx
Read it, write a NEW complete Markdown file with the changes applied,
convert it to a new .docx. Tell the user the new file path.
