"""Web app server: multi-conversation, streaming, files, settings.

Run with: python -m harness.server [port]
"""
from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from pathlib import Path

import platform
import re
import shutil
import subprocess
import sys

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from .agent import Agent
from .config import (DATA_DIR, ROOT, SESSIONS_DIR, get_default_workspace,
                     load_config, save_user_settings, set_default_workspace)
from .preview import PREVIEWABLE, build_preview

app = FastAPI(title="Little Model Harness")

# windowed app: console children must not pop terminal windows
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

CFG = load_config()          # one shared config: settings changes hit all sessions
MODEL_LOCK = threading.Lock()  # one generation at a time — single local model


class Session:
    def __init__(self, sid: str, title: str = "New chat",
                 created: float | None = None,
                 workspace: str | None = None) -> None:
        self.id = sid
        self.title = title
        self.created = created or time.time()
        self.updated = self.created
        self.pinned = False
        self.display: list[dict] = []   # UI-facing event log
        # each chat works in its own folder; new chats inherit the default
        self.workspace = workspace or str(get_default_workspace())
        self._agent: Agent | None = None

    @property
    def agent(self) -> Agent:
        if self._agent is None:
            self._agent = Agent(CFG, workspace=self.workspace)
        return self._agent

    def set_workspace(self, path: str) -> None:
        p = Path(path).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        self.workspace = str(p)
        if self._agent:
            self._agent.workspace = p
        self.save()

    def meta(self) -> dict:
        return {"id": self.id, "title": self.title, "created": self.created,
                "updated": self.updated, "messages": len(self.display),
                "pinned": self.pinned, "workspace": self.workspace}

    # ---- persistence ----
    def save(self) -> None:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "id": self.id, "title": self.title, "created": self.created,
            "updated": self.updated, "pinned": self.pinned,
            "workspace": self.workspace,
            "display": self.display,
            "messages": self._agent.ctx.messages if self._agent else [],
            "skills_loaded": sorted(self._agent.skills.loaded) if self._agent else [],
            "turn_no": self._agent.turn_no if self._agent else 0,
            "turn_marks": self._agent.turn_marks if self._agent else [],
            "checkpoints": self._agent.checkpoints if self._agent else [],
        }
        (SESSIONS_DIR / f"{self.id}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Session | None":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        s = cls(data["id"], data.get("title", "Chat"), data.get("created"),
                data.get("workspace"))
        s.updated = data.get("updated", s.created)
        s.pinned = data.get("pinned", False)
        s.display = data.get("display", [])
        if data.get("messages"):
            s._agent = Agent(CFG, workspace=s.workspace)
            s._agent.ctx.messages = data["messages"]
            s._agent.skills.loaded = set(data.get("skills_loaded", []))
            s._agent.turn_no = data.get("turn_no", 0)
            s._agent.turn_marks = data.get("turn_marks", [])
            s._agent.checkpoints = data.get("checkpoints", [])
        return s


SESSIONS: dict[str, Session] = {}
for _p in sorted(SESSIONS_DIR.glob("*.json")) if SESSIONS_DIR.is_dir() else []:
    _s = Session.load(_p)
    if _s is None:
        continue
    if not _s.display:  # prune abandoned empty sessions
        _p.unlink(missing_ok=True)
        continue
    SESSIONS[_s.id] = _s


def _get(sid: str) -> Session:
    if sid not in SESSIONS:
        raise HTTPException(404, "no such session")
    return SESSIONS[sid]


# ---------- pages ----------
@app.get("/")
def index():
    return FileResponse(ROOT / "web" / "index.html")


# ---------- meta ----------
_PROBE = Agent(CFG)  # for skills metadata only; never makes a request


@app.get("/api/status")
def status():
    skills = [{"name": s.name, "description": s.description,
               "category": s.category, "hint": s.hint}
              for s in _PROBE.skills.skills.values()]
    return {"model": CFG.model, "base_url": CFG.base_url,
            "workspace": str(get_default_workspace()),
            "data_dir": str(DATA_DIR), "window": CFG.context_window,
            "skills": skills, "busy": MODEL_LOCK.locked()}


class SettingsBody(BaseModel):
    temperature: float | None = None
    max_output_tokens: int | None = None
    workspace: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    context_window: int | None = None


@app.get("/api/settings")
def get_settings():
    return {"temperature": CFG.temperature,
            # derived: max output per message == compaction threshold
            "max_output_tokens": CFG.compact_threshold,
            "workspace": str(get_default_workspace()),
            "model": CFG.model, "base_url": CFG.base_url,
            "api_key_set": bool(CFG.api_key and CFG.api_key != "not-needed"),
            "context_window": CFG.context_window,
            "server_n_ctx": DETECTED["n_ctx"],
            "compact_threshold": CFG.compact_threshold}


def _apply_window(window: int) -> None:
    """Compaction fires when the conversation reaches window - reserve
    (16k of generation headroom), floored at half the window."""
    CFG.context_window = max(2048, min(1_048_576, window))
    CFG.compact_threshold = max(CFG.context_window - CFG.output_reserve,
                                CFG.context_window // 2)
    CFG.compact_target = CFG.compact_threshold // 2


DETECTED = {"n_ctx": None}


def _sync_window() -> None:
    """Ask the model server how much context it actually has (llama.cpp and
    LM Studio expose meta.n_ctx) and clamp our window to it. This is what
    keeps the harness working when someone loads a model at 4k."""
    try:
        r = httpx.get(f"{CFG.base_url}/models", timeout=5.0)
        for m in r.json().get("data") or []:
            n = ((m.get("meta") or {}).get("n_ctx"))
            if n:
                DETECTED["n_ctx"] = int(n)
                break
    except Exception:
        return
    n = DETECTED["n_ctx"]
    if n and n < CFG.context_window:
        _apply_window(n)


@app.post("/api/settings")
def set_settings(body: SettingsBody):
    if body.temperature is not None:
        CFG.temperature = max(0.0, min(2.0, body.temperature))
    # max_output_tokens is derived from the window now; body field ignored
    if body.context_window is not None:
        _apply_window(body.context_window)
    endpoint_changed = False
    if body.base_url is not None and body.base_url.strip():
        CFG.base_url = body.base_url.strip().rstrip("/")
        endpoint_changed = True
    if body.model is not None and body.model.strip():
        CFG.model = body.model.strip()
        endpoint_changed = True
    if body.api_key is not None:  # empty string clears the key
        CFG.api_key = body.api_key.strip() or "not-needed"
        endpoint_changed = True
    if endpoint_changed:
        for s in SESSIONS.values():
            if s._agent:
                s._agent.llm.reconfigure(CFG.base_url, CFG.model, CFG.api_key)
    _sync_window()  # re-clamp to whatever the (possibly new) server supports
    save_user_settings({"temperature": CFG.temperature,
                        "base_url": CFG.base_url, "model": CFG.model,
                        "api_key": CFG.api_key,
                        "context_window": CFG.context_window})
    if body.workspace is not None and body.workspace.strip():
        try:
            set_default_workspace(body.workspace.strip())
        except OSError as e:
            raise HTTPException(400, f"can't use that folder: {e}")
    return get_settings()


# ---------- sessions ----------
@app.get("/api/sessions")
def list_sessions():
    return sorted((s.meta() for s in SESSIONS.values()),
                  key=lambda m: (not m["pinned"], -m["updated"]))


@app.get("/api/search")
def search_chats(q: str):
    """Full-content search across all sessions for the sidebar."""
    terms = [t for t in re.findall(r"\w{2,}", q.lower())]
    if not terms:
        return []
    out = []
    for s in SESSIONS.values():
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


@app.post("/api/sessions")
def create_session():
    s = Session(uuid.uuid4().hex[:12])
    SESSIONS[s.id] = s
    return s.meta()


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    s = _get(sid)
    st = s.agent.context_status() if s._agent else {
        "estimated_tokens": 0, "window": CFG.context_window,
        "compactions": 0, "last_prompt_tokens": 0, "skills_loaded": []}
    return {**s.meta(), "display": s.display, "context": st}


class RenameBody(BaseModel):
    title: str | None = None
    pinned: bool | None = None


@app.patch("/api/sessions/{sid}")
def rename_session(sid: str, body: RenameBody):
    s = _get(sid)
    if body.title is not None:
        s.title = body.title.strip()[:80] or s.title
    if body.pinned is not None:
        s.pinned = body.pinned
    s.save()
    return s.meta()


@app.delete("/api/sessions/{sid}")
def delete_session(sid: str):
    _get(sid)
    del SESSIONS[sid]
    f = SESSIONS_DIR / f"{sid}.json"
    if f.exists():
        f.unlink()
    return {"ok": True}


@app.post("/api/sessions/{sid}/stop")
def stop_session(sid: str):
    s = _get(sid)
    if s._agent:
        s._agent.request_stop()
    return {"ok": True}


class RevertBody(BaseModel):
    display_index: int


def _revert(s: Session, display_index: int) -> dict:
    """Rewind chat AND restore files to just before the user turn at (or
    nearest before) display_index. Turn N = the Nth user item."""
    if MODEL_LOCK.locked():
        raise HTTPException(409, "busy — stop generation first")
    user_items = [i for i, it in enumerate(s.display) if it.get("t") == "user"]
    if not user_items:
        raise HTTPException(400, "nothing to revert")
    # the turn whose user item is at/nearest before display_index
    turn = next((n for n in range(len(user_items), 0, -1)
                 if user_items[n - 1] <= display_index), 1)
    ui = user_items[turn - 1]
    text = s.display[ui]["text"]
    s.display = s.display[:ui]
    restored: list[str] = []
    if s._agent:
        restored = s._agent.revert_to_turn(turn)
    s.updated = time.time()
    s.save()
    return {"text": text, "restored_files": restored, "turn": turn}


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


# ---------- chat ----------
class ChatBody(BaseModel):
    session_id: str
    message: str


@app.post("/api/chat")
def chat(body: ChatBody):
    s = _get(body.session_id)
    q: queue.Queue = queue.Queue()

    # server-side mirror of what the client renders, for persistence
    turn: list[dict] = [{"t": "user", "text": body.message}]

    def flush_text(kind: str, buf: list[str]) -> None:
        if buf:
            turn.append({"t": kind, "text": "".join(buf)})
            buf.clear()

    reasoning_buf: list[str] = []
    text_buf: list[str] = []

    def emit(etype: str, data) -> None:
        if etype == "reasoning_delta":
            flush_text("text", text_buf)
            reasoning_buf.append(data)
        elif etype == "content_delta":
            flush_text("reasoning", reasoning_buf)
            text_buf.append(data)
        elif etype == "tool_call":
            flush_text("reasoning", reasoning_buf)
            flush_text("text", text_buf)
            turn.append({"t": "tool", "name": data["name"],
                         "args": data["arguments"], "result": None})
        elif etype == "tool_result":
            for item in reversed(turn):
                if item.get("t") == "tool" and item["result"] is None:
                    item["result"] = data["result"]
                    break
        elif etype == "context":
            turn.append({"t": "notice", "text": str(data)})
        elif etype == "error":
            turn.append({"t": "error", "text": str(data)})
        q.put({"type": etype, "data": data})

    def worker() -> None:
        with MODEL_LOCK:
            try:
                final = s.agent.run_turn(body.message, on_event=emit)
                flush_text("reasoning", reasoning_buf)
                flush_text("text", text_buf)
                if not any(i.get("t") == "text" and i["text"].strip() == final.strip()
                           for i in turn):
                    turn.append({"t": "text", "text": final})
                q.put({"type": "final", "data": final})
            except Exception as e:  # crash-proof the worker
                turn.append({"t": "error", "text": f"{type(e).__name__}: {e}"})
                q.put({"type": "error", "data": f"{type(e).__name__}: {e}"})
            finally:
                s.display.extend(turn)
                s.updated = time.time()
                if s.title == "New chat":
                    s.title = body.message.strip().replace("\n", " ")[:60]
                s.save()
                q.put({"type": "session", "data": s.meta()})
                q.put({"type": "context", "data": None})
                q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        while True:
            item = q.get()
            if item is None:
                yield 'data: {"type": "done"}\n\n'
                break
            if item["type"] == "context" and item["data"] is None:
                item = {"type": "context_status", "data": s.agent.context_status()}
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/memory")
def get_memory():
    from .memory import MEMORY_FILE, memory_text
    return {"content": memory_text(), "path": str(MEMORY_FILE)}


# ---------- workspace files ----------
def _ws_for(sid: str | None) -> Path:
    """The workspace to serve file requests from: the chat's own folder,
    or the global default when no chat exists yet."""
    if sid and sid in SESSIONS:
        return Path(SESSIONS[sid].workspace)
    return get_default_workspace()


@app.get("/api/files")
def list_files(sid: str | None = None):
    ws = _ws_for(sid)
    files = []
    if ws.is_dir():
        for p in ws.iterdir():
            if p.is_file():
                st = p.stat()
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


@app.get("/api/preview/{name:path}")
def preview_file(name: str, sid: str | None = None):
    p = _safe_workspace_path(name, sid)
    ext = p.suffix.lower()
    if ext in (".html", ".htm"):
        # inject the console bridge so the artifact panel can show errors live
        html = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"<head[^>]*>", html, re.I)
        if m:
            html = html[:m.end()] + CONSOLE_BRIDGE + html[m.end():]
        else:
            html = CONSOLE_BRIDGE + html
        return HTMLResponse(html)
    # other renderable types (incl. video/audio, played natively) as-is
    if ext in (".svg", ".png", ".jpg", ".jpeg", ".gif",
               ".webp", ".mp4", ".webm", ".mov", ".mp3", ".wav", ".ogg"):
        return FileResponse(p)
    return HTMLResponse(build_preview(p))


_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}


