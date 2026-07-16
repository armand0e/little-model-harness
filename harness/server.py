"""Web app server: multi-conversation, streaming, files, settings.

Run with: python -m harness.server [port]
"""
from __future__ import annotations

import json
import copy
import math
import mimetypes
import os
import queue
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import platform
import re
import shutil
import subprocess
import sys

import httpx
import uvicorn
from fastapi import (FastAPI, HTTPException, Request, UploadFile, WebSocket,
                     WebSocketDisconnect)
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               StreamingResponse)
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .agent import Agent
from .config import (DATA_DIR, ROOT, SESSIONS_DIR, get_default_workspace,
                     load_config, load_user_settings, save_user_settings,
                     set_default_workspace)
from .preview import OFFICE_EXTS, PREVIEWABLE, build_preview, validate_office_archive
from .mcp_client import (BUILTIN_COMPUTER_SERVER, MCP_HUB,
                         computer_backend_info, load_mcp_servers,
                         load_user_mcp_servers, merge_builtin_mcp_servers,
                         validate_mcp_servers)
from .persistence import atomic_write_text
from .skills import SkillsManager

app = FastAPI(title="Little Model Harness")
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "[::1]"],
)


@app.middleware("http")
async def local_request_boundary(request: Request, call_next):
    """Keep hostile web origins and DNS-rebinding hosts away from local APIs."""
    if request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        fetch_site = request.headers.get("sec-fetch-site", "").lower()
        try:
            origin_host = urlsplit(origin).hostname if origin else None
        except ValueError:
            origin_host = "invalid"
        if (origin and origin_host not in {"127.0.0.1", "localhost", "::1"}) \
                or fetch_site == "cross-site":
            return JSONResponse({"detail": "cross-origin API access denied"},
                                status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response

# windowed app: console children must not pop terminal windows
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

CFG = load_config()          # one shared config: settings changes hit all sessions
MODEL_LOCK = threading.Lock()  # one generation at a time — single local model
WORKSPACE_STATE_LOCK = threading.RLock()
JOBS_FILE = DATA_DIR / "jobs.json"
MAX_SESSION_FILE_BYTES = 50 * 1024 * 1024
MAX_PERSISTED_TOOL_RESULT_CHARS = 100_000
MAX_PERSISTED_TOOL_ERROR_CHARS = 4_000


def _cap_persisted_tool_text(value: object) -> object:
    if not isinstance(value, str):
        return value
    limit = (MAX_PERSISTED_TOOL_ERROR_CHARS
             if value.lstrip().startswith("Error")
             else MAX_PERSISTED_TOOL_RESULT_CHARS)
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[persisted tool output truncated]"


class Session:
    def __init__(self, sid: str, title: str = "New chat",
                 created: float | None = None,
                 workspace: str | None = None, mode: str = "agent",
                 project_id: str | None = None) -> None:
        self.id = sid
        self.title = title
        self.created = created if created is not None else time.time()
        self.updated = self.created
        self.pinned = False
        self.project_id = project_id
        self.display: list[dict] = []   # UI-facing event log
        # each chat works in its own folder; new chats inherit the default
        self.workspace = workspace or str(get_default_workspace())
        self.mode = mode if mode in {"agent", "chat", "research"} else "agent"
        self._agent: Agent | None = None
        self._agent_state: dict | None = None
        self._safe_agent_state: dict | None = None
        self.running = False
        self.queued = False
        self._job: GenerationJob | None = None
        self.pending_messages: list[dict] = []
        self._dispatching_followup = False
        self._state_lock = threading.RLock()
        self._save_lock = threading.RLock()

    @property
    def agent(self) -> Agent:
        if self._agent is None:
            self._agent = Agent(CFG, workspace=self.workspace)
            self._agent.tool_mode = self.mode == "agent"
            if self._agent_state:
                state = copy.deepcopy(self._agent_state)
                self._agent.ctx.messages = state["messages"]
                self._agent.skills.loaded = set(state["skills_loaded"])
                self._agent.turn_no = state["turn_no"]
                self._agent.turn_marks = state["turn_marks"]
                self._agent.checkpoints = state["checkpoints"]
                self._agent.ctx.compactions = int(state.get("compactions", 0))
                self._agent.ctx.calibrator.ratio = float(
                    state.get("calibration_ratio", 1.0))
                self._agent.ctx.calibrator.last_real_prompt = int(
                    state.get("last_real_prompt", 0))
                self._safe_agent_state = copy.deepcopy(self._agent_state)
                self._agent_state = None
        return self._agent

    def set_workspace(self, path: str) -> None:
        p = Path(path).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        self.workspace = str(p)
        if self._agent:
            self._agent.workspace = p
        self.save()

    def meta(self) -> dict:
        job = self._job
        return {"id": self.id, "title": self.title, "created": self.created,
                "updated": self.updated, "messages": len(self.display),
                "pinned": self.pinned, "workspace": self.workspace,
                "running": self.running, "queued": self.queued,
                "mode": self.mode, "project_id": self.project_id,
                "pending_count": len(self.pending_messages),
                "job_id": job.id if job is not None else None,
                "queue_position": _queue_position(job) if self.queued else None}

    # ---- persistence ----
    def save(self, *, include_live_agent: bool = False) -> None:
        with self._save_lock:
            SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            empty_state = {"messages": [], "skills_loaded": [], "turn_no": 0,
                           "turn_marks": [], "checkpoints": [],
                           "compactions": 0, "calibration_ratio": 1.0,
                           "last_real_prompt": 0}
            if self._agent is not None and (include_live_agent or not self.running):
                state = {
                    "messages": copy.deepcopy(self._agent.ctx.messages),
                    "skills_loaded": sorted(self._agent.skills.loaded),
                    "turn_no": self._agent.turn_no,
                    "turn_marks": copy.deepcopy(self._agent.turn_marks),
                    "checkpoints": copy.deepcopy(self._agent.checkpoints),
                    "compactions": self._agent.ctx.compactions,
                    "calibration_ratio": self._agent.ctx.calibrator.ratio,
                    "last_real_prompt": self._agent.ctx.calibrator.last_real_prompt,
                }
                self._safe_agent_state = copy.deepcopy(state)
            else:
                state = copy.deepcopy(
                    self._agent_state or self._safe_agent_state or empty_state)
            data = {
                "id": self.id, "title": self.title, "created": self.created,
                "updated": self.updated, "pinned": self.pinned,
                "workspace": self.workspace,
                "mode": self.mode,
                "project_id": self.project_id,
                "pending_messages": self.pending_messages,
                "display": self.display,
                "messages": state["messages"],
                "skills_loaded": state["skills_loaded"],
                "turn_no": state["turn_no"],
                "turn_marks": state["turn_marks"],
                "checkpoints": state["checkpoints"],
                "context_compactions": state.get("compactions", 0),
                "context_calibration_ratio": state.get("calibration_ratio", 1.0),
                "context_last_real_prompt": state.get("last_real_prompt", 0),
            }
            target = SESSIONS_DIR / f"{self.id}.json"
            tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            try:
                with tmp.open("w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, target)
            finally:
                tmp.unlink(missing_ok=True)

    @classmethod
    def load(cls, path: Path) -> "Session | None":
        try:
            if path.stat().st_size > MAX_SESSION_FILE_BYTES:
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            sid = data.get("id")
            if not isinstance(sid, str) or not re.fullmatch(r"[a-f0-9]{12}", sid):
                return None
            display = data.get("display", [])
            messages = data.get("messages", [])
            if (not isinstance(display, list)
                    or not all(isinstance(x, dict) for x in display)
                    or not isinstance(messages, list)
                    or not all(_valid_context_message(x) for x in messages)):
                return None
            # Older computer-use failures could persist an entire malformed
            # snapshot (including screenshot base64) inside an error string.
            # Bound those records during load so opening the affected chat or
            # sending its next turn cannot freeze the UI/model again.
            for item in display:
                if item.get("t") == "tool":
                    item["result"] = _cap_persisted_tool_text(
                        item.get("result"))
            for message in messages:
                if message.get("role") == "tool":
                    message["content"] = _cap_persisted_tool_text(
                        message.get("content"))
            skills_loaded = data.get("skills_loaded", [])
            turn_marks = data.get("turn_marks", [])
            checkpoints = data.get("checkpoints", [])
            pending_messages = data.get("pending_messages", [])
            turn_no = int(data.get("turn_no", 0))
            compactions = data.get("context_compactions", 0)
            calibration_ratio = data.get("context_calibration_ratio", 1.0)
            last_real_prompt = data.get("context_last_real_prompt", 0)
            if (not isinstance(skills_loaded, list)
                    or not all(isinstance(x, str) for x in skills_loaded)
                    or not isinstance(turn_marks, list)
                    or not all(isinstance(x, dict) for x in turn_marks)
                    or not isinstance(checkpoints, list)
                    or not all(isinstance(x, dict) for x in checkpoints)
                    or not isinstance(pending_messages, list)
                    or len(pending_messages) > 20
                    or not all(_valid_pending_message(x)
                               for x in pending_messages)
                    or turn_no < 0
                    or isinstance(compactions, bool)
                    or not isinstance(compactions, int) or compactions < 0
                    or isinstance(calibration_ratio, bool)
                    or not isinstance(calibration_ratio, (int, float))
                    or not math.isfinite(float(calibration_ratio))
                    or not 0.5 <= float(calibration_ratio) <= 2.5
                    or isinstance(last_real_prompt, bool)
                    or not isinstance(last_real_prompt, int)
                    or last_real_prompt < 0):
                return None
            if not all(isinstance(mark.get("turn"), int)
                       and isinstance(mark.get("msg_index"), int)
                       and mark["turn"] >= 1 and mark["msg_index"] >= 0
                       for mark in turn_marks):
                return None
            mark_turns = [mark["turn"] for mark in turn_marks]
            if (mark_turns != sorted(set(mark_turns))
                    or any(turn > turn_no for turn in mark_turns)):
                return None
            if not all(isinstance(cp.get("turn"), int)
                       and cp["turn"] >= 1
                       and isinstance(cp.get("path"), str)
                       and isinstance(cp.get("existed"), bool)
                       and (cp.get("before") is None
                            or isinstance(cp.get("before"), str))
                       and (cp.get("before_b64") is None
                            or isinstance(cp.get("before_b64"), str))
                       for cp in checkpoints):
                return None
            if any(cp["turn"] > turn_no for cp in checkpoints):
                return None
            for cp in checkpoints:
                snapshots = sum(cp.get(key) is not None
                                for key in ("before", "before_b64"))
                if (cp["existed"] and snapshots != 1) or (
                        not cp["existed"] and snapshots != 0):
                    return None
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return None
        workspace = data.get("workspace")
        if workspace is not None and not isinstance(workspace, str):
            return None
        created = data.get("created")
        updated = data.get("updated")
        if (created is not None and (
                isinstance(created, bool)
                or not isinstance(created, (int, float))
                or not math.isfinite(created))):
            return None
        if (updated is not None and (
                isinstance(updated, bool)
                or not isinstance(updated, (int, float))
                or not math.isfinite(updated))):
            return None
        mode = data.get("mode", "agent")
        if mode not in {"agent", "chat", "research"}:
            return None
        s = cls(sid, str(data.get("title", "Chat"))[:80], created, workspace, mode)
        project_id = data.get("project_id")
        s.project_id = project_id if isinstance(project_id, str) else None
        s.updated = updated if updated is not None else s.created
        s.pinned = bool(data.get("pinned", False))
        s.display = display
        s.pending_messages = pending_messages
        if messages:
            s._agent_state = {
                "messages": messages, "skills_loaded": skills_loaded,
                "turn_no": turn_no, "turn_marks": turn_marks,
                "checkpoints": checkpoints,
                "compactions": compactions,
                "calibration_ratio": float(calibration_ratio),
                "last_real_prompt": last_real_prompt,
            }
        return s


def _valid_context_message(message: object) -> bool:
    if not isinstance(message, dict):
        return False
    if message.get("role") not in {"user", "assistant", "tool", "system"}:
        return False
    content = message.get("content")
    if content is not None and not isinstance(content, (str, list)):
        return False
    if isinstance(content, list) and not all(isinstance(part, dict) for part in content):
        return False
    calls = message.get("tool_calls", [])
    if not isinstance(calls, list) or not all(isinstance(call, dict) for call in calls):
        return False
    return True


def _valid_pending_message(message: object) -> bool:
    return (isinstance(message, dict)
            and isinstance(message.get("id"), str)
            and re.fullmatch(r"[a-f0-9]{12}", message["id"]) is not None
            and isinstance(message.get("text"), str)
            and bool(message["text"].strip())
            and len(message["text"]) <= 3_000_000
            and not isinstance(message.get("created"), bool)
            and isinstance(message.get("created"), (int, float))
            and math.isfinite(message["created"]))


SESSIONS: dict[str, Session] = {}
SESSIONS_LOCK = threading.RLock()
for _p in sorted(SESSIONS_DIR.glob("*.json")) if SESSIONS_DIR.is_dir() else []:
    _s = Session.load(_p)
    if _s is None:
        continue
    SESSIONS[_s.id] = _s


def _get(sid: str) -> Session:
    with SESSIONS_LOCK:
        session = SESSIONS.get(sid)
    if session is None:
        raise HTTPException(404, "no such session")
    return session


def _context_status_for(session: Session) -> dict:
    if session._agent or session._agent_state:
        return session.agent.context_status()
    return {"estimated_tokens": 0, "window": CFG.context_window,
            "compact_threshold": CFG.compact_threshold,
            "compact_target": CFG.compact_target,
            "compactions": 0, "last_prompt_tokens": 0,
            "system_tokens": 0, "tool_schema_tokens": 0,
            "conversation_tokens": 0, "calibration_ratio": 1.0,
            "skills_loaded": []}


# ---------- pages ----------
@app.get("/")
def index():
    return FileResponse(ROOT / "web" / "index.html")


VENDOR_FILES = {"xterm.js": "text/javascript",
                "xterm.css": "text/css",
                "addon-fit.js": "text/javascript"}


@app.get("/vendor/{name}")
def vendor_asset(name: str):
    if name not in VENDOR_FILES:
        raise HTTPException(404, "unknown asset")
    path = ROOT / "web" / "vendor" / name
    if not path.is_file():
        raise HTTPException(404, "asset missing")
    return FileResponse(path, media_type=VENDOR_FILES[name])


# ---------- interactive terminal (xterm.js over a websocket PTY) ----------
@app.websocket("/api/terminal")
async def terminal_socket(websocket: WebSocket, sid: str | None = None):
    import asyncio

    # HTTP middleware does not cover websocket handshakes: enforce the same
    # local-only host/origin boundary here.
    host = (websocket.headers.get("host") or "").split(":")[0].lower()
    origin = websocket.headers.get("origin")
    try:
        origin_host = urlsplit(origin).hostname if origin else None
    except ValueError:
        origin_host = "invalid"
    if host not in {"127.0.0.1", "localhost", "[::1]", "::1"} or (
            origin and origin_host not in {"127.0.0.1", "localhost", "::1"}):
        await websocket.close(code=4403)
        return

    workspace = get_default_workspace()
    if sid:
        with SESSIONS_LOCK:
            session = SESSIONS.get(sid)
        if session is not None:
            workspace = Path(session.workspace)

    await websocket.accept()
    from .pty_shell import spawn_shell
    try:
        shell = spawn_shell(workspace)
    except Exception as exc:
        await websocket.send_text(
            f"\r\n[terminal unavailable: {type(exc).__name__}: {exc}]\r\n")
        await websocket.close()
        return

    loop = asyncio.get_running_loop()

    async def pump_output() -> None:
        try:
            while True:
                chunk = await loop.run_in_executor(None, shell.read)
                await websocket.send_text(chunk)
        except (EOFError, OSError, RuntimeError):
            try:
                await websocket.send_text("\r\n[shell exited]\r\n")
                await websocket.close()
            except Exception:
                pass

    reader = asyncio.ensure_future(pump_output())
    try:
        while True:
            message = await websocket.receive_text()
            if len(message) > 65536:
                continue
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            data = payload.get("input")
            if isinstance(data, str) and data:
                try:
                    shell.write(data)
                except OSError:
                    break
            resize = payload.get("resize")
            if isinstance(resize, dict):
                try:
                    shell.resize(int(resize.get("cols", 100)),
                                 int(resize.get("rows", 30)))
                except (OSError, TypeError, ValueError):
                    pass
    except WebSocketDisconnect:
        pass
    finally:
        reader.cancel()
        shell.close()


# ---------- meta ----------
SKILL_CATALOG = SkillsManager()


def _computer_control_status() -> dict[str, object]:
    info = dict(computer_backend_info())
    info.pop("command", None)  # do not expose install paths through the API
    runtime = next((item for item in MCP_HUB.status()
                    if item.get("name") == BUILTIN_COMPUTER_SERVER), None)
    if runtime:
        info.update({"state": runtime.get("state"),
                     "error": runtime.get("error"),
                     "tools": runtime.get("tools", 0)})
    else:
        info.update({"state": "not_started" if info.get("available")
                     else "unavailable", "error": None, "tools": 0})
    return info


# ---------------- OpenAI-compatible provider facade (/v1) ----------------
# The claude-desktop-open-source shell talks OpenAI /v1 to its provider.
# Serving that surface here gives it one local endpoint that follows the
# harness settings (base_url / model / api key) instead of its own config.

def _upstream_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if CFG.api_key and CFG.api_key != "not-needed":
        headers["Authorization"] = f"Bearer {CFG.api_key}"
    return headers


@app.get("/v1/models")
async def v1_models():
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{CFG.base_url}/models",
                                 headers=_upstream_headers())
        raw = r.json()
    except Exception as exc:
        return JSONResponse({"error": {"message": f"upstream: {exc}"}},
                            status_code=502)
    # Normalize to OpenAI shape: some local servers answer /v1/models in
    # Ollama's {"models": [{"name"/"model": ...}]} form, which breaks
    # clients that expect {"data": [{"id": ...}]}.
    items = None
    if isinstance(raw, dict):
        if isinstance(raw.get("data"), list):
            items = raw["data"]
        elif isinstance(raw.get("models"), list):
            items = raw["models"]
    if items is None:
        return JSONResponse(raw, status_code=r.status_code)
    data = []
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id") or item.get("model") or item.get("name")
        if model_id:
            data.append({"id": str(model_id), "object": "model",
                         "owned_by": "local"})
    return {"object": "list", "data": data}


@app.post("/v1/chat/completions")
async def v1_chat_completions(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be a JSON object")
    if not body.get("model"):
        body["model"] = CFG.model
    url = f"{CFG.base_url}/chat/completions"
    client = httpx.AsyncClient(timeout=httpx.Timeout(None, connect=20))
    try:
        upstream = await client.send(
            client.build_request("POST", url, json=body,
                                 headers=_upstream_headers()),
            stream=True)
    except Exception as exc:
        await client.aclose()
        return JSONResponse({"error": {"message": f"upstream: {exc}"}},
                            status_code=502)
    if upstream.status_code >= 400:
        detail = (await upstream.aread()).decode("utf-8", "replace")[:1000]
        await upstream.aclose()
        await client.aclose()
        return JSONResponse({"error": {"message": detail or "upstream error"}},
                            status_code=upstream.status_code)

    async def relay():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        relay(),
        media_type=upstream.headers.get("content-type", "application/json"))


@app.get("/api/status")
def status():
    SKILL_CATALOG.refresh()
    skills = [{"name": s.name, "description": s.description,
               "category": s.category, "hint": s.hint}
              for s in SKILL_CATALOG.skills.values()]
    return {"model": CFG.model, "base_url": CFG.base_url,
            "workspace": str(get_default_workspace()),
            "data_dir": str(DATA_DIR), "window": CFG.context_window,
            "skills": skills, "busy": _jobs_active(),
            "mcp": MCP_HUB.status(),
            "ui_scale": int(load_user_settings().get("ui_scale", 100) or 100),
            "computer_control": _computer_control_status()}


class SettingsBody(BaseModel):
    temperature: float | None = None
    max_output_tokens: int | None = None
    workspace: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    context_window: int | None = None
    mcp_servers: dict[str, dict] | None = None
    global_rules: str | None = None
    ui_scale: int | None = None


@app.get("/api/settings")
def get_settings():
    with SETTINGS_REFRESH_LOCK:
        refresh = copy.deepcopy(SETTINGS_REFRESH)
    return {"temperature": CFG.temperature,
            "max_output_tokens": CFG.max_output_tokens,
            "workspace": str(get_default_workspace()),
            "model": CFG.model, "base_url": CFG.base_url,
            "api_key_set": bool(CFG.api_key and CFG.api_key != "not-needed"),
            # Keep the user's requested window distinct from the effective
            # window, which may be temporarily clamped by the active model.
            "context_window": REQUESTED_CONTEXT_WINDOW,
            "effective_context_window": CFG.context_window,
            "server_n_ctx": DETECTED["n_ctx"],
            "compact_threshold": CFG.compact_threshold,
            # Only user-configured servers are editable. The hash-pinned
            # native computer backend is attached automatically by OS.
            "mcp_servers": load_user_mcp_servers(),
            "mcp_status": MCP_HUB.status(),
            "computer_control": _computer_control_status(),
            "global_rules": str(load_user_settings().get("global_rules", "")),
            "ui_scale": int(load_user_settings().get("ui_scale", 100) or 100),
            "background": refresh}


def _apply_window(window: int) -> None:
    """Recompute the prompt ceiling and post-compaction target."""
    CFG.context_window = max(2048, min(1_048_576, window))
    CFG.compact_threshold = max(CFG.context_window - CFG.output_reserve,
                                CFG.context_window // 2)
    CFG.compact_target = CFG.compact_threshold * 2 // 3
    # Output budget is derived, not configured: always 75% of the window
    # (each call is still clamped to the space actually left).
    CFG.max_output_tokens = max(256, int(CFG.context_window * 0.75))


DETECTED: dict[str, int | None] = {"n_ctx": None}
REQUESTED_CONTEXT_WINDOW = CFG.context_window
SETTINGS_REFRESH_LOCK = threading.RLock()
SETTINGS_REFRESH: dict[str, object] = {
    "revision": 0,
    "model": {"state": "idle", "error": None},
    "mcp": {"state": "idle", "error": None},
}


def _fetch_models(base_url: str | None = None,
                  api_key: str | None = None) -> list[dict]:
    """Return a bounded, normalized OpenAI-compatible /models response."""
    url = (base_url or CFG.base_url).rstrip("/") + "/models"
    key = CFG.api_key if api_key is None else api_key
    headers = ({"Authorization": f"Bearer {key}"}
               if key and key != "not-needed" else {})
    response = httpx.get(url, timeout=5.0, headers=headers)
    response.raise_for_status()
    payload = response.json()
    raw_models = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(raw_models, list):
        raise ValueError("model endpoint returned an invalid data list")
    models = []
    for raw in raw_models[:200]:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            continue
        model_id = raw["id"].strip()[:500]
        if not model_id:
            continue
        raw_meta = raw.get("meta")
        meta: dict[str, object] = dict(raw_meta) if isinstance(raw_meta, dict) else {}
        n_ctx = meta.get("n_ctx")
        try:
            n_ctx = (int(n_ctx) if isinstance(n_ctx, (str, int, float))
                     and not isinstance(n_ctx, bool) else None)
        except (TypeError, ValueError, OverflowError):
            n_ctx = None
        models.append({
            "id": model_id,
            "owned_by": str(raw.get("owned_by", ""))[:200],
            "n_ctx": n_ctx if n_ctx and n_ctx > 0 else None,
        })
    return models


@app.get("/api/models")
def list_models():
    try:
        return {"models": _fetch_models(), "selected": CFG.model}
    except Exception as e:
        raise HTTPException(502, f"could not list models: {type(e).__name__}: {e}")


@app.get("/api/mcp")
def mcp_status():
    schemas = []
    error = None
    try:
        MCP_HUB.ensure_configured()
        schemas = MCP_HUB.schemas()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    return {"servers": MCP_HUB.status(),
            "tools": [schema["function"]["name"] for schema in schemas],
            "error": error}


def _sync_window() -> None:
    """Ask the model server how much context it actually has (llama.cpp and
    LM Studio expose meta.n_ctx) and clamp our window to it. This is what
    keeps the harness working when someone loads a model at 4k."""
    DETECTED["n_ctx"] = None
    _apply_window(REQUESTED_CONTEXT_WINDOW)
    try:
        models = _fetch_models()
        selected = next((m for m in models if m.get("id") == CFG.model), None)
        if selected is None and len(models) == 1:
            selected = models[0]
        n = selected.get("n_ctx") if selected else None
        if n:
            DETECTED["n_ctx"] = int(n)
    except Exception:
        return
    n = DETECTED["n_ctx"]
    if n:
        # The model server's reported n_ctx is authoritative — grow or
        # shrink to it. The configured window only matters when the server
        # does not report one.
        _apply_window(n)


def _schedule_settings_refresh(mcp_servers: dict[str, dict] | None = None,
                               *, force_mcp: bool = False) -> None:
    """Probe slow external services without holding an HTTP request open.

    Settings are already validated and durably saved before this runs.  A
    revision token prevents an older, slower probe from overwriting a newer
    save when the user changes endpoints twice in quick succession.
    """
    with SETTINGS_REFRESH_LOCK:
        previous_revision = SETTINGS_REFRESH["revision"]
        revision = (previous_revision if isinstance(previous_revision, int)
                    else 0) + 1
        SETTINGS_REFRESH["revision"] = revision
        SETTINGS_REFRESH["model"] = {"state": "checking", "error": None}
        if mcp_servers is not None:
            SETTINGS_REFRESH["mcp"] = {"state": "connecting", "error": None}
        base_url, api_key, model = CFG.base_url, CFG.api_key, CFG.model
        requested = REQUESTED_CONTEXT_WINDOW

    def probe_model() -> None:
        state = "ready"
        error = None
        detected: int | None = None
        try:
            models = _fetch_models(base_url, api_key)
            selected = next((m for m in models if m.get("id") == model), None)
            if selected is None and len(models) == 1:
                selected = models[0]
            n_ctx = selected.get("n_ctx") if selected else None
            if n_ctx:
                detected = int(n_ctx)
        except Exception as exc:
            state = "error"
            error = f"{type(exc).__name__}: {exc}"[:500]
        with SETTINGS_REFRESH_LOCK:
            if SETTINGS_REFRESH["revision"] != revision:
                return
            DETECTED["n_ctx"] = detected
            _apply_window(min(requested, detected) if detected else requested)
            SETTINGS_REFRESH["model"] = {"state": state, "error": error}

    threading.Thread(target=probe_model, name="lmh-model-probe",
                     daemon=True).start()

    if mcp_servers is None:
        return

    def configure_mcp() -> None:
        state = "ready"
        error = None
        try:
            MCP_HUB.configure(mcp_servers, force=force_mcp)
        except Exception as exc:
            state = "error"
            error = f"{type(exc).__name__}: {exc}"[:500]
        with SETTINGS_REFRESH_LOCK:
            if SETTINGS_REFRESH["revision"] != revision:
                return
            SETTINGS_REFRESH["mcp"] = {"state": state, "error": error}

    threading.Thread(target=configure_mcp, name="lmh-mcp-config",
                     daemon=True).start()


@app.post("/api/settings")
def set_settings(body: SettingsBody):
    global REQUESTED_CONTEXT_WINDOW
    if MODEL_LOCK.locked() or _jobs_active():
        raise HTTPException(409, "stop or finish queued jobs before changing model settings")
    # Validate everything before mutating the process-wide live config.
    temperature = CFG.temperature
    if body.temperature is not None:
        if not math.isfinite(body.temperature):
            raise HTTPException(400, "temperature must be a finite number")
        temperature = max(0.0, min(2.0, body.temperature))
    context_window = REQUESTED_CONTEXT_WINDOW
    if body.context_window is not None:
        context_window = max(2048, min(1_048_576, body.context_window))
    # Output budget is derived (75% of the window); any client-sent value
    # is ignored so old clients can't pin a stale budget.
    max_output_tokens = max(256, int(context_window * 0.75))
    base_url = CFG.base_url
    if body.base_url is not None and body.base_url.strip():
        base_url = body.base_url.strip().rstrip("/")
        try:
            parsed = urlsplit(base_url)
        except ValueError:
            parsed = None
        if (parsed is None or parsed.scheme not in {"http", "https"}
                or not parsed.hostname or parsed.username is not None
                or parsed.password is not None):
            raise HTTPException(400, "model endpoint must be an http(s) URL without credentials")
    model = CFG.model
    if body.model is not None:
        if body.model.strip():
            model = body.model.strip()
        else:
            # Blank means "auto": use whatever the endpoint reports first.
            try:
                candidates = _fetch_models(base_url, CFG.api_key
                                           if body.api_key is None
                                           else (body.api_key.strip()
                                                 or "not-needed"))
                if candidates:
                    model = candidates[0]["id"]
            except Exception:
                pass  # endpoint offline: keep the current model id
    global_rules = None
    if body.global_rules is not None:
        global_rules = body.global_rules.strip()[:4000]
    ui_scale = None
    if body.ui_scale is not None:
        ui_scale = max(80, min(150, int(body.ui_scale)))
    api_key = CFG.api_key
    if body.api_key is not None:  # empty string clears the key
        api_key = body.api_key.strip() or "not-needed"
    workspace: Path | None = None
    if body.workspace is not None and body.workspace.strip():
        try:
            workspace = Path(os.path.expandvars(
                os.path.expanduser(body.workspace.strip()))).resolve()
            workspace.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise HTTPException(400, f"can't use that folder: {e}")
    old_user_mcp_servers = load_user_mcp_servers()
    try:
        user_mcp_servers = (validate_mcp_servers(body.mcp_servers)
                            if body.mcp_servers is not None
                            else old_user_mcp_servers)
    except ValueError as e:
        raise HTTPException(400, str(e))

    endpoint_changed = (base_url, model, api_key) != (
        CFG.base_url, CFG.model, CFG.api_key)
    mcp_changed = (body.mcp_servers is not None
                   and user_mcp_servers != old_user_mcp_servers)
    effective_mcp_servers = merge_builtin_mcp_servers(user_mcp_servers)

    # Commit to disk before mutating live process state.  The previous flow
    # could return an error after partially applying settings, leaving the UI
    # unable to tell whether Save had worked.
    try:
        save_user_settings({"temperature": temperature,
                            "max_output_tokens": max_output_tokens,
                            "base_url": base_url, "model": model,
                            "api_key": api_key,
                            "context_window": context_window,
                            "mcp_servers": user_mcp_servers,
                            **({"workspace": str(workspace)} if workspace else {}),
                            **({"global_rules": global_rules}
                               if global_rules is not None else {}),
                            **({"ui_scale": ui_scale}
                               if ui_scale is not None else {})})
    except OSError as exc:
        raise HTTPException(500, f"could not save settings: {exc}")

    CFG.temperature = temperature
    CFG.max_output_tokens = max_output_tokens
    CFG.base_url, CFG.model, CFG.api_key = base_url, model, api_key
    REQUESTED_CONTEXT_WINDOW = context_window
    _apply_window(context_window)
    if endpoint_changed:
        with SESSIONS_LOCK:
            sessions = list(SESSIONS.values())
        for s in sessions:
            if s._agent:
                s._agent.reconfigure_model(
                    CFG.base_url, CFG.model, CFG.api_key)
    # Respond immediately. Endpoint probing and MCP startup are health checks,
    # not part of durable persistence, and their states are exposed to the UI.
    _schedule_settings_refresh(effective_mcp_servers if mcp_changed else None,
                               force_mcp=mcp_changed)
    return get_settings()


# ---------- sessions ----------
@app.get("/api/sessions")
def list_sessions():
    with SESSIONS_LOCK:
        metas = [s.meta() for s in SESSIONS.values()]
    return sorted(metas,
                  key=lambda m: (not m["pinned"], -m["updated"]))


@app.get("/api/search")
def search_chats(q: str):
    """Full-content search across all sessions for the sidebar."""
    terms = [t for t in re.findall(r"\w{2,}", q.lower())]
    if not terms:
        return []
    out = []
    with SESSIONS_LOCK:
        sessions = list(SESSIONS.values())
    for s in sessions:
        best, snippet = 0, ""
        for item in s.display:
            text = item.get("text") or item.get("result") or ""
            if not isinstance(text, str):
                continue
            low = text.lower()
            score = sum(1 for t in terms if t in low)
            if score > best:
                best = score
                pos = min((low.find(t) for t in terms if t in low), default=0)
                start = max(0, pos - 40)
                snippet = " ".join(text[start:start + 160].split())
        title_score = sum(2 for t in terms if t in s.title.lower())
        if best + title_score > 0:
            out.append({**s.meta(), "score": best + title_score,
                        "snippet": snippet})
    out.sort(key=lambda m: -m["score"])
    return out[:20]


# ---------------- projects ----------------
# A project is a named shared workspace plus instructions. Instructions live
# as HARNESS.md inside the project workspace — the exact file the agent
# already injects as "Project notes", so no new context machinery exists.

PROJECTS_FILE = DATA_DIR / "projects.json"
PROJECTS_LOCK = threading.Lock()


def _load_projects() -> list[dict]:
    try:
        data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_projects(projects: list[dict]) -> None:
    PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(PROJECTS_FILE,
                      json.dumps(projects, ensure_ascii=False, indent=1))


def _find_project(pid: str) -> dict | None:
    return next((p for p in _load_projects() if p.get("id") == pid), None)


def _project_meta(project: dict) -> dict:
    instructions = ""
    try:
        instructions = (Path(project["workspace"])
                        / "HARNESS.md").read_text(encoding="utf-8")
    except OSError:
        pass
    with SESSIONS_LOCK:
        chats = sum(1 for s in SESSIONS.values()
                    if s.project_id == project.get("id"))
    return {**project, "instructions": instructions, "chats": chats}


class ProjectBody(BaseModel):
    name: str | None = None
    instructions: str | None = None


@app.get("/api/projects")
def list_projects():
    with PROJECTS_LOCK:
        projects = _load_projects()
    return [_project_meta(p) for p in projects]


@app.post("/api/projects")
def create_project(body: ProjectBody):
    name = (body.name or "").strip()[:60]
    if not name:
        raise HTTPException(400, "project name is required")
    pid = uuid.uuid4().hex[:12]
    slug = re.sub(r"[^\w\- ]", "", name).strip().replace(" ", "-").lower()
    workspace = get_default_workspace() / "projects" / (
        f"{slug}-{pid[:4]}" if slug else pid)
    try:
        workspace.mkdir(parents=True, exist_ok=True)
        if body.instructions and body.instructions.strip():
            (workspace / "HARNESS.md").write_text(
                body.instructions.strip(), encoding="utf-8")
    except OSError as exc:
        raise HTTPException(500, f"could not create project folder: {exc}")
    project = {"id": pid, "name": name, "workspace": str(workspace),
               "created": time.time()}
    with PROJECTS_LOCK:
        projects = _load_projects()
        projects.append(project)
        _save_projects(projects)
    return _project_meta(project)


@app.patch("/api/projects/{pid}")
def update_project(pid: str, body: ProjectBody):
    with PROJECTS_LOCK:
        projects = _load_projects()
        project = next((p for p in projects if p.get("id") == pid), None)
        if project is None:
            raise HTTPException(404, "no such project")
        if body.name is not None and body.name.strip():
            project["name"] = body.name.strip()[:60]
        _save_projects(projects)
    if body.instructions is not None:
        target = Path(project["workspace"]) / "HARNESS.md"
        try:
            if body.instructions.strip():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body.instructions.strip(),
                                  encoding="utf-8")
            elif target.is_file():
                target.unlink()
        except OSError as exc:
            raise HTTPException(500, f"could not save instructions: {exc}")
    return _project_meta(project)


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    with PROJECTS_LOCK:
        projects = _load_projects()
        keep = [p for p in projects if p.get("id") != pid]
        if len(keep) == len(projects):
            raise HTTPException(404, "no such project")
        _save_projects(keep)
    # Chats survive their project: they just lose the grouping. The project
    # folder stays on disk — it may hold the user's files.
    with SESSIONS_LOCK:
        affected = [s for s in SESSIONS.values() if s.project_id == pid]
    for s in affected:
        s.project_id = None
        s.save()
    return {"ok": True}


class CreateSessionBody(BaseModel):
    mode: str = "agent"
    project_id: str | None = None


@app.post("/api/sessions")
def create_session(body: CreateSessionBody | None = None):
    mode = body.mode if body else "agent"
    if mode not in {"agent", "chat", "research"}:
        raise HTTPException(400, "mode must be 'agent', 'chat', or 'research'")
    project = None
    if body and body.project_id:
        with PROJECTS_LOCK:
            project = _find_project(body.project_id)
        if project is None:
            raise HTTPException(404, "no such project")
    s = Session(uuid.uuid4().hex[:12], mode=mode,
                workspace=project["workspace"] if project else None,
                project_id=project["id"] if project else None)
    with SESSIONS_LOCK:
        SESSIONS[s.id] = s
    return s.meta()


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    s = _get(sid)
    st = _context_status_for(s)
    return {**s.meta(), "display": s.display, "context": st,
            "pending_messages": list(s.pending_messages)}


class RenameBody(BaseModel):
    title: str | None = None
    pinned: bool | None = None
    mode: str | None = None


@app.patch("/api/sessions/{sid}")
def rename_session(sid: str, body: RenameBody):
    s = _get(sid)
    with s._state_lock:
        if s.running or s.queued:
            raise HTTPException(409, "stop generation before changing this session")
        if body.title is not None:
            s.title = body.title.strip()[:80] or s.title
        if body.pinned is not None:
            s.pinned = body.pinned
        if body.mode is not None:
            if body.mode not in {"agent", "chat", "research"}:
                raise HTTPException(400, "mode must be 'agent', 'chat', or 'research'")
            s.mode = body.mode
            if s._agent:
                s._agent.tool_mode = s.mode == "agent"
        s.save()
    return s.meta()


@app.delete("/api/sessions/{sid}")
def delete_session(sid: str):
    s = _get(sid)
    with s._state_lock:
        if s.running or s.queued:
            raise HTTPException(409, "stop this session's job before deleting it")
        f = SESSIONS_DIR / f"{sid}.json"
        try:
            f.unlink(missing_ok=True)
        except OSError as e:
            raise HTTPException(400, f"could not delete this session: {e}")
        with SESSIONS_LOCK:
            SESSIONS.pop(sid, None)
        if s._agent:
            s._agent.llm.close()
    return {"ok": True}


@app.post("/api/sessions/{sid}/stop")
def stop_session(sid: str):
    s = _get(sid)
    job = s._job
    if job:
        job.cancel()
    elif s.running and s._agent:
        s._agent.request_stop()
    return {"ok": True, "requested": bool(job or s.running),
            "job_id": job.id if job else None,
            "state": job.state if job else "idle"}


class RevertBody(BaseModel):
    display_index: int


def _revert(s: Session, display_index: int) -> dict:
    """Rewind chat AND restore files to just before the user turn at (or
    nearest before) display_index. Turn N = the Nth user item."""
    with s._state_lock:
        if s.running or s.queued:
            raise HTTPException(409, "busy — stop generation first")
        user_items = [i for i, it in enumerate(s.display) if it.get("t") == "user"]
        if not user_items:
            raise HTTPException(400, "nothing to revert")
        # the turn whose user item is at/nearest before display_index
        turn = next((n for n in range(len(user_items), 0, -1)
                     if user_items[n - 1] <= display_index), 1)
        ui = user_items[turn - 1]
        text = s.display[ui]["text"]
        attachments = s.display[ui].get("attachments", [])
        s.display = s.display[:ui]
        restored: list[str] = []
        if s._agent or s._agent_state:
            restored = s.agent.revert_to_turn(turn)
        s.updated = time.time()
        s.save()
    return {"text": text, "attachments": attachments,
            "restored_files": restored, "turn": turn}


@app.post("/api/sessions/{sid}/undo")
def undo_last_turn(sid: str):
    """Rewind the last turn (chat + files). For regenerate / edit-prompt."""
    s = _get(sid)
    return _revert(s, len(s.display))


@app.post("/api/sessions/{sid}/revert")
def revert_to(sid: str, body: RevertBody):
    """Rewind to just before the user turn at display_index — undoes the
    model's file writes/edits from that point on and truncates the chat."""
    s = _get(sid)
    return _revert(s, body.display_index)


# ---------- background generation queue ----------
GENERATION_QUEUE: queue.Queue = queue.Queue()
JOBS_LOCK = threading.RLock()
ACTIVE_JOBS: dict[str, GenerationJob] = {}
JOB_ORDER: list[str] = []
MAX_ACTIVE_JOBS = 100
_JOB_RESERVATIONS = 0
_QUEUE_THREAD: threading.Thread | None = None
_SHUTTING_DOWN = False


def _queue_position(job: GenerationJob | None) -> int | None:
    if job is None or job.state != "queued":
        return None
    with JOBS_LOCK:
        queued = [jid for jid in JOB_ORDER
                  if (candidate := ACTIVE_JOBS.get(jid)) is not None
                  and candidate.state == "queued"]
    try:
        return queued.index(job.id) + 1
    except ValueError:
        return None


def _notify_queue_positions() -> None:
    with JOBS_LOCK:
        jobs = [ACTIVE_JOBS[jid] for jid in JOB_ORDER
                if jid in ACTIVE_JOBS and ACTIVE_JOBS[jid].state == "queued"]
    for position, job in enumerate(jobs, 1):
        job.events.put({"type": "queue", "data": {
            "job_id": job.id, "position": position,
        }})


def _persist_jobs(*, strict: bool = False) -> None:
    with JOBS_LOCK:
        jobs = [ACTIVE_JOBS[jid] for jid in JOB_ORDER if jid in ACTIVE_JOBS]
        payload = [{"id": job.id, "session_id": job.session.id,
                    "message": job.message, "created": job.created,
                    "display_message": job.display_message,
                    "attachments": [item["name"] for item in job.attachments],
                    "steers": job.steers,
                    "state": job.state}
                   for job in jobs if job.state in {"queued", "running"}]
    try:
        atomic_write_text(JOBS_FILE, json.dumps(payload, ensure_ascii=False, indent=2))
    except OSError:
        if strict:
            raise


def _finish_job(job: GenerationJob) -> None:
    with JOBS_LOCK:
        ACTIVE_JOBS.pop(job.id, None)
        try:
            JOB_ORDER.remove(job.id)
        except ValueError:
            pass
    _notify_queue_positions()
    _persist_jobs()


def _queue_loop() -> None:
    while True:
        job = GENERATION_QUEUE.get()
        if job is None:
            return
        job.run()


def _ensure_queue_thread() -> None:
    global _QUEUE_THREAD
    with JOBS_LOCK:
        if _QUEUE_THREAD is None or not _QUEUE_THREAD.is_alive():
            _QUEUE_THREAD = threading.Thread(
                target=_queue_loop, name="lmh-generation-queue", daemon=True)
            _QUEUE_THREAD.start()


class GenerationJob:
    def __init__(self, session: Session, message: str,
                 job_id: str | None = None,
                 created: float | None = None,
                 display_message: str | None = None,
                 attachments: list[dict] | None = None,
                 steers: list[str] | None = None) -> None:
        self.id = job_id or uuid.uuid4().hex[:16]
        self.session = session
        self.message = message
        self.display_message = display_message if display_message is not None else message
        self.attachments = attachments or []
        self.steers = steers or []
        self.created = created if created is not None else time.time()
        self.state = "queued"
        self.events: queue.Queue = queue.Queue()
        user_item: dict = {"t": "user", "text": self.display_message}
        if self.attachments:
            user_item["attachments"] = self.attachments
        self.turn: list[dict] = [user_item]
        self.turn.extend({"t": "steer", "text": text} for text in self.steers)
        self.reasoning_buf: list[str] = []
        self.text_buf: list[str] = []
        self._lock = threading.RLock()
        self._finalized = False
        self._stream_claimed = False
        self._agent_started = False
        self._cancel_requested = threading.Event()
        self.started_at: float | None = None
        self.last_activity_at = self.created
        self.activity: dict = {"phase": "queued"}
        self.events.put({"type": "user", "data": {
            "text": self.display_message, "attachments": self.attachments,
        }})
        for text in self.steers:
            self.events.put({"type": "steer", "data": text})

    def meta(self) -> dict:
        return {"id": self.id, "session_id": self.session.id,
                "state": self.state, "created": self.created,
                "position": _queue_position(self),
                "activity": self.activity_snapshot()}

    def activity_snapshot(self) -> dict:
        with self._lock:
            now = time.time()
            return {**self.activity,
                    "elapsed_seconds": max(
                        0, int(now - (self.started_at or self.created))),
                    "idle_seconds": max(0, int(now - self.last_activity_at))}

    def flush_text(self, kind: str, buf: list[str]) -> None:
        if buf:
            self.turn.append({"t": kind, "text": "".join(buf)})
            buf.clear()

    def emit(self, etype: str, data) -> None:
        with self._lock:
            self.last_activity_at = time.time()
            if etype == "reasoning_delta":
                self.activity = {"phase": "reasoning"}
                self.flush_text("text", self.text_buf)
                self.reasoning_buf.append(data)
            elif etype == "content_delta":
                self.activity = {"phase": "answering"}
                self.flush_text("reasoning", self.reasoning_buf)
                self.text_buf.append(data)
            elif etype == "activity" and isinstance(data, dict):
                self.activity = dict(data)
            elif etype == "skill_loaded" and isinstance(data, dict):
                self.flush_text("reasoning", self.reasoning_buf)
                self.flush_text("text", self.text_buf)
                self.turn.append({"t": "skill",
                                  "name": str(data.get("name", "")),
                                  "source": str(data.get("source", "automatic"))})
            elif etype == "tool_call":
                self.activity = {"phase": "running_tool",
                                 "tool": data["name"]}
                self.flush_text("reasoning", self.reasoning_buf)
                self.flush_text("text", self.text_buf)
                self.turn.append({"t": "tool", "name": data["name"],
                                  "args": data["arguments"], "result": None})
            elif etype == "tool_result":
                for item in reversed(self.turn):
                    if item.get("t") == "tool" and item["result"] is None:
                        item["result"] = data["result"]
                        break
            elif etype == "context":
                self.turn.append({"t": "notice", "text": str(data)})
            elif etype == "error":
                self.turn.append({"t": "error", "text": str(data)})
        if etype == "activity":
            data = self.activity_snapshot()
        self.events.put({"type": etype, "data": data})

    def claim_stream(self) -> bool:
        with self._lock:
            if self._stream_claimed:
                return False
            self._stream_claimed = True
            return True

    def release_stream(self) -> None:
        with self._lock:
            self._stream_claimed = False

    def steer(self, text: str) -> bool:
        with self._lock:
            if self._finalized or self.state not in {"queued", "running"}:
                return False
            if self.state == "running" and self._agent_started:
                agent = self.session._agent
                if agent is None or not agent.submit_steer(text):
                    return False
            else:
                self.message += (
                    "\n\n[User steering update before execution]\n" + text)
            self.flush_text("reasoning", self.reasoning_buf)
            self.flush_text("text", self.text_buf)
            self.steers.append(text)
            self.turn.append({"t": "steer", "text": text})
            self.events.put({"type": "steer", "data": text})
        _persist_jobs()
        return True

    def run(self) -> None:
        with self._lock:
            if self._finalized:
                return
            self.state = "running"
            self.started_at = time.time()
            self.last_activity_at = self.started_at
            self.activity = {"phase": "starting"}
        try:
            # Do not perform model/tool actions unless crash recovery knows
            # this job has started. Replaying a stale "queued" record after a
            # crash could otherwise repeat destructive tool calls.
            _persist_jobs(strict=True)
        except OSError as exc:
            message = f"Could not persist running job state: {exc}"
            self.turn.append({"t": "error", "text": message})
            self.events.put({"type": "error", "data": message})
            self._finalize("done")
            return
        session = self.session
        with WORKSPACE_STATE_LOCK, session._state_lock:
            if self._finalized:
                return
            session.queued = False
            session.running = True
        MODEL_LOCK.acquire()
        self.events.put({"type": "job", "data": {
            "job_id": self.id, "state": "running"}})
        _notify_queue_positions()
        try:
            agent = session.agent
            agent.tool_mode = session.mode == "agent"
            with self._lock:
                self._agent_started = True
            if self._cancel_requested.is_set():
                agent.request_stop()
            if session.mode == "research":
                from .research import run_research
                final = run_research(agent, self.message, on_event=self.emit)
            else:
                final = agent.run_turn(self.message, on_event=self.emit)
            self.flush_text("reasoning", self.reasoning_buf)
            self.flush_text("text", self.text_buf)
            if not any(item.get("t") == "text"
                       and item["text"].strip() == final.strip()
                       for item in self.turn):
                self.turn.append({"t": "text", "text": final})
            self.events.put({"type": "final", "data": final})
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            self.turn.append({"t": "error", "text": message})
            self.events.put({"type": "error", "data": message})
        finally:
            MODEL_LOCK.release()
            self._finalize(
                "cancelled" if self._cancel_requested.is_set() else "done")

    def cancel(self) -> None:
        self._cancel_requested.set()
        with self._lock:
            if self._finalized:
                return
            if self.state == "queued":
                self.turn.append(
                    {"t": "notice", "text": "Cancelled while queued."})
                self.events.put({
                    "type": "final", "data": "(cancelled while queued)"})
                self._finalize("cancelled")
                return
        if self.state == "running":
            if self.session._agent:
                self.session._agent.request_stop()

    def _finalize(self, state: str) -> None:
        with self._lock:
            if self._finalized:
                return
            self._finalized = True
            self.state = state
        session = self.session
        persistence_error = None
        try:
            self.flush_text("reasoning", self.reasoning_buf)
            self.flush_text("text", self.text_buf)
            session.display.extend(self.turn)
            session.updated = time.time()
            if session.title == "New chat":
                session.title = self.display_message.strip().replace("\n", " ")[:60]
            session.save(include_live_agent=True)
        except Exception as exc:
            persistence_error = (
                f"Could not save this chat: {type(exc).__name__}: {exc}")
        finally:
            with session._state_lock:
                session.running = False
                session.queued = False
                if session._job is self:
                    session._job = None
            if persistence_error:
                self.events.put({"type": "error", "data": persistence_error})
            self.events.put({"type": "session", "data": session.meta()})
            self.events.put({"type": "context_status",
                             "data": _context_status_for(session)})
            self.events.put({"type": "job", "data": {
                "job_id": self.id, "state": state}})
            self.events.put(None)
            _finish_job(self)
            _dispatch_next_followup(session)


def _enqueue_job(session: Session, message: str,
                 job_id: str | None = None,
                 created: float | None = None,
                 display_message: str | None = None,
                 attachments: list[dict] | None = None,
                 steers: list[str] | None = None) -> GenerationJob:
    global _JOB_RESERVATIONS
    job = GenerationJob(
        session, message, job_id, created, display_message, attachments, steers)
    with JOBS_LOCK:
        if len(ACTIVE_JOBS) + _JOB_RESERVATIONS >= MAX_ACTIVE_JOBS:
            raise HTTPException(429, "the background job queue is full")
        _JOB_RESERVATIONS += 1
    try:
        with WORKSPACE_STATE_LOCK, session._state_lock:
            if session.running or session.queued:
                raise HTTPException(409, "this session already has an active job")
            previous_updated, previous_title = session.updated, session.title
            session.queued = True
            session._job = job
            session.updated = time.time()
            if session.title == "New chat":
                session.title = job.display_message.strip().replace("\n", " ")[:60]
            try:
                session.save()
            except OSError as exc:
                session.queued = False
                session._job = None
                session.updated, session.title = previous_updated, previous_title
                raise HTTPException(500, f"could not persist queued job: {exc}")
    except BaseException:
        with JOBS_LOCK:
            _JOB_RESERVATIONS -= 1
        raise
    with JOBS_LOCK:
        _JOB_RESERVATIONS -= 1
        ACTIVE_JOBS[job.id] = job
        JOB_ORDER.append(job.id)
    try:
        # A job is not accepted until its durable queue record exists.
        _persist_jobs(strict=True)
    except OSError as exc:
        with JOBS_LOCK:
            ACTIVE_JOBS.pop(job.id, None)
            try:
                JOB_ORDER.remove(job.id)
            except ValueError:
                pass
        with WORKSPACE_STATE_LOCK, session._state_lock:
            session.queued = False
            session._job = None
            session.updated, session.title = previous_updated, previous_title
            try:
                session.save()
            except OSError:
                pass
        raise HTTPException(500, f"could not persist background job: {exc}")
    _ensure_queue_thread()
    GENERATION_QUEUE.put(job)
    _notify_queue_positions()
    return job


def _dispatch_next_followup(session: Session) -> GenerationJob | None:
    """Atomically promote the oldest same-chat follow-up into the global queue."""
    if _SHUTTING_DOWN:
        return None
    with session._state_lock:
        if (session.running or session.queued or session._dispatching_followup
                or not session.pending_messages):
            return None
        session._dispatching_followup = True
        pending = session.pending_messages.pop(0)
        try:
            session.save()
        except OSError:
            session.pending_messages.insert(0, pending)
            session._dispatching_followup = False
            return None
    try:
        return _enqueue_job(
            session, pending["text"], display_message=pending["text"])
    except HTTPException:
        with session._state_lock:
            session.pending_messages.insert(0, pending)
            try:
                session.save()
            except OSError:
                pass
        return None
    finally:
        with session._state_lock:
            session._dispatching_followup = False


def _jobs_active() -> bool:
    with JOBS_LOCK:
        return bool(ACTIVE_JOBS)


@app.get("/api/jobs")
def list_jobs():
    with JOBS_LOCK:
        return [ACTIVE_JOBS[jid].meta() for jid in JOB_ORDER
                if jid in ACTIVE_JOBS]


def _stream_job(job: GenerationJob) -> StreamingResponse:
    def stream():
        try:
            while True:
                try:
                    item = job.events.get(timeout=5.0)
                except queue.Empty:
                    yield "data: " + json.dumps({
                        "type": "heartbeat",
                        "data": job.activity_snapshot(),
                    }, ensure_ascii=False) + "\n\n"
                    continue
                if item is None:
                    yield 'data: {"type": "done"}\n\n'
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        finally:
            job.release_stream()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/jobs/{job_id}/stream")
def stream_existing_job(job_id: str):
    with JOBS_LOCK:
        job = ACTIVE_JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "no such active job")
    if not job.claim_stream():
        raise HTTPException(409, "this job stream is already connected")
    return _stream_job(job)


