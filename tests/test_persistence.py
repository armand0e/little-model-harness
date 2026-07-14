from __future__ import annotations

import json
from pathlib import Path

import pytest

import harness.config as config
import harness.memory as memory
import harness.skills as skills


def test_settings_reject_non_object_json_and_save_atomically(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "USER_SETTINGS", path)
    path.write_text("[]", encoding="utf-8")
    assert config.load_user_settings() == {}
    config.save_user_settings({"temperature": 0.3})
    assert json.loads(path.read_text(encoding="utf-8")) == {"temperature": 0.3}
    assert not list(tmp_path.glob("*.tmp"))

    path.write_text('{"workspace": {"not": "a path"}}', encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    assert config.get_default_workspace() == tmp_path / "data" / "workspace"


def test_memory_is_atomic_and_history_search_ignores_corrupt_shapes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    memory_file = tmp_path / "memory.md"
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr(memory, "MEMORY_FILE", memory_file)
    monkeypatch.setattr(memory, "SESSIONS_DIR", sessions)
    assert memory.remember("prefers concise answers").startswith("Remembered")
    assert "prefers concise" in memory.load_memory()
    assert not list(tmp_path.glob("*.tmp"))

    (sessions / "bad.json").write_text(json.dumps({
        "title": None, "updated": 10**1000,
        "display": [None, {"text": "needle in a valid item"}],
    }), encoding="utf-8")
    result = memory.search_sessions("needle")
    assert "unknown date" in result
    assert "needle" in result


def test_skill_save_preserves_metadata_and_limits_index_hint(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    builtins = tmp_path / "builtins"
    users = tmp_path / "users"
    base = builtins / "base" / "SKILL.md"
    base.parent.mkdir(parents=True)
    base.write_text(
        "---\nname: base\ndescription: Base skill\ncategory: software\n"
        "hint: base hint\n---\nOriginal body\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(skills, "BUILTIN_SKILLS_DIR", builtins)
    monkeypatch.setattr(skills, "USER_SKILLS_DIR", users)

    extended = skills.save_skill("base", "updated hint", "Extra", append=True)
    assert extended.startswith("Extended")
    parsed = skills._parse_skill_md(users / "base" / "SKILL.md")
    assert parsed is not None
    assert parsed.category == "software"
    assert "Original body" in parsed.body and "Extra" in parsed.body

    replaced = skills.save_skill("base", "replacement hint", "Replacement")
    assert replaced.startswith("Saved")
    parsed = skills._parse_skill_md(users / "base" / "SKILL.md")
    assert parsed is not None and parsed.category == "software"

    result = skills.save_skill(
        "new-skill", "one two three four five six seven eight nine ten eleven twelve",
        "Body",
    )
    assert result.startswith("Saved")
    parsed = skills._parse_skill_md(users / "new-skill" / "SKILL.md")
    assert parsed is not None
    assert 0 < len(parsed.hint.split()) <= 10
    assert skills.save_skill("empty", "", "Body").startswith("Error")


def test_entire_bundled_skill_catalog_is_valid_and_unique():
    paths = sorted(skills.BUILTIN_SKILLS_DIR.glob("*/SKILL.md"))
    parsed = [skills._parse_skill_md(path) for path in paths]
    assert paths
    assert all(skill is not None for skill in parsed)
    valid = [skill for skill in parsed if skill is not None]
    assert len({skill.name for skill in valid}) == len(valid)
    assert all(skill.description and skill.body for skill in valid)
    assert all(0 < len(skill.hint.split()) <= 10 for skill in valid)
    assert all(skill.category in skills.CATEGORY_ORDER for skill in valid)


def test_standard_skill_metadata_gets_compact_local_grouping(tmp_path: Path):
    skill_dir = tmp_path / "browser-control"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: browser-control\n"
        "description: Use when operating a public website with semantic refs "
        "and screenshots for verification.\n---\nInstructions\n",
        encoding="utf-8")
    parsed = skills._parse_skill_md(skill_dir / "SKILL.md")
    assert parsed is not None
    assert parsed.category == "office"
    assert parsed.hint.startswith("operating a public website")
    assert not parsed.hint.endswith("verificatio")


def test_browser_and_terminal_skills_route_to_first_class_tools():
    manager = skills.SkillsManager()
    browser_matches = manager.recommend("open Gmail in the browser and click inbox")
    assert "browser-control" in browser_matches
    assert "computer" not in browser_matches
    assert "terminal-workflows" in manager.recommend(
        "run the test suite from the terminal")


def test_corrupt_oversized_prompt_inputs_are_bounded(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    settings = tmp_path / "settings.json"
    settings.write_text('{"temperature": 0.2}', encoding="utf-8")
    monkeypatch.setattr(config, "USER_SETTINGS", settings)
    monkeypatch.setattr(config, "MAX_SETTINGS_BYTES", 2)
    assert config.load_user_settings() == {}

    memory_file = tmp_path / "memory.md"
    memory_file.write_text("too large", encoding="utf-8")
    monkeypatch.setattr(memory, "MEMORY_FILE", memory_file)
    monkeypatch.setattr(memory, "MAX_MEMORY_FILE_BYTES", 2)
    assert "omitted" in memory.load_memory()
    assert memory.remember("new fact").startswith("Error")

    skill_file = tmp_path / "huge" / "SKILL.md"
    skill_file.parent.mkdir()
    skill_file.write_text(
        "---\nname: huge\ndescription: x\n---\nbody", encoding="utf-8")
    monkeypatch.setattr(skills, "MAX_SKILL_FILE_BYTES", 2)
    assert skills._parse_skill_md(skill_file) is None
