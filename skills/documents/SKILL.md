---
name: documents
description: Create, edit, or read Word (.docx) documents and read PDFs
category: office
hint: Word .docx and PDF files: create, read, edit
---
Create Word documents by writing Markdown, then converting with the helper script. Do NOT write python-docx code yourself.

## Create a .docx
1. Write the content as a Markdown file with write_file (e.g. to the workspace, `report.md`).
2. Convert: `run("python \"{dir}\scripts\md2docx.py\" report.md report.docx")`

Supported Markdown: `#`..`####` headings, paragraphs, `-` bullets (indent 2 spaces to nest), `1.` numbered lists, `**bold**`, `*italic*`, `` `code` ``, tables (`| a | b |` with `|---|---|` separator), `>` block quotes, ``` code blocks, `---` on its own line = horizontal rule, `\newpage` on its own line = page break.

Tips for good documents:
- Start with a `#` title. Use `##` for sections.
- Business tone unless told otherwise. Include a short intro paragraph.

## Read a .docx
`run("python \"{dir}\scripts\read_docx.py\" file.docx")`

## Read a PDF
`run("python \"{dir}\scripts\read_pdf.py\" file.pdf")` — add a page range like `1-5` as a second argument for long PDFs.

## Edit a .docx
Read it, write a NEW complete Markdown file with the changes applied, convert it to a new .docx. Tell the user the new file path.