def _recover_jobs() -> None:
    try:
        if JOBS_FILE.stat().st_size > 10 * 1024 * 1024:
            return
        payload = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, list):
        return
    for raw in payload[:100]:
        if not isinstance(raw, dict):
            continue
        job_id, sid = raw.get("id"), raw.get("session_id")
        message, state = raw.get("message"), raw.get("state")
        display_message = raw.get("display_message", message)
        attachment_names = raw.get("attachments", [])
        steers = raw.get("steers", [])
        created = raw.get("created")
        if (not isinstance(job_id, str)
                or not re.fullmatch(r"[a-f0-9]{16}", job_id)
                or not isinstance(sid, str) or sid not in SESSIONS
                or not isinstance(message, str) or not message.strip()
                or len(message) > 3_000_000
                or not isinstance(display_message, str)
                or not isinstance(attachment_names, list)
                or not all(isinstance(name, str) for name in attachment_names)
                or not isinstance(steers, list) or len(steers) > 20
                or not all(isinstance(text, str) and text.strip()
                           and len(text) <= 3_000_000 for text in steers)
                or state not in {"queued", "running"}
                or isinstance(created, bool)
                or not isinstance(created, (int, float))
                or not math.isfinite(created)):
            continue
        session = SESSIONS[sid]
        try:
            attachments = _attachment_metadata(session, attachment_names)
        except HTTPException:
            attachments = []
        if session.running or session.queued:
            continue
        if state == "queued":
            _enqueue_job(session, message, job_id, created,
                         display_message, attachments, steers)
        else:
            user_item: dict = {"t": "user", "text": display_message}
            if attachments:
                user_item["attachments"] = attachments
            session.display.extend([
                user_item,
                *({"t": "steer", "text": text} for text in steers),
                {"t": "error", "text": (
                    "This job was interrupted when the app stopped. It was not "
                    "automatically replayed because earlier tool actions may "
                    "already have changed files. Retry it if appropriate.")},
            ])
            session.updated = time.time()
            if session.title == "New chat":
                session.title = display_message.strip().replace("\n", " ")[:60]
            try:
                session.save()
            except OSError:
                pass
    _persist_jobs()
    for session in list(SESSIONS.values()):
        _dispatch_next_followup(session)


