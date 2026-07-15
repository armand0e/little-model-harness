"""In-process application service used by the Qt client.

The native UI deliberately calls the harness domain objects directly.  No
localhost server, HTTP request, JSON serialization, or SSE connection sits
between a button click and the agent/job it controls.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException

from .. import server
from ..config import get_default_workspace


class ServiceError(RuntimeError):
    pass


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except HTTPException as exc:
        raise ServiceError(str(exc.detail)) from exc
    except (OSError, ValueError) as exc:
        raise ServiceError(str(exc)) from exc


class HarnessService:
    """Stable facade around the existing tested session/agent domain."""

    def start(self) -> None:
        server.start_background_services()

    def status(self) -> dict:
        return _call(server.status)

    def settings(self) -> dict:
        return _call(server.get_settings)

    def save_settings(self, values: dict) -> dict:
        try:
            body = server.SettingsBody(**values)
        except (TypeError, ValueError) as exc:
            raise ServiceError(str(exc)) from exc
        return _call(server.set_settings, body)

    def models(self) -> list[dict]:
        return _call(server.list_models)["models"]

    def sessions(self, mode: str | None = None) -> list[dict]:
        items = _call(server.list_sessions)
        if mode in {"agent", "chat", "research"}:
            items = [item for item in items if item.get("mode", "agent") == mode]
        return items

    def search_sessions(self, query: str, mode: str | None = None) -> list[dict]:
        items = _call(server.search_chats, query)
        if mode in {"agent", "chat", "research"}:
            items = [item for item in items if item.get("mode", "agent") == mode]
        return items

    def create_session(self, mode: str) -> dict:
        return _call(server.create_session, server.CreateSessionBody(mode=mode))

    def session(self, sid: str) -> dict:
        return _call(server.get_session, sid)

    def rename_session(self, sid: str, title: str) -> dict:
        return _call(server.rename_session, sid, server.RenameBody(title=title))

    def pin_session(self, sid: str, pinned: bool) -> dict:
        return _call(server.rename_session, sid, server.RenameBody(pinned=pinned))

    def delete_session(self, sid: str) -> None:
        _call(server.delete_session, sid)

    def stop(self, sid: str) -> dict:
        return _call(server.stop_session, sid)

    def job(self, sid: str):
        return _call(server._get, sid)._job

    def import_attachments(self, sid: str, paths: Iterable[str]) -> list[dict]:
        session = _call(server._get, sid)
        workspace = Path(session.workspace).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        for raw in list(paths)[:server.MAX_UPLOAD_FILES]:
            source = Path(raw).expanduser().resolve()
            if not source.is_file():
                raise ServiceError(f"Attachment does not exist: {source}")
            if source.stat().st_size > server.MAX_UPLOAD:
                raise ServiceError(f"Attachment is too large: {source.name}")
            name = source.name
            target = workspace / name
            index = 2
            while target.exists() and target.resolve() != source:
                target = workspace / f"{source.stem}-{index}{source.suffix}"
                index += 1
            if target.resolve() != source:
                shutil.copy2(source, target)
            copied.append(target.name)
        return _call(server._attachment_metadata, session, copied)

    def send(self, sid: str, text: str,
             attachment_paths: Iterable[str] = ()):  # GenerationJob
        session = _call(server._get, sid)
        attachments = self.import_attachments(sid, attachment_paths)
        display = text.strip() or "Please look at the attached file(s)."
        if not display and not attachments:
            raise ServiceError("Message cannot be empty")
        model_message = display
        if attachments:
            model_message += "\n\n[Attached files, saved in the workspace: " \
                + ", ".join(item["name"] for item in attachments) + "]"
        max_chars = max(4000, server.CFG.compact_threshold * 3)
        if len(model_message) > max_chars:
            raise ServiceError(
                f"Message is too large for this model (limit {max_chars:,} characters)")
        return _call(
            server._enqueue_job, session, model_message,
            display_message=display, attachments=attachments)

    def followup(self, sid: str, text: str, action: str) -> dict:
        return _call(server.add_followup, sid, server.FollowupBody(
            message=text, action=action))

    def followups(self, sid: str) -> list[dict]:
        return _call(server.list_followups, sid)["pending_messages"]

    def delete_followup(self, sid: str, message_id: str) -> list[dict]:
        return _call(server.delete_followup, sid, message_id)["pending_messages"]

    def promote_followup(self, sid: str, message_id: str) -> list[dict]:
        return _call(server.promote_followup_to_steer, sid, message_id)[
            "pending_messages"]

    def undo(self, sid: str) -> dict:
        return _call(server.undo_last_turn, sid)

    def revert(self, sid: str, display_index: int) -> dict:
        return _call(server.revert_to, sid, server.RevertBody(
            display_index=display_index))

    def set_workspace(self, sid: str, path: str) -> str:
        session = _call(server._get, sid)
        if session.running or session.queued:
            raise ServiceError("Stop generation before changing the workspace")
        _call(session.set_workspace, path)
        return session.workspace

    def workspace(self, sid: str | None) -> Path:
        return (Path(_call(server._get, sid).workspace) if sid
                else Path(get_default_workspace()))

    def file_tree(self, sid: str | None) -> dict:
        return _call(server.file_tree, sid)

    def delete_path(self, sid: str, relative: str) -> None:
        _call(server.delete_file, relative, sid)

    def rename_path(self, sid: str, old: str, new: str) -> dict:
        return _call(server.rename_file, server.FileOpBody(
            sid=sid, path=old, new_name=new))

    def make_folder(self, sid: str, path: str) -> dict:
        return _call(server.make_folder, server.FileOpBody(sid=sid, path=path))

    def memory(self) -> dict:
        return _call(server.get_memory)

    def skills(self) -> list[dict]:
        return self.status().get("skills", [])

    def close(self) -> None:
        server.begin_shutdown()
        with server.JOBS_LOCK:
            jobs = list(server.ACTIVE_JOBS.values())
        for job in jobs:
            job.cancel()
        deadline = time.monotonic() + 3
        while server.MODEL_LOCK.locked() and time.monotonic() < deadline:
            time.sleep(0.05)
        from .. import browser
        from ..mcp_client import MCP_HUB
        browser.close()
        MCP_HUB.close()
