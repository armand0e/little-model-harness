"""Configuration for the harness.

Everything is tuned for a small local model with a 32k context window.
Values can be overridden with environment variables (LMH_*) or a
harness.toml file in the project root.

Paths: the install dir (ROOT) is treated as read-only — packaged builds
live in Program Files. Everything the harness writes (sessions, settings,
memory, learned skills, the browser profile, the default workspace) lives
in a per-user data dir (DATA_DIR).
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

if getattr(sys, "frozen", False):
    # PyInstaller bundle: data files (web/, skills/) sit in the extraction
    # dir (_MEIPASS for onefile, <app>/_internal for onedir)
    ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    ROOT = Path(__file__).resolve().parent.parent
BUILTIN_SKILLS_DIR = ROOT / "skills"


def _default_data_dir() -> Path:
    if os.environ.get("LMH_DATA_DIR"):
        return Path(os.environ["LMH_DATA_DIR"]).expanduser().resolve()
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "LittleHarness"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "LittleHarness"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "LittleHarness"


DATA_DIR = _default_data_dir()
SESSIONS_DIR = DATA_DIR / "sessions"
USER_SETTINGS = DATA_DIR / "user_settings.json"
MEMORY_FILE = DATA_DIR / "memory.md"
USER_SKILLS_DIR = DATA_DIR / "skills"          # save_skill writes here
BROWSER_PROFILE_DIR = DATA_DIR / "browser-profile"


def _migrate_legacy_data() -> None:
    """One-time move of data that older versions kept in the install dir."""
    if DATA_DIR == ROOT:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    pairs = (
        (ROOT / "sessions", SESSIONS_DIR),
        (ROOT / "user_settings.json", USER_SETTINGS),
        (ROOT / "memory.md", MEMORY_FILE),
        (ROOT / "browser-profile", BROWSER_PROFILE_DIR),
    )
    for legacy, new in pairs:
        try:
            if legacy.exists() and not new.exists():
                shutil.move(str(legacy), str(new))
        except OSError:
            pass  # locked or unwritable — the harness still works from DATA_DIR


_migrate_legacy_data()


def load_user_settings() -> dict:
    try:
        return json.loads(USER_SETTINGS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_user_settings(updates: dict) -> None:
    data = {**load_user_settings(), **updates}
    USER_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    USER_SETTINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")


# The DEFAULT workspace is what new chats inherit; each chat can then point
# its own workspace anywhere. Resolution: env var > saved setting > appdata.
def get_default_workspace() -> Path:
    if os.environ.get("LMH_WORKSPACE"):
        return Path(os.environ["LMH_WORKSPACE"])
    saved = load_user_settings().get("workspace")
    if saved:
        return Path(saved)
    return DATA_DIR / "workspace"


def set_default_workspace(path: str) -> Path:
    """Point the default workspace at any folder; creates it if missing."""
    p = Path(os.path.expandvars(os.path.expanduser(path))).resolve()
    p.mkdir(parents=True, exist_ok=True)
    save_user_settings({"workspace": str(p)})
    return p


@dataclass
class Config:
    base_url: str = "http://localhost:1234/v1"
    model: str = "llm"
    api_key: str = "not-needed"

    # Sampling — low temperature keeps small models on-task for tool use.
    temperature: float = 0.4
    max_output_tokens: int = 4096

    # Context budget (tokens). The window is auto-clamped to the model
    # server's real n_ctx at runtime.
    context_window: int = 32768
    # Keep this much headroom free for generation: compaction fires (even
    # mid-turn) when the conversation reaches window - reserve.
    output_reserve: int = 16384
    # Derived at runtime from window/reserve; kept for display/config.
    compact_threshold: int = 16384
    compact_target: int = 8192
    # Hard cap for a single tool result (characters).
    tool_result_max_chars: int = 6000
    # Tool results older than this many user turns get collapsed.
    tool_result_keep_turns: int = 2

    # Agent loop. High on purpose: real agentic work (debugging, multi-file
    # edits) legitimately takes many steps — context pressure is handled by
    # mid-turn compaction, so this is only a runaway guard.
    max_iterations: int = 100
    request_timeout: float = 600.0

    extra: dict = field(default_factory=dict)


def load_config() -> Config:
    cfg = Config()
    toml_path = ROOT / "harness.toml"
    if toml_path.exists():
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        for k, v in data.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
            else:
                cfg.extra[k] = v
    # Env overrides
    if os.environ.get("LMH_BASE_URL"):
        cfg.base_url = os.environ["LMH_BASE_URL"]
    if os.environ.get("LMH_MODEL"):
        cfg.model = os.environ["LMH_MODEL"]
    if os.environ.get("LMH_TEMPERATURE"):
        cfg.temperature = float(os.environ["LMH_TEMPERATURE"])
    # settings saved from the web UI persist across restarts
    saved = load_user_settings()
    if "temperature" in saved:
        cfg.temperature = float(saved["temperature"])
    if "max_output_tokens" in saved:
        cfg.max_output_tokens = int(saved["max_output_tokens"])
    if saved.get("base_url") and not os.environ.get("LMH_BASE_URL"):
        cfg.base_url = saved["base_url"]
    if saved.get("model") and not os.environ.get("LMH_MODEL"):
        cfg.model = saved["model"]
    if saved.get("api_key"):
        cfg.api_key = saved["api_key"]
    if saved.get("context_window"):
        cfg.context_window = int(saved["context_window"])
        cfg.compact_threshold = max(cfg.context_window - cfg.output_reserve,
                                    cfg.context_window // 2)
        cfg.compact_target = cfg.compact_threshold // 2
    return cfg