# ---------- chat ----------
class ChatBody(BaseModel):
    session_id: str
    message: str
    attachments: list[str] = Field(default_factory=list)


class FollowupBody(BaseModel):
    message: str
    action: str = "queue"


def _validate_followup_text(text: str) -> str:
    clean = text.strip()
    if not clean:
        raise HTTPException(422, "message cannot be empty")
    max_chars = max(4000, CFG.compact_threshold * 3)
    if len(clean) > max_chars:
        raise HTTPException(413, f"message is too large (limit {max_chars:,} characters)")
    return clean


@app.get("/api/sessions/{sid}/followups")
def list_followups(sid: str):
    session = _get(sid)
    with session._state_lock:
        return {"pending_messages": list(session.pending_messages)}


@app.post("/api/sessions/{sid}/followups")
def add_followup(sid: str, body: FollowupBody):
    session = _get(sid)
    text = _validate_followup_text(body.message)
    if body.action == "steer":
        with session._state_lock:
            job = session._job
            if job is None or not job.steer(text):
                raise HTTPException(
                    409, "this chat is no longer accepting steering")
        return {"action": "steer", "pending_messages": list(session.pending_messages)}
    if body.action != "queue":
        raise HTTPException(422, "action must be 'queue' or 'steer'")
    with session._state_lock:
        if len(session.pending_messages) >= 20:
            raise HTTPException(429, "this chat already has 20 queued messages")
        item = {"id": uuid.uuid4().hex[:12], "text": text,
                "created": time.time()}
        session.pending_messages.append(item)
        try:
            session.save()
        except OSError as exc:
            session.pending_messages.remove(item)
            raise HTTPException(500, f"could not persist queued message: {exc}")
    job = _dispatch_next_followup(session)
    return {"action": "queue", "queued": item,
            "started_job_id": job.id if job else None,
            "pending_messages": list(session.pending_messages)}


