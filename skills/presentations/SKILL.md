---
name: presentations
description: Create or read PowerPoint (.pptx) presentations with a designed theme system
category: office
hint: PowerPoint .pptx decks: create and read
---
Create designed PowerPoint decks by writing a Markdown outline and converting
it with the helper script. The script owns the design (themes, layouts,
typography, footers); you own the content. Do NOT write python-pptx code.

## Workflow
1. Write the outline with write_file (e.g. `deck.md`) using the syntax below.
2. Convert: `run("python \"{dir}\scripts\md2pptx.py\" deck.md deck.pptx")`

## Outline syntax
```
# Deck Title
Subtitle line (optional, right after the title)
Theme: ocean            ← ink | ocean | forest | slate | sunset
Footer: Acme Corp       ← optional, shown with page numbers
Date: July 2026         ← optional, defaults to the current month

## [section] Part One             ← dark divider slide, numbered 01, 02, …
One optional intro sentence.

## Normal content slide
Kicker: OPTIONAL LABEL            ← small accent label above the title
- 3 to 5 short bullets, parallel phrasing
  - sub-points use a 2-space indent
Notes: optional speaker notes

## [stats] Headline numbers       ← big number cards (2-4 items)
- $4.8M | Quarterly revenue, up 22% YoY
- 118% | Net revenue retention

## [table] Comparison title       ← styled table from a markdown table
| Plan | Price | Support |
|---|---|---|
| Basic | $10 | Email |

## [cols] Two columns             ← side-by-side cards; `---` splits them
Left heading (a plain line becomes the column heading)
- left bullet
---
Right heading
- right bullet

## [quote] Optional title         ← large pull-quote slide
> The quotation text.
— Person, Role

## [closing] Thank you            ← dark closing slide
contact@example.com · @handle
```
A `##` slide with no bullets and only plain lines becomes a big centered
statement slide — good for one-line takeaways.

## Make it genuinely good (content rules)
- Pick the theme for the topic: ocean/slate for business & tech, forest for
  sustainability/health, sunset/ink for creative or editorial decks.
- Give the deck rhythm: open with a `[section]`, alternate dense slides
  (bullets, table) with breathing room (`[stats]`, `[quote]`, statement).
- Bullets are phrases, not sentences: aim ≤ 12 words, parallel structure,
  concrete numbers. 3-5 per slide; never more than 7.
- Any deck with data deserves one `[stats]` slide (2-4 numbers max) and,
  when comparing options, one `[table]`.
- Use `Kicker:` to label a content slide's theme (PERFORMANCE, RISKS, …).
- End with `[closing]`, including a contact line when known.

## Read a .pptx
`run("python \"{dir}\scripts\read_pptx.py\" file.pptx")`

## Edit a .pptx
Read it, write a new complete outline with the changes, convert again.
