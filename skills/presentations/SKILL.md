---
name: presentations
description: Create or read PowerPoint (.pptx) presentations
category: office
hint: PowerPoint .pptx decks: create and read
---
Create PowerPoint decks by writing a Markdown outline, then converting with the helper script. Do NOT write python-pptx code yourself.

## Create a .pptx
1. Write a Markdown outline with write_file (e.g. `deck.md`):
```
# Presentation Title
Optional subtitle line

## First Slide Title
- bullet point
- another point
  - sub-bullet (2-space indent)
Notes: optional speaker notes for this slide

## Second Slide Title
- more content
```
2. Convert: `run("python \"{dir}\scripts\md2pptx.py\" deck.md deck.pptx")`

Rules:
- The first `#` line becomes the title slide; the line right after it (if any) is the subtitle.
- Each `##` starts a new slide. Keep to 3-6 bullets per slide, short phrases not sentences.
- A line starting with `Notes:` becomes speaker notes for the current slide.
- A slide with NO bullets but one or more plain paragraphs becomes a statement slide (big centered text) — good for section breaks.

## Read a .pptx
`run("python \"{dir}\scripts\read_pptx.py\" file.pptx")`

## Edit a .pptx
Read it, write a new complete outline with changes, convert to a new .pptx.