@app.delete("/api/sessions/{sid}/followups/{message_id}")
def delete_followup(sid: str, message_id: str):
    session = _get(sid)
    with session._state_lock:
        item = next((item for item in session.pending_messages
                     if item["id"] == message_id), None)
        if item is None:
            raise HTTPException(404, "no such queued message")
        session.pending_messages.remove(item)
        session.save()
        return {"pending_messages": list(session.pending_messages)}


@app.post("/api/sessions/{sid}/followups/{message_id}/steer")
def promote_followup_to_steer(sid: str, message_id: str):
    session = _get(sid)
    with session._state_lock:
        item = next((item for item in session.pending_messages
                     if item["id"] == message_id), None)
        if item is None:
            raise HTTPException(404, "no such queued message")
        job = session._job
        if job is None or not job.steer(item["text"]):
            raise HTTPException(409, "the current turn is no longer steerable")
        session.pending_messages.remove(item)
        session.save()
        return {"pending_messages": list(session.pending_messages)}


_INLINE_ATTACHMENT_EXTS = {
    ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".gif": "image", ".webp": "image",
    ".mp4": "video", ".webm": "video", ".mov": "video",
    ".mp3": "audio", ".wav": "audio", ".ogg": "audio",
}


def _attachment_metadata(session: Session, names: list[str]) -> list[dict]:
    """Re-derive safe attachment metadata from files in the session workspace."""
    if len(names) > MAX_UPLOAD_FILES:
        raise HTTPException(413, f"attach at most {MAX_UPLOAD_FILES} files")
    workspace = Path(session.workspace).resolve()
    result: list[dict] = []
    seen: set[str] = set()
    for raw_name in names:
        if (not isinstance(raw_name, str) or not raw_name
                or Path(raw_name).name != raw_name or raw_name in {".", ".."}):
            raise HTTPException(422, "attachment names must be workspace filenames")
        if raw_name in seen:
            continue
        seen.add(raw_name)
        path = (workspace / raw_name).resolve()
        try:
            if not path.is_relative_to(workspace) or not path.is_file():
                raise HTTPException(404, f"attachment no longer exists: {raw_name}")
            size = path.stat().st_size
        except OSError:
            raise HTTPException(404, f"attachment no longer exists: {raw_name}")
        ext = path.suffix.lower()
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        result.append({
            "name": path.name,
            "size": size,
            "mime": mime,
            "kind": _INLINE_ATTACHMENT_EXTS.get(ext, "file"),
            "previewable": ext in PREVIEWABLE,
        })
    return result