@app.get("/api/tree")
def file_tree(sid: str | None = None):
    """Nested workspace tree (depth-limited) for the live file panel."""
    root = _ws_for(sid)
    count = [0]

    def walk(d: Path, depth: int) -> list[dict]:
        out = []
        try:
            entries = sorted(d.iterdir(),
                             key=lambda e: (e.is_file(), e.name.lower()))
        except OSError:
            return out
        for e in entries:
            if count[0] >= 400:
                break
            if e.name.startswith(".__lmh_check__") or e.name in _SKIP_DIRS:
                continue
            count[0] += 1
            rel = e.relative_to(root).as_posix()
            if e.is_dir():
                out.append({"name": e.name, "path": rel, "dir": True,
                            "children": walk(e, depth + 1) if depth < 3 else []})
            else:
                st = e.stat()
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


@app.get("/api/files/{name:path}")
def download_file(name: str, sid: str | None = None, inline: bool = False):
    p = _safe_workspace_path(name, sid)
    if inline:
        return FileResponse(p)
    return FileResponse(p, filename=p.name)


@app.delete("/api/files/{name:path}")
def delete_file(name: str, sid: str | None = None):
    """Delete a workspace file or folder (folders recursively)."""
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
    p = _safe_workspace_path(body.path, body.sid, want="any")
    new_name = Path(body.new_name or "").name  # strip any path components
    if not new_name:
        raise HTTPException(400, "give a new name")
    target = p.parent / new_name
    if target.exists():
        raise HTTPException(409, "something with that name already exists")
    try:
        p.rename(target)
    except OSError as e:
        raise HTTPException(400, f"could not rename: {e}")
    rel = target.relative_to(_ws_for(body.sid).resolve()).as_posix()
    return {"ok": True, "path": rel}


