"""Skills: on-demand instruction packs.

Each skill is a folder under skills/ containing SKILL.md with a small
frontmatter block. Only `name: description` lines go in the system prompt;
the full body is injected only when the model calls the skill() tool.
This is the main context-saving mechanism of the harness.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import BUILTIN_SKILLS_DIR, USER_SKILLS_DIR
from .persistence import atomic_write_text


CATEGORY_ORDER = ["office", "software", "writing", "reasoning", "math",
                  "science", "creative", "other"]
MAX_SKILL_FILE_BYTES = 25_000

# Portable Codex-style SKILL.md frontmatter contains only name/description.
# Product-specific grouping therefore belongs in the catalog, not the files.
CATEGORY_SKILLS: dict[str, set[str]] = {
    "office": {
        "browser-control", "computer", "documents", "presentations",
        "research", "spreadsheets",
    },
    "software": {
        "api-and-interface-design", "code-writing-discipline", "coding",
        "debugging-method", "godot-essentials", "javascript-game-dev",
        "software-design-taste", "system-design-basics", "terminal-workflows",
    },
    "writing": {
        "clear-writing", "communication-style", "explaining-concepts",
        "negotiation-and-persuasion", "reading-comprehension",
    },
    "reasoning": {
        "answer-verification", "calibrated-uncertainty", "causal-reasoning",
        "cognitive-biases", "decision-analysis", "deductive-logic",
        "ethical-reasoning", "inference-types", "logic-puzzles",
        "logical-fallacies", "problem-decomposition", "temporal-reasoning",
        "thinking-method", "world-knowledge-anchors",
    },
    "math": {
        "algebra-word-problems", "combinatorics-and-counting",
        "estimation-anchors", "fermi-estimation", "geometry-essentials",
        "mental-math", "percentages-ratios-rates", "probabilistic-reasoning",
        "statistics-interpretation", "unit-conversion",
    },
    "science": {
        "biology-essentials", "chemistry-essentials", "physics-intuition",
        "scientific-method",
    },
    "creative": {
        "animation-principles", "blender-animation-rigging",
        "blender-modeling", "game-design-fundamentals", "threejs-essentials",
        "ui-ux-design",
    },
}

# Local models are inconsistent at voluntarily selecting a skill from a long
# tool/index list. These conservative routes preload only strongly indicated
# skills; the model can still call ``skill`` for anything else mid-turn.
SKILL_ROUTES: dict[str, tuple[str, ...]] = {
    "documents": (r"\b(docx|word document|microsoft word|pdf)\b",),
    "spreadsheets": (r"\b(xlsx|xls|spreadsheet|excel|csv|worksheet)\b",),
    "presentations": (r"\b(pptx|powerpoint|slide deck|presentation)\b",),
    "computer": (
        r"\b(keyboard|mouse|desktop app|control (?:an? )?app|click on (?:the )?screen|type into|take (?:a )?screenshot|screen capture)\b",
        r"\bfrom chrome\b|\b(?:existing|signed[- ]in|my).{0,20}\b(?:chrome|browser)\b",
    ),
    "browser-control": (
        r"\b(open|use|navigate|browse|click|type|log ?in|sign ?in|submit).{0,80}\b(browser|website|web ?app|gmail|chrome|page)\b",
        r"\b(browser|website|web ?app|gmail|page).{0,80}\b(open|click|navigate|type|read|summarize|submit)\b",
    ),
    "terminal-workflows": (
        r"\b(terminal|shell|powershell|bash|command line|cli)\b",
        r"\b(run|execute).{0,25}\b(command|tests?|build|script|npm|pip|git)\b",
    ),
    "research": (r"\b(research|sources?|citations?|look up|latest|current (?:news|price|version|information|events))\b",),
    "threejs-essentials": (r"\b(three\.?js|threejs|webgl|3d scene|3d model)\b",),
    "blender-modeling": (r"\b(blender|blend file|3d mesh|3d render)\b",),
    "blender-animation-rigging": (r"\b(blender).{0,30}\b(rig|animate|animation)\b",),
    "animation-principles": (r"\b(animate|animated|animation|motion|easing|tween)\b",),
    "javascript-game-dev": (r"\b(canvas game|browser game|javascript game)\b",),
    "godot-essentials": (r"\b(godot|gdscript)\b",),
    "game-design-fundamentals": (r"\b(game design|gameplay|game loop|level design)\b",),
    "ui-ux-design": (r"\b(ui|ux|user interface|frontend|web ?page|website|html|css|layout|responsive|visual design)\b",),
    "debugging-method": (r"\b(debug|bug|broken|failure|failing|crash|freeze|frozen|hang|stuck|glitch|regression|audit)\b",),
    "api-and-interface-design": (r"\b(api design|interface design|endpoint|openapi|sdk)\b",),
    "system-design-basics": (r"\b(system design|architecture|scalability|cache|queue|distributed)\b",),
    "software-design-taste": (r"\b(refactor|codebase|repository|repo|architecture|maintainability|technical debt|audit)\b",),
    "coding": (r"\b(code|coding|programming|implement|repository|repo|codebase|html|css|javascript|typescript|python|backend|frontend|app|harness|context engineering)\b",),
    "clear-writing": (r"\b(rewrite|edit prose|email|memo|report|documentation|readme)\b",),
    "statistics-interpretation": (r"\b(statistics?|statistical|p-value|confidence interval)\b",),
    "probabilistic-reasoning": (r"\b(probability|bayes|odds|expected value)\b",),
    "temporal-reasoning": (r"\b(timezone|time zone|date arithmetic|schedule|duration)\b",),
}


@dataclass
class Skill:
    name: str
    description: str
    body: str
    dir: Path
    category: str = "other"
    hint: str = ""


def _compact_hint(description: str) -> str:
    source = re.sub(
        r"^use\s+(?:whenever|when|for|at|as|to)\s+", "", description,
        flags=re.IGNORECASE)
    chosen: list[str] = []
    for word in source.split():
        candidate = " ".join([*chosen, word])
        if len(chosen) >= 8 or len(candidate) > 64:
            break
        chosen.append(word)
    return " ".join(chosen) or description[:80].rstrip()


def _inferred_category(name: str) -> str:
    return next((category for category, names in CATEGORY_SKILLS.items()
                 if name in names), "other")


def _parse_skill_md(path: Path) -> Skill | None:
    try:
        if path.stat().st_size > MAX_SKILL_FILE_BYTES:
            return None
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not m:
        return None
    meta, body = m.group(1), m.group(2).strip()
    fields = {}
    for line in meta.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip()
    name = (fields.get("name") or path.parent.name).strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,59}", name):
        return None
    desc = " ".join(fields.get("description", "").split())[:500]
    hint = _compact_hint(fields.get("hint") or desc)
    category = fields.get("category") or _inferred_category(name)
    if category not in CATEGORY_ORDER:
        category = "other"
    return Skill(name=name, description=desc, body=body, dir=path.parent,
                 category=category, hint=hint)


class SkillsManager:
    # user dir scanned last so learned skills shadow bundled ones by name
    def __init__(self, skills_dirs: tuple[Path, ...] =
                 (BUILTIN_SKILLS_DIR, USER_SKILLS_DIR)) -> None:
        self.skills_dirs = skills_dirs
        self.skills: dict[str, Skill] = {}
        self.loaded: set[str] = set()
        self.refresh()

    def refresh(self) -> None:
        self.skills.clear()
        for d in self.skills_dirs:
            if not d.is_dir():
                continue
            for md in sorted(d.glob("*/SKILL.md")):
                skill = _parse_skill_md(md)
                if skill:
                    self.skills[skill.name] = skill

    def index_text(self) -> str:
        """Grouped, hint-length index — this is all that lives in the
        system prompt. Full descriptions stay in the skill bodies."""
        groups: dict[str, list[Skill]] = {}
        for s in self.skills.values():
            groups.setdefault(s.category, []).append(s)
        lines = []
        for cat in CATEGORY_ORDER:
            if cat not in groups:
                continue
            lines.append(f"[{cat}]")
            lines.extend(f"- {s.name}: {s.hint}"
                         for s in sorted(groups[cat], key=lambda s: s.name))
        return "\n".join(lines)

    def recommend(self, text: str, limit: int = 3) -> list[str]:
        """Select strongly relevant skills without relying on model tool use.

        Exact skill-name mentions win, followed by curated domain routes in
        declaration order. Generic coding routes come after specialized ones.
        """
        low = " ".join(text.lower().split())
        if limit <= 0 or not low:
            return []
        matches: list[tuple[int, int, int, str]] = []
        route_order = {name: order for order, name in enumerate(SKILL_ROUTES)}
        for name in self.skills:
            aliases = {name, name.replace("-", " ")}
            if any(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", low)
                   for alias in aliases):
                matches.append((1, 0, route_order.get(name, -1), name))
        for order, (name, patterns) in enumerate(SKILL_ROUTES.items()):
            if name not in self.skills:
                continue
            count = sum(1 for pattern in patterns if re.search(pattern, low))
            if count:
                matches.append((0, count, order, name))
        matches.sort(key=lambda item: (-item[0], -item[1], item[2]))
        chosen = []
        for _, _, _, name in matches:
            if name not in chosen:
                chosen.append(name)
            if len(chosen) >= max(0, limit):
                break
        return chosen

    def activate(self, name: str) -> bool:
        name = name.strip().lower()
        if name not in self.skills:
            return False
        self.loaded.add(name)
        return True

    def active_text(self) -> str:
        blocks = []
        for name in sorted(self.loaded):
            skill = self.skills.get(name)
            if skill:
                blocks.append(
                    f"[active skill: {name}]\n"
                    + skill.body.replace("{dir}", str(skill.dir)))
        return "\n\n".join(blocks)

    def load(self, name: str) -> str:
        name = name.strip().lower()
        skill = self.skills.get(name)
        if not skill:
            names = ", ".join(self.skills)
            return f"Error: no skill named '{name}'. Available: {names}"
        if name in self.loaded:
            return (f"[skill: {name}] is already active for this turn; its "
                    "instructions are in the system prompt.")
        self.loaded.add(name)
        # {dir} lets skill bodies reference their own helper scripts portably.
        return (f"[skill: {name}]\n"
                + skill.body.replace("{dir}", str(skill.dir)))

    def reset(self) -> None:
        self.loaded.clear()


def save_skill(name: str, hint: str, content: str,
               category: str | None = None, append: bool = False) -> str:
    """The learning loop: the agent persists what it learned as a skill."""
    name = re.sub(r"[^a-z0-9-]", "-", name.strip().lower()).strip("-")
    if not name or len(name) > 60:
        return "Error: give a short kebab-case skill name."
    if category is not None and category not in CATEGORY_ORDER:
        category = "other"
    hint = " ".join(hint.split()[:10])[:80]
    if not hint:
        return "Error: give a short hint for the skills index."
    content = content.strip()
    if not content:
        return "Error: content is empty."
    # learned skills always land in the writable user dir; extending a
    # bundled skill writes a shadowing copy there (install dir stays clean)
    path = USER_SKILLS_DIR / name / "SKILL.md"
    src = path if path.exists() else BUILTIN_SKILLS_DIR / name / "SKILL.md"
    if src.exists():
        existing = _parse_skill_md(src)
        if append and existing:
            body = existing.body + "\n\n" + content
            desc = existing.description
            category = existing.category
            hint = hint or existing.hint
        else:
            body = content
            desc = existing.description if existing else hint
            if existing and category is None:
                category = existing.category
    else:
        body, desc = content, hint
    category = category or "other"
    if len(body) > 8000:
        return ("Error: skill body would exceed 8000 chars — trim it or "
                "split into two skills.")
    try:
        atomic_write_text(
            path,
            f"---\nname: {name}\ndescription: {desc}\ncategory: {category}\n"
            f"hint: {hint}\n---\n{body}\n",
        )
    except OSError as e:
        return f"Error: could not save skill: {e}"
    verb = "Extended" if append and src.exists() else "Saved"
    return f"{verb} skill '{name}' — it is now in the skills index for every future session."