@app.post("/api/chat")
def chat(body: ChatBody):
    s = _get(body.session_id)
    attachments = _attachment_metadata(s, body.attachments)
    if not body.message.strip() and not attachments:
        raise HTTPException(422, "message cannot be empty")
    display_message = body.message.strip() or "Please look at the attached file(s)."
    message = display_message
    if attachments:
        message += "\n\n[Attached files, saved in the workspace: " \
            + ", ".join(item["name"] for item in attachments) + "]"
    max_chars = max(4000, CFG.compact_threshold * 3)
    if len(message) > max_chars:
        raise HTTPException(
            413,
            f"message is too large for this model window; attach it as a file "
            f"instead (limit {max_chars:,} characters)",
        )
    job = _enqueue_job(s, message, display_message=display_message,
                       attachments=attachments)
    job.claim_stream()
    return _stream_job(job)


@app.get("/api/memory")
def get_memory():
    from .memory import MEMORY_FILE, memory_text
    return {"content": memory_text(), "path": str(MEMORY_FILE)}


# ---------- workspace files ----------
def _ws_for(sid: str | None) -> Path:
    """The workspace to serve file requests from: the chat's own folder,
    or the global default when no chat exists yet."""
    if sid is not None:
        return Path(_get(sid).workspace)
    return get_default_workspace()