@app.post("/api/files/mkdir")
def make_folder(body: FileOpBody):
    """Create a new folder inside the workspace."""
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
    if not _DIALOG_LOCK.acquire(blocking=False):
        raise HTTPException(409, "a folder picker is already open")
    try:
        chosen = _native_folder_dialog(str(current))
    finally:
        _DIALOG_LOCK.release()
    if not chosen:
        return {"cancelled": True, "workspace": str(current)}
    try:
        if sid and sid in SESSIONS:
            SESSIONS[sid].set_workspace(chosen)
            return {"cancelled": False, "workspace": SESSIONS[sid].workspace}
        set_default_workspace(chosen)
    except OSError as e:
        raise HTTPException(400, f"can't use that folder: {e}")
    return {"cancelled": False, "workspace": str(get_default_workspace())}


MAX_UPLOAD = 50 * 1024 * 1024


@app.post("/api/upload")
async def upload_files(files: list[UploadFile], sid: str | None = None):
    """Save pasted/uploaded files into the chat's workspace, collision-safe."""
    ws = _ws_for(sid)
    ws.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        raw = await f.read()
        if len(raw) > MAX_UPLOAD:
            raise HTTPException(413, f"{f.filename} is over 50 MB")
        name = re.sub(r"[^\w.\- ()]", "_", Path(f.filename or "pasted").name) or "pasted"
        stem, ext = Path(name).stem, Path(name).suffix
        target = ws / name
        n = 1
        while target.exists():
            target = ws / f"{stem}({n}){ext}"
            n += 1
        target.write_bytes(raw)
        saved.append(target.name)
    return {"saved": saved}


_sync_window()  # clamp our budget to the model server's real context size


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8321
    print(f"Little Model Harness web UI: http://localhost:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
