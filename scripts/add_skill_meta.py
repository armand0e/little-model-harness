"""One-time: add category+hint frontmatter to every SKILL.md."""
import re
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / "skills"

META = {
    # name: (category, hint <=10 words)
    "documents": ("office", "Word .docx and PDF files: create, read, edit"),
    "spreadsheets": ("office", "Excel .xlsx and CSV: create, read, edit"),
    "presentations": ("office", "PowerPoint .pptx decks: create and read"),
    "computer": ("office", "control apps, windows, keyboard, mouse, screenshots"),
    "research": ("office", "web research with cited sources"),
    "clear-writing": ("writing", "make prose sharp: emails, reports, docs"),
    "communication-style": ("writing", "tone and framing for difficult messages"),
    "explaining-concepts": ("writing", "teach ideas clearly at any level"),
    "negotiation-and-persuasion": ("writing", "prepare and run negotiations"),
    "reading-comprehension": ("writing", "extract what a text actually says"),
    "ethical-reasoning": ("writing", "analyze dilemmas with ethical frameworks"),
    "coding": ("software", "write, edit, debug code in projects"),
    "api-and-interface-design": ("software", "design clean APIs and interfaces"),
    "code-writing-discipline": ("software", "habits for writing correct clean code"),
    "debugging-method": ("software", "systematic bug isolation and fixing"),
    "software-design-taste": ("software", "judgment for clean architecture"),
    "system-design-basics": ("software", "scalability, caching, queues, tradeoffs"),
    "thinking-method": ("reasoning", "master working style for nontrivial tasks"),
    "problem-decomposition": ("reasoning", "break big problems into tractable steps"),
    "answer-verification": ("reasoning", "check answers before finalizing"),
    "calibrated-uncertainty": ("reasoning", "express confidence honestly"),
    "causal-reasoning": ("reasoning", "does X cause Y; studies, confounders"),
    "cognitive-biases": ("reasoning", "spot and counter common biases"),
    "decision-analysis": ("reasoning", "structure choices, weigh options"),
    "deductive-logic": ("reasoning", "syllogisms, implication, valid inference"),
    "inference-types": ("reasoning", "deduction vs induction vs abduction"),
    "logic-puzzles": ("reasoning", "grid, knights-and-knaves, constraint puzzles"),
    "logical-fallacies": ("reasoning", "name and rebut bad arguments"),
    "probabilistic-reasoning": ("reasoning", "probability, Bayes, expected value"),
    "scientific-method": ("reasoning", "hypotheses, experiments, evidence"),
    "temporal-reasoning": ("reasoning", "dates, durations, timezones, scheduling"),
    "fermi-estimation": ("reasoning", "order-of-magnitude estimates from scratch"),
    "estimation-anchors": ("reasoning", "reference quantities for sanity checks"),
    "world-knowledge-anchors": ("reasoning", "key facts: populations, sizes, dates"),
    "mental-math": ("math", "reliable arithmetic tricks and verification"),
    "algebra-word-problems": ("math", "turn word problems into equations"),
    "percentages-ratios-rates": ("math", "percent change, ratios, rates"),
    "combinatorics-and-counting": ("math", "permutations, combinations, counting"),
    "geometry-essentials": ("math", "areas, volumes, angles, triangles"),
    "statistics-interpretation": ("math", "read stats claims without being fooled"),
    "unit-conversion": ("math", "convert units without mistakes"),
    "physics-intuition": ("science", "forces, energy, momentum sanity checks"),
    "chemistry-essentials": ("science", "stoichiometry, bonding, reactions"),
    "biology-essentials": ("science", "cells, genetics, evolution, physiology"),
    "game-design-fundamentals": ("creative", "mechanics, loops, balance, playtesting"),
    "javascript-game-dev": ("creative", "browser games: canvas, loops, physics"),
    "godot-essentials": ("creative", "Godot 4: nodes, scenes, GDScript"),
    "threejs-essentials": ("creative", "Three.js: scenes, meshes, lights"),
    "blender-modeling": ("creative", "Blender modeling, materials, rendering"),
    "blender-animation-rigging": ("creative", "Blender rigging and animation"),
    "animation-principles": ("creative", "the 12 principles, timing, easing"),
    "ui-ux-design": ("creative", "layout, hierarchy, flows users understand"),
}

for md in sorted(SKILLS.glob("*/SKILL.md")):
    name = md.parent.name
    if name not in META:
        print(f"!! no meta for {name}")
        continue
    cat, hint = META[name]
    text = md.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        print(f"!! bad frontmatter in {name}")
        continue
    meta_block = m.group(1)
    # drop any existing category/hint lines, then append fresh ones
    lines = [l for l in meta_block.splitlines()
             if not l.startswith(("category:", "hint:"))]
    lines += [f"category: {cat}", f"hint: {hint}"]
    new = "---\n" + "\n".join(lines) + "\n---\n" + text[m.end():]
    md.write_text(new, encoding="utf-8")
    print(f"ok {name} [{cat}]")

print("done")