@app.get("/api/files")
def list_files(sid: str | None = None):
    ws = _ws_for(sid)
    files = []
    if ws.is_dir():
        for p in ws.iterdir():
            try:
                is_file = p.is_file() and not p.is_symlink()
                st = p.stat() if is_file else None
            except OSError:
                continue
            if is_file and st is not None:
                files.append({"name": p.name, "size": st.st_size,
                              "mtime": st.st_mtime,
                              "previewable": p.suffix.lower() in PREVIEWABLE})
    return sorted(files, key=lambda f: f["mtime"], reverse=True)


# posts page console errors up to the artifact panel (parent frame)
CONSOLE_BRIDGE = (
    '<script>(function(){var E=[];var t=null;function send(){try{'
    'window.parent.postMessage({type:"lmh-console",entries:E.slice(0,15)},"*");'
    '}catch(e){}}function add(k,m){E.push(k+": "+String(m).slice(0,250));'
    'clearTimeout(t);t=setTimeout(send,300);}window.addEventListener("error",'
    'function(e){if(e.target&&(e.target.src||e.target.href)){add("failed to load",'
    'e.target.src||e.target.href);}else{add("error",e.message+" (line "+'
    '(e.lineno||"?")+")");}},true);window.addEventListener("unhandledrejection",'
    'function(e){add("rejection",e.reason);});var c=console.error;console.error='
    'function(){add("console.error",Array.prototype.slice.call(arguments).join(" "));'
    'if(c)c.apply(console,arguments);};})();</script>')

