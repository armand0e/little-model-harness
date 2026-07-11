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


CATEGORY_ORDER = ["office", "software", "writing", "reasoning", "math",
                  "science", "creative", "other"]


@dataclass
class Skill:
    name: str
    description: str
    body: str
    dir: Path
    category: str = "other"
    hint: str = ""


def _parse_skill_md(path: Path) -> Skill | None:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not m:
        return None
    meta, body = m.group(1), m.group(2).strip()
    fields = {}
    for line in meta.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip()
    name = fields.get("name") or path.parent.name
    desc = fields.get("description", "")
    hint = fields.get("hint") or " ".join(desc.split()[:10])
    category = fields.get("category", "other")
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

    def load(self, name: str) -> str:
        name = name.strip().lower()
        skill = self.skills.get(name)
        if not skill:
            names = ", ".join(self.skills)
            return f"Error: no skill named '{name}'. Available: {names}"
        self.loaded.add(name)
        # {dir} lets skill bodies reference their own helper scripts portably.
        return (f"[skill: {name}]\n"
                + skill.body.replace("{dir}", str(skill.dir)))

    def reset(self) -> None:
        self.loaded.clear()


def save_skill(name: str, hint: str, content: str,
               category: str = "other", append: bool = False) -> str:
    """The learning loop: the agent persists what it learned as a skill."""
    name = re.sub(r"[^a-z0-9-]", "-", name.strip().lower()).strip("-")
    if not name or len(name) > 60:
        return "Error: give a short kebab-case skill name."
    if category not in CATEGORY_ORDER:
        category = "other"
    hint = " ".join(hint.split())[:80]
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
    else:
        body, desc = content, hint
    if len(body) > 8000:
        return ("Error: skill body would exceed 8000 chars — trim it or "
                "split into two skills.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\ndescription: {desc}\ncategory: {category}\n"
        f"hint: {hint}\n---\n{body}\n", encoding="utf-8")
    verb = "Extended" if append and path.exists() else "Saved"
    return f"{verb} skill '{name}' — it is now in the skills index for every future session."
