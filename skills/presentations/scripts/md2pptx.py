"""Convert a Markdown outline to a .pptx deck.

Usage: python md2pptx.py outline.md output.pptx
"""
import re
import sys

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

ACCENT = RGBColor(0x2F, 0x54, 0x96)
DARK = RGBColor(0x33, 0x33, 0x33)


def clean(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    return re.sub(r"\*(.+?)\*", r"\1", text).strip()


def parse(md_path):
    lines = open(md_path, encoding="utf-8").read().splitlines()
    deck = {"title": "", "subtitle": "", "slides": []}
    slide = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# ") and not deck["title"]:
            deck["title"] = clean(stripped[2:])
            continue
        if stripped.startswith("## "):
            slide = {"title": clean(stripped[3:]), "bullets": [],
                     "paras": [], "notes": []}
            deck["slides"].append(slide)
            continue
        if slide is None:
            if deck["title"] and not deck["subtitle"]:
                deck["subtitle"] = clean(stripped)
            continue
        if stripped.lower().startswith("notes:"):
            slide["notes"].append(stripped[6:].strip())
            continue
        m = re.match(r"^(\s*)[-*]\s+(.*)$", line)
        if m:
            slide["bullets"].append((len(m.group(1)) // 2, clean(m.group(2))))
        else:
            slide["paras"].append(clean(stripped))
    return deck


def build(md_path, out_path):
    deck = parse(md_path)
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    def textbox(slide, left, top, width, height):
        box = slide.shapes.add_textbox(left, top, width, height)
        box.text_frame.word_wrap = True
        return box.text_frame

    # title slide
    if deck["title"]:
        s = prs.slides.add_slide(blank)
        tf = textbox(s, Inches(1), Inches(2.7), Inches(11.3), Inches(1.6))
        p = tf.paragraphs[0]
        p.text = deck["title"]
        p.font.size = Pt(44)
        p.font.bold = True
        p.font.color.rgb = ACCENT
        p.alignment = PP_ALIGN.CENTER
        if deck["subtitle"]:
            p2 = tf.add_paragraph()
            p2.text = deck["subtitle"]
            p2.font.size = Pt(20)
            p2.font.color.rgb = DARK
            p2.alignment = PP_ALIGN.CENTER

    for sl in deck["slides"]:
        s = prs.slides.add_slide(blank)
        # title bar
        tf = textbox(s, Inches(0.6), Inches(0.4), Inches(12.1), Inches(1.0))
        p = tf.paragraphs[0]
        p.text = sl["title"]
        p.font.size = Pt(30)
        p.font.bold = True
        p.font.color.rgb = ACCENT

        if sl["bullets"]:
            tf = textbox(s, Inches(0.9), Inches(1.7), Inches(11.5), Inches(5.2))
            first = True
            for level, text in sl["bullets"]:
                p = tf.paragraphs[0] if first else tf.add_paragraph()
                first = False
                p.text = ("• " if level == 0 else "– ") + text
                p.level = min(level, 4)
                p.font.size = Pt(20 if level == 0 else 17)
                p.font.color.rgb = DARK
                p.space_after = Pt(10)
        elif sl["paras"]:
            tf = textbox(s, Inches(1.4), Inches(2.9), Inches(10.5), Inches(2.5))
            first = True
            for text in sl["paras"]:
                p = tf.paragraphs[0] if first else tf.add_paragraph()
                first = False
                p.text = text
                p.font.size = Pt(28)
                p.font.color.rgb = DARK
                p.alignment = PP_ALIGN.CENTER

        if sl["notes"]:
            s.notes_slide.notes_text_frame.text = " ".join(sl["notes"])

    prs.save(out_path)
    print(f"Saved {out_path} ({len(prs.slides.slides if hasattr(prs.slides, 'slides') else prs.slides._sldIdLst)} slides)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python md2pptx.py outline.md output.pptx")
    build(sys.argv[1], sys.argv[2])