MAX_RENDER_BYTES = 20 * 1024 * 1024


@app.get("/api/preview/{name:path}")
def preview_file(name: str, sid: str | None = None):
    p = _safe_workspace_path(name, sid)
    ext = p.suffix.lower()
    streamed = {".png", ".jpg", ".jpeg", ".gif", ".webp",
                ".mp4", ".webm", ".mov", ".mp3", ".wav", ".ogg"}
    try:
        if ext not in streamed and p.stat().st_size > MAX_RENDER_BYTES:
            raise HTTPException(413, "file is too large to render safely; download it instead")
    except OSError as e:
        raise HTTPException(404, f"could not inspect file: {e}")
    if ext in OFFICE_EXTS:
        try:
            validate_office_archive(p)
        except ValueError as e:
            raise HTTPException(413, str(e))
    if ext in (".html", ".htm"):
        # inject the console bridge so the artifact panel can show errors live
        html = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"<head[^>]*>", html, re.I)
        if m:
            html = html[:m.end()] + CONSOLE_BRIDGE + html[m.end():]
        else:
            html = CONSOLE_BRIDGE + html
        return HTMLResponse(html, headers={
            "Content-Security-Policy": "sandbox allow-scripts allow-modals",
        })
    # other renderable types (incl. video/audio, played natively) as-is
    if ext in (".svg", ".png", ".jpg", ".jpeg", ".gif",
               ".webp", ".mp4", ".webm", ".mov", ".mp3", ".wav", ".ogg"):
        headers = ({"Content-Security-Policy": "sandbox"}
                   if ext == ".svg" else None)
        return FileResponse(p, headers=headers)
    return HTMLResponse(build_preview(p), headers={
        "Content-Security-Policy": "sandbox",
    })


_SKIP_DIRS = {".git", ".lmh", "node_modules", "__pycache__", ".venv", "venv"}


@app.get("/api/tree")
def file_tree(sid: str | None = None):
    """Nested workspace tree (depth-limited) for the live file panel."""
    root = _ws_for(sid)
    count = [0]

    def walk(d: Path, depth: int) -> list[dict]:
        out: list[dict] = []
        try:
            entries = sorted(d.iterdir(),
                             key=lambda e: (e.is_file(), e.name.lower()))
        except OSError:
            return out
        for e in entries:
            if count[0] >= 400:
                break
            try:
                is_symlink = e.is_symlink()
                is_dir = e.is_dir()
            except OSError:
                continue
            if is_symlink or e.name.startswith(".__lmh_check__") \
                    or e.name in _SKIP_DIRS:
                continue
            count[0] += 1
            rel = e.relative_to(root).as_posix()
            if is_dir:
                out.append({"name": e.name, "path": rel, "dir": True,
                            "children": walk(e, depth + 1) if depth < 3 else []})
            else:
                try:
                    st = e.stat()
                except OSError:
                    continue
                out.append({"name": e.name, "path": rel, "dir": False,
                            "size": st.st_size, "mtime": st.st_mtime,
                            "previewable": e.suffix.lower() in PREVIEWABLE})
        return out

    return {"root": str(root), "tree": walk(root, 1)}


def _safe_workspace_path(name: str, sid: str | None = None,
                         want: str = "file") -> Path:
    """Resolve a workspace-relative path and refuse anything that escapes
    the workspace. want: 'file' | 'dir' | 'any' | 'new' (need not exist)."""
    ws = _ws_for(sid).resolve()
    p = (ws / name).resolve()
    try:
        ok = p.is_relative_to(ws) and p != ws
    except ValueError:
        ok = False
    if not ok:
        raise HTTPException(404, "no such file")
    if want == "file" and not p.is_file():
        raise HTTPException(404, "no such file")
    if want == "dir" and not p.is_dir():
        raise HTTPException(404, "no such folder")
    if want == "any" and not p.exists():
        raise HTTPException(404, "no such file")
    return p


def _ensure_workspace_idle(workspace: Path) -> None:
    target = workspace.resolve()
    with SESSIONS_LOCK:
        sessions = list(SESSIONS.values())
    for session in sessions:
        if (session.running or session.queued) \
                and Path(session.workspace).resolve() == target:
            raise HTTPException(409, "stop generation before changing workspace files")


@app.get("/api/files/{name:path}")
def download_file(name: str, sid: str | None = None):
    p = _safe_workspace_path(name, sid)
    # Always force a download. Rendering user/model-created HTML under the
    # API origin would let it call local endpoints outside the preview sandbox.
    return FileResponse(p, filename=p.name)


@app.delete("/api/files/{name:path}")
def delete_file(name: str, sid: str | None = None):
    """Delete a workspace file or folder (folders recursively)."""
    with WORKSPACE_STATE_LOCK:
        workspace = _ws_for(sid)
        _ensure_workspace_idle(workspace)
        p = _safe_workspace_path(name, sid, want="any")
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
        except OSError as e:
            raise HTTPException(400, f"could not delete: {e}")
    return {"ok": True}


class FileOpBody(BaseModel):
    sid: str | None = None
    path: str
    new_name: str | None = None


@app.post("/api/files/rename")
def rename_file(body: FileOpBody):
    """Rename a file or folder in place (same parent directory)."""
    with WORKSPACE_STATE_LOCK:
        workspace = _ws_for(body.sid)
        _ensure_workspace_idle(workspace)
        p = _safe_workspace_path(body.path, body.sid, want="any")
        new_name = (body.new_name or "").strip()
        if (not new_name or new_name in {".", ".."} or "/" in new_name
                or "\\" in new_name or Path(new_name).name != new_name):
            raise HTTPException(400, "give a plain file or folder name")
        target = p.parent / new_name
        if target.exists():
            raise HTTPException(409, "something with that name already exists")
        try:
            p.rename(target)
        except OSError as e:
            raise HTTPException(400, f"could not rename: {e}")
        rel = target.relative_to(workspace.resolve()).as_posix()
    return {"ok": True, "path": rel}


@app.post("/api/files/mkdir")
def make_folder(body: FileOpBody):
    """Create a new folder inside the workspace."""
    with WORKSPACE_STATE_LOCK:
        workspace = _ws_for(body.sid)
        _ensure_workspace_idle(workspace)
        p = _safe_workspace_path(body.path, body.sid, want="new")
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise HTTPException(400, f"could not create folder: {e}")
    return {"ok": True}


def _native_folder_dialog(start_dir: str) -> str | None:
    """Open the OS-native folder picker on the machine running the server.
    Returns the chosen path, or None if cancelled/unavailable."""
    system = platform.system()
    try:
        # packaged app on Windows: our exe has no -c mode; it has
        # --pick-folder (macOS keeps the nicer native osascript picker below)
        if getattr(sys, "frozen", False) and system == "Windows":
            from .tools.shell import _frozen_cli_exe
            r = subprocess.run([_frozen_cli_exe(), "--pick-folder", start_dir],
                               capture_output=True, text=True, timeout=300,
                               creationflags=CREATE_NO_WINDOW)
            path = (r.stdout or "").strip()
            return path.replace("/", "\\") if path else None
        if system == "Windows":
            # tkinter's askdirectory uses the modern IFileOpenDialog picker
            # (Tk 8.6.11+), same one web apps get for file uploads
            import os as _os
            env = {**_os.environ, "LMH_PICK_START": start_dir}
            code = (
                "import os, tkinter as tk, tkinter.filedialog as fd\n"
                "root = tk.Tk(); root.withdraw(); root.attributes('-topmost', 1)\n"
                "print(fd.askdirectory(initialdir=os.environ.get('LMH_PICK_START'),"
                " title='Choose the Little Harness workspace folder', mustexist=False)"
                " or '')")
            r = subprocess.run([sys.executable, "-c", code], env=env,
                               capture_output=True, text=True, timeout=300,
                               creationflags=CREATE_NO_WINDOW)
            path = (r.stdout or "").strip()
            return path.replace("/", "\\") if path else None
        if system == "Darwin":
            r = subprocess.run(
                ["osascript", "-e",
                 'POSIX path of (choose folder with prompt "Choose the Little Harness workspace folder")'],
                capture_output=True, text=True, timeout=300)
            path = (r.stdout or "").strip()
            return path or None
        # Linux: zenity → kdialog → tkinter
        if shutil.which("zenity"):
            r = subprocess.run(["zenity", "--file-selection", "--directory",
                                "--title=Choose the Little Harness workspace folder"],
                               capture_output=True, text=True, timeout=300)
            return (r.stdout or "").strip() or None
        if shutil.which("kdialog"):
            r = subprocess.run(["kdialog", "--getexistingdirectory", start_dir],
                               capture_output=True, text=True, timeout=300)
            return (r.stdout or "").strip() or None
        r = subprocess.run(
            ["python3", "-c",
             "import tkinter as tk, tkinter.filedialog as fd; root = tk.Tk(); "
             "root.withdraw(); root.attributes('-topmost', 1); "
             "print(fd.askdirectory() or '')"],
            capture_output=True, text=True, timeout=300)
        return (r.stdout or "").strip() or None
    except (subprocess.TimeoutExpired, OSError):
        return None


_DIALOG_LOCK = threading.Lock()


class BrowseBody(BaseModel):
    sid: str | None = None


@app.post("/api/workspace/browse")
def browse_workspace(body: BrowseBody | None = None):
    """Pop the native folder picker. With a sid, the chosen folder becomes
    that chat's workspace; without one it becomes the default for new chats."""
    sid = body.sid if body else None
    current = _ws_for(sid)
    if sid is not None and (_get(sid).running or _get(sid).queued):
        raise HTTPException(409, "stop generation before changing the workspace")
    if not _DIALOG_LOCK.acquire(blocking=False):
        raise HTTPException(409, "a folder picker is already open")
    try:
        chosen = _native_folder_dialog(str(current))
    finally:
        _DIALOG_LOCK.release()
    if not chosen:
        return {"cancelled": True, "workspace": str(current)}
    try:
        if sid:
            session = _get(sid)
            with WORKSPACE_STATE_LOCK, session._state_lock:
                if session.running or session.queued:
                    raise HTTPException(
                        409, "generation started while the folder picker was open; try again")
                session.set_workspace(chosen)
            return {"cancelled": False, "workspace": session.workspace}
        set_default_workspace(chosen)
    except OSError as e:
        raise HTTPException(400, f"can't use that folder: {e}")
    return {"cancelled": False, "workspace": str(get_default_workspace())}


MAX_UPLOAD = 50 * 1024 * 1024
MAX_UPLOAD_TOTAL = 200 * 1024 * 1024
MAX_UPLOAD_FILES = 20
UPLOAD_CHUNK = 1024 * 1024
_UPLOAD_LOCK = threading.Lock()


@app.post("/api/upload")
async def upload_files(files: list[UploadFile], sid: str | None = None):
    """Save pasted/uploaded files into the chat's workspace, collision-safe."""
    ws = _ws_for(sid)
    if not files:
        raise HTTPException(400, "no files were uploaded")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(413, f"upload at most {MAX_UPLOAD_FILES} files at once")
    ws.mkdir(parents=True, exist_ok=True)
    staged: list[tuple[Path, str]] = []
    temporary: list[Path] = []
    batch_total = 0
    try:
        for f in files:
            name = re.sub(
                r"[^\w.\- ()]", "_", Path(f.filename or "pasted").name,
            ) or "pasted"
            if name in {".", ".."}:
                name = "pasted"
            tmp = ws / f".__lmh_upload__.{uuid.uuid4().hex}.tmp"
            temporary.append(tmp)
            file_total = 0
            try:
                with tmp.open("xb") as out:
                    while chunk := await f.read(UPLOAD_CHUNK):
                        file_total += len(chunk)
                        batch_total += len(chunk)
                        if file_total > MAX_UPLOAD:
                            raise HTTPException(413, f"{f.filename} is over 50 MB")
                        if batch_total > MAX_UPLOAD_TOTAL:
                            raise HTTPException(413, "upload batch is over 200 MB")
                        out.write(chunk)
                staged.append((tmp, name))
            finally:
                try:
                    await f.close()
                except OSError:
                    pass

        committed: list[Path] = []
        try:
            with WORKSPACE_STATE_LOCK, _UPLOAD_LOCK:
                _ensure_workspace_idle(ws)
                reserved: set[Path] = set()
                planned: list[tuple[Path, Path]] = []
                for tmp, name in staged:
                    stem, ext = Path(name).stem, Path(name).suffix
                    target = ws / name
                    n = 1
                    while target.exists() or target in reserved:
                        target = ws / f"{stem}({n}){ext}"
                        n += 1
                    reserved.add(target)
                    planned.append((tmp, target))
                for tmp, target in planned:
                    os.replace(tmp, target)
                    committed.append(target)
        except (OSError, HTTPException) as e:
            for target in committed:
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
            if isinstance(e, HTTPException):
                raise
            raise HTTPException(400, f"could not save upload batch: {e}")
        names = [target.name for target in committed]
        # Keep `saved` for older clients; richer metadata is persisted with the
        # user message by /api/chat and drives inline chat previews.
        session = _get(sid) if sid is not None else Session(
            "000000000000", workspace=str(ws))
        return {"saved": names,
                "attachments": _attachment_metadata(session, names)}
    except OSError as e:
        raise HTTPException(400, f"could not stage upload batch: {e}")
    finally:
        for tmp in temporary:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


_SERVICES_STARTED = False
_SERVICES_LOCK = threading.Lock()


def begin_shutdown() -> None:
    """Prevent completed jobs from starting persisted follow-ups during exit."""
    global _SHUTTING_DOWN
    _SHUTTING_DOWN = True


def start_background_services() -> None:
    """Start side-effecting services only after the instance lock is held."""
    global _SERVICES_STARTED, _SHUTTING_DOWN
    with _SERVICES_LOCK:
        if _SERVICES_STARTED:
            return
        _SERVICES_STARTED = True
        _SHUTTING_DOWN = False
    # Do not make desktop startup wait on an offline model or slow MCP server.
    _schedule_settings_refresh(load_mcp_servers())
    _recover_jobs()


def main() -> None:
    from .instance import acquire_instance_lock
    if not acquire_instance_lock():
        print("Little Model Harness is already running for this data directory.",
              file=sys.stderr)
        return
    start_background_services()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8321
    print(f"Little Model Harness web UI: http://localhost:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
