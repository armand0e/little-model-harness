from __future__ import annotations

import copy
import io
import json
import queue
import threading
import time
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from harness.agent import Agent
from harness.config import Config
from harness.llm import LLMResponse
from harness.server import ChatBody, Session, app
import harness.server as server
import harness.config as config
import harness.memory as memory
from harness.tools.files import edit_file, read_file, search, write_file
from harness.tools import build_registry
from harness.verify import VISUAL_MARKER, _find_browser, visual_check
from harness.skills import SkillsManager


@pytest.fixture
def isolated_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg_state = copy.deepcopy(server.CFG.__dict__)
    detected_state = dict(server.DETECTED)
    settings_refresh_state = copy.deepcopy(server.SETTINGS_REFRESH)
    requested_window = server.REQUESTED_CONTEXT_WINDOW
    sessions_dir = tmp_path / "sessions"
    monkeypatch.setattr(server, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(server, "JOBS_FILE", tmp_path / "jobs.json")
    monkeypatch.setattr(server, "SESSIONS", {})
    # A failed test must not leave the process-wide model lock held.
    if server.MODEL_LOCK.locked():
        server.MODEL_LOCK.release()
    yield tmp_path
    with server.JOBS_LOCK:
        jobs = list(server.ACTIVE_JOBS.values())
    for job in jobs:
        job.cancel()
    deadline = time.time() + 2
    while (server.MODEL_LOCK.locked() or server._jobs_active()) \
            and time.time() < deadline:
        time.sleep(0.01)
    if server.MODEL_LOCK.locked():
        server.MODEL_LOCK.release()
    server.CFG.__dict__.clear()
    server.CFG.__dict__.update(cfg_state)
    server.DETECTED.clear()
    server.DETECTED.update(detected_state)
    with server.SETTINGS_REFRESH_LOCK:
        server.SETTINGS_REFRESH.clear()
        server.SETTINGS_REFRESH.update(settings_refresh_state)
    server.REQUESTED_CONTEXT_WINDOW = requested_window


def local_client() -> TestClient:
    return TestClient(app, base_url="http://localhost")


def test_local_api_rejects_untrusted_hosts_and_origins(isolated_server: Path):
    with TestClient(app, base_url="http://evil.example") as client:
        assert client.get("/api/status").status_code == 400

    with local_client() as client:
        response = client.get("/api/status", headers={"Origin": "https://evil.example"})
        assert response.status_code == 403
        assert client.get("/api/status").status_code == 200


def test_unknown_session_never_falls_back_to_default_workspace(
        isolated_server: Path):
    with local_client() as client:
        assert client.get("/api/files", params={"sid": "missing"}).status_code == 404
        assert client.get("/api/tree", params={"sid": "missing"}).status_code == 404


def test_workspace_paths_and_previews_are_sandboxed(isolated_server: Path):
    workspace = isolated_server / "workspace"
    workspace.mkdir()
    (workspace / "demo.html").write_text(
        "<script>fetch('/api/sessions')</script>", encoding="utf-8")
    (isolated_server / "secret.txt").write_text("secret", encoding="utf-8")
    session = Session("abcdef123456", workspace=str(workspace))
    server.SESSIONS[session.id] = session

    with local_client() as client:
        preview = client.get(
            "/api/preview/demo.html", params={"sid": session.id})
        assert preview.status_code == 200
        assert preview.headers["content-security-policy"].startswith("sandbox")
        download = client.get(
            "/api/files/demo.html",
            params={"sid": session.id, "inline": "true"},
        )
        assert download.status_code == 200
        assert download.headers["content-disposition"].startswith("attachment;")
        assert client.get(
            "/api/files/../secret.txt", params={"sid": session.id}
        ).status_code == 404

    frontend = (Path(__file__).parents[1] / "web" / "index.html").read_text(
        encoding="utf-8")
    assert 'iframe.removeAttribute("sandbox")' not in frontend
    assert "window.open(url); setTimeout(() => URL.revokeObjectURL" not in frontend
    assert 'data:text/html;charset=utf-8,' in frontend


def test_uploaded_attachments_are_structured_and_kept_out_of_display_text(
        isolated_server: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = isolated_server / "workspace"
    session = Session("abc123def456", workspace=str(workspace))
    server.SESSIONS[session.id] = session

    captured: dict = {}

    class FakeJob:
        def __init__(self) -> None:
            self.events: queue.Queue = queue.Queue()
            self.events.put(None)

        def claim_stream(self) -> bool:
            return True

        def release_stream(self) -> None:
            pass

    def fake_enqueue(_session, message, **kwargs):
        captured.update(message=message, **kwargs)
        return FakeJob()

    monkeypatch.setattr(server, "_enqueue_job", fake_enqueue)
    with local_client() as client:
        uploaded = client.post(
            "/api/upload",
            params={"sid": session.id},
            files={"files": ("screen.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        )
        assert uploaded.status_code == 200
        payload = uploaded.json()
        assert payload["saved"] == ["screen.png"]
        assert payload["attachments"] == [{
            "name": "screen.png", "size": 8, "mime": "image/png",
            "kind": "image", "previewable": True,
        }]

        response = client.post("/api/chat", json={
            "session_id": session.id,
            "message": "What is in this image?",
            "attachments": ["screen.png"],
        })
        assert response.status_code == 200

    assert captured["display_message"] == "What is in this image?"
    assert captured["message"].endswith(
        "[Attached files, saved in the workspace: screen.png]")
    assert captured["attachments"][0]["kind"] == "image"
    job = server.GenerationJob(
        session, captured["message"], display_message=captured["display_message"],
        attachments=captured["attachments"],
    )
    assert job.turn[0]["text"] == "What is in this image?"
    assert job.turn[0]["attachments"][0]["name"] == "screen.png"


def test_chat_rejects_attachment_paths_outside_workspace(isolated_server: Path):
    session = Session("fed654cba321", workspace=str(isolated_server / "workspace"))
    server.SESSIONS[session.id] = session
    with local_client() as client:
        response = client.post("/api/chat", json={
            "session_id": session.id,
            "message": "inspect this",
            "attachments": ["../secret.png"],
        })
    assert response.status_code == 422


def test_session_persistence_is_atomic_and_preserves_lazy_agent_state(
        isolated_server: Path):
    workspace = isolated_server / "workspace"
    session = Session("123456abcdef", workspace=str(workspace))
    session.display = [{"t": "user", "text": "hello"}]
    session._agent_state = {
        "messages": [{"role": "user", "content": "hello"}],
        "skills_loaded": ["coding"],
        "turn_no": 1,
        "turn_marks": [{"turn": 1, "msg_index": 0}],
        "checkpoints": [],
        "compactions": 3,
        "calibration_ratio": 1.7,
        "last_real_prompt": 4321,
    }
    session.save()

    path = server.SESSIONS_DIR / f"{session.id}.json"
    assert path.is_file()
    assert not list(server.SESSIONS_DIR.glob("*.tmp"))
    loaded = Session.load(path)
    assert loaded is not None
    assert loaded._agent is None
    assert loaded._agent_state is not None
    assert loaded._agent_state["compactions"] == 3
    assert loaded._agent_state["calibration_ratio"] == 1.7
    assert loaded._agent_state["last_real_prompt"] == 4321

    loaded.title = "renamed"
    loaded.save()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["messages"] == [{"role": "user", "content": "hello"}]
    assert data["title"] == "renamed"
    assert data["context_compactions"] == 3
    assert data["context_calibration_ratio"] == 1.7
    assert data["context_last_real_prompt"] == 4321


def test_session_load_caps_legacy_tool_error_snapshots(
        isolated_server: Path):
    huge_error = "Error: malformed snapshot " + "x" * 200_000
    path = server.SESSIONS_DIR / "123456abcdef.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "id": "123456abcdef",
        "display": [{"t": "tool", "name": "computer",
                     "args": "{}", "result": huge_error}],
        "messages": [{"role": "tool", "tool_call_id": "old",
                      "name": "computer", "content": huge_error}],
        "skills_loaded": [], "turn_no": 0, "turn_marks": [],
        "checkpoints": [],
    }), encoding="utf-8")
    loaded = Session.load(path)
    assert loaded is not None
    assert len(loaded.display[0]["result"]) < 4_100
    assert loaded._agent_state is not None
    assert len(loaded._agent_state["messages"][0]["content"]) < 4_100


@pytest.mark.parametrize("payload", [
    [],
    {"id": "../../escape", "display": [], "messages": []},
    {"id": "abcdef123456", "display": "bad", "messages": []},
    {"id": "abcdef123456", "display": [], "messages": "bad"},
    {"id": "abcdef123456", "display": [],
     "messages": [{"content": "missing role"}]},
    {"id": "abcdef123456", "display": [], "messages": [],
     "created": float("nan")},
    {"id": "abcdef123456", "display": [], "messages": [], "turn_no": 1,
     "checkpoints": [{"turn": 1, "path": "x", "existed": True,
                      "before": None}]},
])
def test_malformed_sessions_are_ignored(
        isolated_server: Path, payload: object):
    path = isolated_server / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert Session.load(path) is None


def test_read_file_is_bounded_and_recursive_glob_matches_root_files(
        tmp_path: Path):
    source = tmp_path / "root.py"
    source.write_text("\n".join(f"line {i}" for i in range(3000)),
                      encoding="utf-8")
    result = read_file("root.py", max_lines=100_000, base=tmp_path)
    assert "2000| line 1999" in result
    assert "2001|" not in result
    assert "more lines" in result
    assert "root.py" in search(glob="**/*.py", base=tmp_path)

    long_line = tmp_path / "minified.js"
    long_line.write_text("a" * 500_000 + "\nsecond", encoding="utf-8")
    bounded = read_file("minified.js", base=tmp_path)
    assert "[line truncated]" in bounded
    assert "2| second" in bounded
    assert len(bounded) < 10_000


def test_oversized_prompt_rolls_back_context_without_calling_model(
        tmp_path: Path):
    cfg = Config(context_window=4096, compact_threshold=2048,
                 output_reserve=2048)
    agent = Agent(cfg, workspace=tmp_path)
    try:
        result = agent.run_turn("x" * 50_000, stream=False)
        assert "does not fit" in result
        assert agent.ctx.messages == []
        assert agent.turn_no == 0
        assert agent.turn_marks == []
    finally:
        agent.llm.close()


def test_overflow_after_compaction_removes_only_the_current_turn(
        tmp_path: Path):
    cfg = Config(context_window=4096, compact_threshold=2048,
                 output_reserve=2048)
    agent = Agent(cfg, workspace=tmp_path)
    agent.llm.close()

    class SummaryOnlyLLM:
        def chat(self, *args, **kwargs):
            return LLMResponse(content="prior conversation summary")

    agent.llm = SummaryOnlyLLM()  # type: ignore[assignment]
    agent.ctx.messages = [
        {"role": "user" if i % 2 == 0 else "assistant",
         "content": f"old-{i}-" + "y" * 500}
        for i in range(12)
    ]
    agent.turn_no = 6
    agent.turn_marks = [
        {"turn": i + 1, "msg_index": i * 2} for i in range(6)
    ]
    huge = "x" * 50_000
    result = agent.run_turn(huge, stream=False)
    assert "does not fit" in result
    assert all(huge not in str(message.get("content"))
               for message in agent.ctx.messages)
    assert agent.turn_no == 6
    assert len(agent.turn_marks) == 6


def test_binary_file_checkpoint_reverts_exact_bytes(tmp_path: Path):
    original = b"\x00\xff\x10binary\x80"
    target = tmp_path / "asset.bin"
    target.write_bytes(original)
    agent = Agent(Config(), workspace=tmp_path)
    try:
        agent.turn_no = 1
        assert agent.record_file_snapshot("asset.bin") is True
        assert agent.record_file_snapshot("asset.bin") is True
        assert len(agent.checkpoints) == 1
        write_file("asset.bin", "replacement", base=tmp_path)
        assert target.read_bytes() != original
        agent.revert_to_turn(1)
        assert target.read_bytes() == original
        assert edit_file("asset.bin", "x", "y", base=tmp_path).startswith("Error")
    finally:
        agent.llm.close()


def test_uncheckpointable_file_write_reports_revert_warning(tmp_path: Path):
    target = tmp_path / "large.txt"
    target.write_text("x" * (Agent.SNAPSHOT_MAX + 1), encoding="utf-8")
    agent = Agent(Config(), workspace=tmp_path)
    try:
        agent.turn_no = 1
        result = agent.tools.execute(
            "write_file",
            json.dumps({"path": "large.txt", "content": "replacement"}),
            agent=agent,
        )
        assert "revert cannot restore it" in result
        assert agent.checkpoints == []
    finally:
        agent.llm.close()


def test_subtask_checkpoints_are_merged_into_parent_turn(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    parent = Agent(Config(), workspace=tmp_path)
    parent.turn_no = 4

    def fake_run_turn(self, *args, **kwargs):
        self.checkpoints = [{
            "turn": 1, "path": str(tmp_path / "made.txt"),
            "existed": False, "before": None,
        }]
        return "complete"

    monkeypatch.setattr(Agent, "run_turn", fake_run_turn)
    try:
        assert "complete" in parent.run_subtask("make a file")
        assert parent.checkpoints == [{
            "turn": 4, "path": str(tmp_path / "made.txt"),
            "existed": False, "before": None,
        }]
    finally:
        parent.llm.close()


def test_agent_reset_clears_all_conversation_and_revert_state(tmp_path: Path):
    agent = Agent(Config(), workspace=tmp_path)
    try:
        agent.ctx.messages = [{"role": "user", "content": "old"}]
        agent.turn_no = 3
        agent.turn_marks = [{"turn": 3, "msg_index": 0}]
        agent.checkpoints = [{
            "turn": 3, "path": str(tmp_path / "old.txt"),
            "existed": False, "before": None,
        }]
        agent._pending_nudge = 4
        agent.reset()
        assert agent.ctx.messages == []
        assert agent.turn_no == 0
        assert agent.turn_marks == []
        assert agent.checkpoints == []
        assert agent._pending_nudge == 0
    finally:
        agent.llm.close()


def test_stop_during_model_transport_error_is_reported_as_user_stop(
        tmp_path: Path):
    agent = Agent(Config(), workspace=tmp_path)

    class InterruptedLLM:
        def chat(self, *args, **kwargs):
            agent._stop.set()
            raise RuntimeError("socket closed")

        def close(self):
            pass

        def cancel_current(self):
            pass

    agent.llm.close()
    agent.llm = InterruptedLLM()  # type: ignore[assignment]
    result = agent.run_turn("wait", stream=True)
    assert result == "(stopped by user)"
    assert "socket closed" not in str(agent.ctx.messages)


def test_chat_mode_exposes_no_tools_and_uses_chat_prompt(tmp_path: Path):
    agent = Agent(Config(), workspace=tmp_path)
    captured = {}

    class ChatLLM:
        def chat(self, **kwargs):
            captured.update(kwargs)
            return LLMResponse(content="plain answer", finish_reason="stop")

        def close(self):
            pass

    agent.llm.close()
    agent.llm = ChatLLM()  # type: ignore[assignment]
    agent.tool_mode = False
    assert agent.run_turn("hello", stream=False) == "plain answer"
    assert captured["tools"] == []
    assert "You have no tools in this mode" in captured["messages"][0]["content"]


def test_agent_honors_configured_max_output_tokens(tmp_path: Path):
    agent = Agent(Config(context_window=65_536, compact_threshold=49_152,
                         max_output_tokens=2048), workspace=tmp_path)
    captured = {}

    class CapturingLLM:
        def chat(self, **kwargs):
            captured.update(kwargs)
            return LLMResponse(content="bounded", finish_reason="stop")

        def close(self):
            pass

    agent.llm.close()
    agent.llm = CapturingLLM()  # type: ignore[assignment]
    assert agent.run_turn("hello", stream=False) == "bounded"
    assert captured["max_tokens"] == 2048


def test_model_reconfigure_resets_vision_and_token_calibration(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    agent = Agent(Config(), workspace=tmp_path)
    calls = []
    monkeypatch.setattr(
        agent.llm, "reconfigure",
        lambda base_url, model, api_key: calls.append(
            (base_url, model, api_key)))
    agent._vision = True
    agent.ctx.calibrator.ratio = 2.1
    agent.ctx.calibrator.last_real_prompt = 1234
    try:
        agent.reconfigure_model("http://localhost:9999/v1", "new", "key")
        assert calls == [("http://localhost:9999/v1", "new", "key")]
        assert agent._vision is None
        assert agent.ctx.calibrator.ratio == 1.0
        assert agent.ctx.calibrator.last_real_prompt == 0
    finally:
        agent.llm.close()


def test_skill_router_preloads_relevant_instructions_each_turn(tmp_path: Path):
    manager = SkillsManager()
    assert manager.recommend(
        "Build a 3D model in HTML and animate it") == [
            "threejs-essentials", "animation-principles", "ui-ux-design"]
    assert manager.recommend("audit and fix every bug in this repository") == [
        "debugging-method", "software-design-taste", "coding"]
    assert manager.recommend(
        "open my email and summarize the top 10 emails using Gmail from Chrome") == [
            "computer", "clear-writing"]
    assert manager.recommend("just say hello") == []

    agent = Agent(Config(), workspace=tmp_path)
    prompts = []

    class SkillAwareLLM:
        def chat(self, **kwargs):
            prompts.append(kwargs["messages"][0]["content"])
            return LLMResponse(content="done", finish_reason="stop")

        def close(self):
            pass

    agent.llm.close()
    agent.llm = SkillAwareLLM()  # type: ignore[assignment]
    events = []
    assert agent.run_turn(
        "audit this repository", stream=False,
        on_event=lambda kind, data: events.append((kind, data))) == "done"
    assert [data["name"] for kind, data in events
            if kind == "skill_loaded"] == [
                "debugging-method", "software-design-taste", "coding"]
    assert "[active skill: debugging-method]" in prompts[0]
    assert "[active skill: coding]" in prompts[0]

    assert agent.run_turn("hello", stream=False) == "done"
    assert "[active skill:" not in prompts[1]
    assert agent.skills.loaded == set()


def test_chat_mode_never_preloads_or_exposes_skills(tmp_path: Path):
    agent = Agent(Config(), workspace=tmp_path)
    agent.tool_mode = False
    captured = {}

    class ChatLLM:
        def chat(self, **kwargs):
            captured.update(kwargs)
            return LLMResponse(content="chat", finish_reason="stop")

        def close(self):
            pass

    agent.llm.close()
    agent.llm = ChatLLM()  # type: ignore[assignment]
    events = []
    assert agent.run_turn(
        "debug this HTML app", stream=False,
        on_event=lambda kind, data: events.append((kind, data))) == "chat"
    assert not [event for event in events if event[0] == "skill_loaded"]
    assert captured["tools"] == []
    assert agent.skills.loaded == set()


def test_existing_agent_discovers_skill_added_after_it_was_created(
        tmp_path: Path):
    skills_dir = tmp_path / "skills"
    manager = SkillsManager((skills_dir,))
    agent = Agent(Config(), workspace=tmp_path)
    agent.skills = manager
    agent.tools = build_registry(manager)
    agent.llm.close()
    prompts = []

    class SkillLLM:
        def chat(self, **kwargs):
            prompts.append(kwargs["messages"][0]["content"])
            return LLMResponse(content="ok", finish_reason="stop")

        def close(self):
            pass

    agent.llm = SkillLLM()  # type: ignore[assignment]
    path = skills_dir / "late-skill" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\nname: late-skill\ndescription: Added later\n"
        "category: other\nhint: late instructions\n---\nFollow late instructions.\n",
        encoding="utf-8")
    assert agent.run_turn("use the late skill", stream=False) == "ok"
    assert "[active skill: late-skill]" in prompts[0]


def test_stop_requested_before_turn_entry_is_not_lost(tmp_path: Path):
    agent = Agent(Config(), workspace=tmp_path)

    class NeverCalledLLM:
        def chat(self, **kwargs):
            raise AssertionError("cancelled turn must not call the model")

        def close(self):
            pass

        def cancel_current(self):
            pass

    agent.llm.close()
    agent.llm = NeverCalledLLM()  # type: ignore[assignment]
    agent.request_stop()
    assert agent.run_turn("do work", stream=False) == "(stopped by user)"
    assert not agent._stop.is_set()


def test_failed_edit_does_not_leave_phantom_revert_checkpoint(tmp_path: Path):
    target = tmp_path / "note.txt"
    target.write_text("original", encoding="utf-8")
    agent = Agent(Config(), workspace=tmp_path)
    try:
        result = agent.tools.execute("edit_file", json.dumps({
            "path": "note.txt", "old_text": "missing", "new_text": "new",
        }), agent=agent)
        assert result.startswith("Error")
        assert agent.checkpoints == []
        assert target.read_text(encoding="utf-8") == "original"
    finally:
        agent.llm.close()


def test_context_detection_uses_the_selected_model_and_clears_stale_data(
        isolated_server: Path, monkeypatch: pytest.MonkeyPatch):
    class Response:
        def __init__(self, data):
            self.data = data

        def json(self):
            return {"data": self.data}

        def raise_for_status(self):
            return None

    monkeypatch.setattr(server.CFG, "model", "wanted")
    monkeypatch.setattr(server.CFG, "context_window", 16_000)
    monkeypatch.setattr(server.CFG, "compact_threshold", 8_000)
    monkeypatch.setattr(server.CFG, "compact_target", 4_000)
    monkeypatch.setattr(server, "REQUESTED_CONTEXT_WINDOW", 16_000)
    monkeypatch.setattr(
        server.httpx, "get",
        lambda *a, **k: Response([
            {"id": "other", "meta": {"n_ctx": 2048}},
            {"id": "wanted", "meta": {"n_ctx": 8192}},
        ]),
    )
    server._sync_window()
    assert server.DETECTED["n_ctx"] == 8192
    assert server.CFG.context_window == 8192

    server._apply_window(16_000)
    monkeypatch.setattr(
        server.httpx, "get",
        lambda *a, **k: Response([
            {"id": "other", "meta": {"n_ctx": 2048}},
            {"id": "another", "meta": {"n_ctx": 4096}},
        ]),
    )
    server._sync_window()
    assert server.DETECTED["n_ctx"] is None
    assert server.CFG.context_window == 16_000


def test_settings_save_is_durable_before_live_mutation_and_background_work(
        isolated_server: Path, monkeypatch: pytest.MonkeyPatch):
    saved = []
    scheduled = []
    monkeypatch.setattr(server, "save_user_settings",
                        lambda values: saved.append(copy.deepcopy(values)))
    monkeypatch.setattr(server, "_schedule_settings_refresh",
                        lambda mcp=None, **kwargs:
                        scheduled.append((copy.deepcopy(mcp), kwargs)))
    previous_model = server.CFG.model
    response = server.set_settings(server.SettingsBody(
        temperature=0.25, model="new-model", context_window=24_000,
        max_output_tokens=3000,
    ))
    assert saved and saved[0]["model"] == "new-model"
    assert saved[0]["context_window"] == 24_000
    assert server.CFG.model == "new-model"
    assert response["context_window"] == 24_000
    assert response["effective_context_window"] == 24_000
    assert scheduled == [(None, {"force_mcp": False})]

    def fail_save(_values):
        raise OSError("disk full")

    monkeypatch.setattr(server, "save_user_settings", fail_save)
    with pytest.raises(HTTPException) as failure:
        server.set_settings(server.SettingsBody(model="must-not-apply"))
    assert failure.value.status_code == 500
    assert server.CFG.model == "new-model"
    assert server.CFG.model != previous_model
    assert len(scheduled) == 1


def test_slow_model_probe_is_backgrounded_and_revision_safe(
        isolated_server: Path, monkeypatch: pytest.MonkeyPatch):
    started = threading.Event()
    release = threading.Event()

    def slow_models(*_args, **_kwargs):
        started.set()
        assert release.wait(2)
        return [{"id": server.CFG.model, "n_ctx": 8192}]

    monkeypatch.setattr(server, "_fetch_models", slow_models)
    began = time.monotonic()
    server._schedule_settings_refresh()
    assert time.monotonic() - began < 0.2
    assert started.wait(1)
    with server.SETTINGS_REFRESH_LOCK:
        assert server.SETTINGS_REFRESH["model"] == {
            "state": "checking", "error": None}
    release.set()
    deadline = time.time() + 2
    while time.time() < deadline:
        with server.SETTINGS_REFRESH_LOCK:
            if server.SETTINGS_REFRESH["model"] == {
                    "state": "ready", "error": None}:
                break
        time.sleep(0.01)
    with server.SETTINGS_REFRESH_LOCK:
        assert server.SETTINGS_REFRESH["model"] == {
            "state": "ready", "error": None}
    assert server.DETECTED["n_ctx"] == 8192


def test_model_listing_uses_auth_and_normalizes_context_metadata(
        isolated_server: Path, monkeypatch: pytest.MonkeyPatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [
                {"id": "small", "owned_by": "local", "meta": {"n_ctx": "8192"}},
                {"id": 123},
            ]}

    def fake_get(url, **kwargs):
        assert url.endswith("/models")
        assert kwargs["headers"]["Authorization"] == "Bearer private-key"
        return Response()

    monkeypatch.setattr(server.CFG, "api_key", "private-key")
    monkeypatch.setattr(server.httpx, "get", fake_get)
    with local_client() as client:
        response = client.get("/api/models")
    assert response.status_code == 200
    assert response.json()["models"] == [{
        "id": "small", "owned_by": "local", "n_ctx": 8192,
    }]


def test_agent_applies_steering_after_active_model_response(tmp_path: Path):
    cfg = Config(context_window=8192, compact_threshold=4096,
                 compact_target=2048, max_iterations=4)
    agent = Agent(cfg, workspace=tmp_path)
    agent.tool_mode = False
    agent.llm.close()
    first_call = threading.Event()
    release_first = threading.Event()
    calls: list[list[dict]] = []

    class SteeringLLM:
        def chat(self, messages, **kwargs):
            calls.append(copy.deepcopy(messages))
            if len(calls) == 1:
                first_call.set()
                assert release_first.wait(2)
                return LLMResponse(content="initial answer", finish_reason="stop")
            return LLMResponse(content="revised answer", finish_reason="stop")

        def cancel_current(self):
            pass

    agent.llm = SteeringLLM()  # type: ignore[assignment]
    events: list[tuple[str, object]] = []
    result: list[str] = []
    thread = threading.Thread(
        target=lambda: result.append(agent.run_turn(
            "start", on_event=lambda kind, data: events.append((kind, data)))))
    thread.start()
    assert first_call.wait(1)
    assert agent.submit_steer("focus on the second option")
    release_first.set()
    thread.join(2)

    assert result == ["revised answer"]
    assert len(calls) == 2
    assert any(message.get("role") == "user"
               and "focus on the second option" in str(message.get("content"))
               for message in calls[1])
    assert ("steer_applied", "focus on the second option") in events


def test_pending_followups_persist_and_run_in_order(
        isolated_server: Path, monkeypatch: pytest.MonkeyPatch):
    first_started = threading.Event()
    release_first = threading.Event()
    calls: list[str] = []

    class SequentialAgent:
        tool_mode = True

        def run_turn(self, message, on_event=None):
            calls.append(message)
            if len(calls) == 1:
                first_started.set()
                assert release_first.wait(3)
            return f"done {len(calls)}"

        def context_status(self):
            return {"estimated_tokens": 1, "window": 4096,
                    "compact_threshold": 2048, "compactions": 0,
                    "last_prompt_tokens": 0, "skills_loaded": []}

        def request_stop(self):
            release_first.set()

    session = Session("a1b2c3d4e5f6", workspace=str(isolated_server / "workspace"))
    session._agent = SequentialAgent()  # type: ignore[assignment]
    server.SESSIONS[session.id] = session
    monkeypatch.setattr(Session, "save", lambda self, **kwargs: None)

    server.chat(ChatBody(session_id=session.id, message="first"))
    assert first_started.wait(1)
    queued = server.add_followup(
        session.id, server.FollowupBody(message="second", action="queue"))
    assert [item["text"] for item in queued["pending_messages"]] == ["second"]
    release_first.set()
    deadline = time.time() + 3
    while len(calls) < 2 and time.time() < deadline:
        time.sleep(0.01)
    assert calls == ["first", "second"]
    deadline = time.time() + 3
    while (session.running or session.queued) and time.time() < deadline:
        time.sleep(0.01)
    assert [item["text"] for item in session.display
            if item.get("t") == "user"] == ["first", "second"]


def test_live_steer_and_pending_message_management(
        isolated_server: Path, monkeypatch: pytest.MonkeyPatch):
    started = threading.Event()
    release = threading.Event()
    steers: list[str] = []

    class SteerableAgent:
        tool_mode = True

        def run_turn(self, message, on_event=None):
            started.set()
            assert release.wait(3)
            return "done"

        def submit_steer(self, text):
            steers.append(text)
            return True

        def context_status(self):
            return {"estimated_tokens": 1, "window": 4096,
                    "compact_threshold": 2048, "compactions": 0,
                    "last_prompt_tokens": 0, "skills_loaded": []}

        def request_stop(self):
            release.set()

    session = Session("0a1b2c3d4e5f", workspace=str(isolated_server / "workspace"))
    session._agent = SteerableAgent()  # type: ignore[assignment]
    server.SESSIONS[session.id] = session
    monkeypatch.setattr(Session, "save", lambda self, **kwargs: None)
    server.chat(ChatBody(session_id=session.id, message="work"))
    assert started.wait(1)

    server.add_followup(
        session.id, server.FollowupBody(message="direct steer", action="steer"))
    queued = server.add_followup(
        session.id, server.FollowupBody(message="promote me", action="queue"))
    pending_id = queued["pending_messages"][0]["id"]
    promoted = server.promote_followup_to_steer(session.id, pending_id)
    assert promoted["pending_messages"] == []
    removable = server.add_followup(
        session.id, server.FollowupBody(message="remove me", action="queue"))
    remove_id = removable["pending_messages"][0]["id"]
    assert server.delete_followup(session.id, remove_id)["pending_messages"] == []
    assert steers == ["direct steer", "promote me"]
    assert [item["text"] for item in session._job.turn
            if item.get("t") == "steer"] == steers
    release.set()


def test_pending_followup_round_trips_through_session_file(isolated_server: Path):
    session = Session("123abc456def", workspace=str(isolated_server / "workspace"))
    session.pending_messages = [{
        "id": "abcdef123456", "text": "run this next", "created": time.time(),
    }]
    session.save()
    loaded = Session.load(server.SESSIONS_DIR / f"{session.id}.json")
    assert loaded is not None
    assert loaded.pending_messages[0]["text"] == "run this next"


def test_oversized_session_file_is_ignored(
        isolated_server: Path, monkeypatch: pytest.MonkeyPatch):
    path = server.SESSIONS_DIR / "123abc456def.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"id":"123abc456def"}', encoding="utf-8")
    monkeypatch.setattr(server, "MAX_SESSION_FILE_BYTES", 2)
    assert Session.load(path) is None


def test_running_session_save_keeps_last_protocol_safe_agent_state(
        isolated_server: Path):
    session = Session("789abc456def", workspace=str(isolated_server / "workspace"))
    agent = session.agent
    agent.ctx.messages = [{"role": "user", "content": "completed turn"},
                          {"role": "assistant", "content": "done"}]
    agent.turn_no = 1
    agent.turn_marks = [{"turn": 1, "msg_index": 0}]
    session.save()

    # Simulate a live model response whose tool call has not received its
    # required tool result yet. A follow-up save must not persist this prefix.
    session.running = True
    agent.ctx.messages.append({
        "role": "assistant", "content": "", "tool_calls": [{
            "id": "call_live", "type": "function",
            "function": {"name": "write_file", "arguments": "{}"},
        }],
    })
    session.pending_messages = [{
        "id": "abcdef123456", "text": "next", "created": time.time(),
    }]
    session.save()
    persisted = json.loads(
        (server.SESSIONS_DIR / f"{session.id}.json").read_text(encoding="utf-8"))
    assert persisted["pending_messages"][0]["text"] == "next"
    assert persisted["messages"][-1] == {
        "role": "assistant", "content": "done"}

    session.save(include_live_agent=True)
    persisted_live = json.loads(
        (server.SESSIONS_DIR / f"{session.id}.json").read_text(encoding="utf-8"))
    assert persisted_live["messages"][-1]["tool_calls"][0]["id"] == "call_live"
    agent.llm.close()


def test_visual_check_captures_multiple_viewports_and_interactive_state(
        tmp_path: Path):
    if not _find_browser():
        pytest.skip("no Chromium-family browser installed")
    page = tmp_path / "visual.html"
    page.write_text("""<!doctype html><html><style>
      body{margin:0}.wide{width:1800px}.modal{display:none}
      .modal.open{display:block}</style><body>
      <button id="open" onclick="document.querySelector('.modal').classList.add('open')">Open</button>
      <div class="wide">wide content</div><img src="missing.png">
      <div class="modal">Modal content</div></body></html>""", encoding="utf-8")
    result = visual_check(
        page, tmp_path, viewports="desktop,mobile", click_selector="#open",
        state_label="modal-open", wait_ms=10)
    assert result.startswith(VISUAL_MARKER)
    payload = json.loads(result[len(VISUAL_MARKER):])
    assert [shot["label"] for shot in payload["screenshots"]] == [
        "desktop", "mobile"]
    assert all(Path(shot["path"]).is_file() for shot in payload["screenshots"])
    assert "HORIZONTAL OVERFLOW" in payload["report"]
    assert "BROKEN IMAGES" in payload["report"]
    assert "Visual screenshot [mobile]" in payload["report"]


def test_agent_resolves_visual_qa_marker_into_model_images(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from PIL import Image
    shot = tmp_path / "shot.png"
    Image.new("RGB", (320, 200), "red").save(shot)
    marker = VISUAL_MARKER + json.dumps({
        "report": f"Visual screenshot [desktop]: {shot}",
        "screenshots": [{"path": str(shot), "label": "desktop"}],
    })
    agent = Agent(Config(), workspace=tmp_path)
    monkeypatch.setattr(agent, "vision_supported", lambda: True)
    try:
        report, images = agent._resolve_image_marker(marker)
        assert "attached" in report
        assert len(images) == 1
        assert images[0]["type"] == "image_url"
        assert images[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    finally:
        agent.llm.close()


def test_visual_check_is_a_core_tool_and_mandatory_in_prompt(tmp_path: Path):
    agent = Agent(Config(), workspace=tmp_path)
    try:
        names = {schema["function"]["name"] for schema in agent.tools.schemas()}
        assert "visual_check" in names
        prompt = agent.system_prompt()
        assert "visual verification is mandatory" in prompt
        assert "clean console" in prompt
    finally:
        agent.llm.close()


def test_html_write_automatically_invokes_visual_qa(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    marker = VISUAL_MARKER + json.dumps({"report": "checked", "screenshots": []})

    def fake_check(path, visual_root=None):
        assert path == (tmp_path / "page.html").resolve()
        assert visual_root == tmp_path
        return marker

    import harness.verify as verify
    monkeypatch.setattr(verify, "check_written_file", fake_check)
    agent = Agent(Config(), workspace=tmp_path)
    try:
        result = agent.tools.execute("write_file", json.dumps({
            "path": "page.html", "content": "<h1>hello</h1>",
        }), agent=agent)
        assert result.startswith(VISUAL_MARKER)
        payload = json.loads(result[len(VISUAL_MARKER):])
        assert "Wrote" in payload["report"]
        assert "checked" in payload["report"]
    finally:
        agent.llm.close()


def test_visual_evidence_follows_all_parallel_tool_results(tmp_path: Path):
    from PIL import Image
    Image.new("RGB", (100, 60), "blue").save(tmp_path / "view.png")
    agent = Agent(Config(max_iterations=3), workspace=tmp_path)
    agent.llm.close()
    agent._vision = True

    class ToolCallingLLM:
        calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(tool_calls=[
                    {"id": "image", "type": "function", "function": {
                        "name": "read_file", "arguments": '{"path":"view.png"}'}},
                    {"id": "list", "type": "function", "function": {
                        "name": "list_dir", "arguments": '{}'}},
                ], finish_reason="tool_calls")
            return LLMResponse(content="visually checked", finish_reason="stop")

        def cancel_current(self):
            pass

    agent.llm = ToolCallingLLM()  # type: ignore[assignment]
    assert agent.run_turn("inspect it", stream=False) == "visually checked"
    roles = [message["role"] for message in agent.ctx.messages]
    assistant_index = roles.index("assistant")
    assert roles[assistant_index:assistant_index + 4] == [
        "assistant", "tool", "tool", "user"]
    visual_message = agent.ctx.messages[assistant_index + 3]
    assert isinstance(visual_message["content"], list)
    assert visual_message["content"][1]["type"] == "image_url"


def test_visual_qa_tool_result_is_attached_to_the_next_model_call(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from PIL import Image
    shot = tmp_path / "qa.png"
    Image.new("RGB", (120, 80), "green").save(shot)
    marker = VISUAL_MARKER + json.dumps({
        "report": f"Visual screenshot [desktop]: {shot}",
        "screenshots": [{"path": str(shot), "label": "desktop"}],
    })
    agent = Agent(Config(max_iterations=3), workspace=tmp_path)
    agent.llm.close()
    agent._vision = True
    calls = []

    class VisualToolLLM:
        def chat(self, messages, **kwargs):
            calls.append(copy.deepcopy(messages))
            if len(calls) == 1:
                return LLMResponse(tool_calls=[{
                    "id": "visual", "type": "function", "function": {
                        "name": "visual_check",
                        "arguments": '{"target":"page.html"}',
                    },
                }], finish_reason="tool_calls")
            return LLMResponse(content="inspected", finish_reason="stop")

        def cancel_current(self):
            pass

    monkeypatch.setattr(agent.tools, "execute", lambda *args, **kwargs: marker)
    agent.llm = VisualToolLLM()  # type: ignore[assignment]
    assert agent.run_turn("inspect the UI", stream=False) == "inspected"
    visual = calls[1][-1]
    assert visual["role"] == "user"
    assert visual["content"][1]["type"] == "image_url"


def test_second_generation_and_delete_are_rejected_while_running(
        isolated_server: Path, monkeypatch: pytest.MonkeyPatch):
    started = threading.Event()
    finish = threading.Event()

    class BlockingAgent:
        def run_turn(self, message, on_event=None):
            started.set()
            assert finish.wait(2)
            return "done"

        def context_status(self):
            return {"estimated_tokens": 1, "window": 4096,
                    "compact_threshold": 2048, "compactions": 0,
                    "last_prompt_tokens": 0, "skills_loaded": []}

    session = Session("fedcba654321", workspace=str(isolated_server / "workspace"))
    session._agent = BlockingAgent()  # type: ignore[assignment]
    server.SESSIONS[session.id] = session
    monkeypatch.setattr(Session, "save", lambda self, **kwargs: None)

    response = server.chat(ChatBody(session_id=session.id, message="first"))
    assert response is not None
    assert started.wait(1)
    with pytest.raises(HTTPException) as second:
        server.chat(ChatBody(session_id=session.id, message="second"))
    assert second.value.status_code == 409
    with pytest.raises(HTTPException) as deletion:
        server.delete_session(session.id)
    assert deletion.value.status_code == 409
    with pytest.raises(HTTPException) as settings:
        server.set_settings(server.SettingsBody(temperature=0.2))
    assert settings.value.status_code == 409
    with pytest.raises(HTTPException) as rename:
        server.rename_session(session.id, server.RenameBody(title="busy"))
    assert rename.value.status_code == 409
    with pytest.raises(HTTPException) as files:
        server.make_folder(server.FileOpBody(
            sid=session.id, path="during-generation"))
    assert files.value.status_code == 409

    finish.set()
    deadline = time.time() + 2
    while session.running and time.time() < deadline:
        time.sleep(0.01)
    assert not session.running
    assert not server.MODEL_LOCK.locked()


def test_different_sessions_queue_and_queued_job_can_be_cancelled(
        isolated_server: Path, monkeypatch: pytest.MonkeyPatch):
    first_started = threading.Event()
    release_first = threading.Event()

    class FirstAgent:
        tool_mode = True

        def run_turn(self, message, on_event=None):
            first_started.set()
            assert release_first.wait(3)
            return "first done"

        def context_status(self):
            return {"estimated_tokens": 1, "window": 4096,
                    "compactions": 0, "last_prompt_tokens": 0,
                    "skills_loaded": []}

        def request_stop(self):
            release_first.set()

    class SecondAgent:
        tool_mode = True

        def run_turn(self, message, on_event=None):
            raise AssertionError("cancelled queued job must never execute")

        def context_status(self):
            return {"estimated_tokens": 0, "window": 4096,
                    "compactions": 0, "last_prompt_tokens": 0,
                    "skills_loaded": []}

    first = Session("111111aaaaaa", workspace=str(isolated_server / "one"))
    second = Session("222222bbbbbb", workspace=str(isolated_server / "two"))
    first._agent = FirstAgent()  # type: ignore[assignment]
    second._agent = SecondAgent()  # type: ignore[assignment]
    server.SESSIONS.update({first.id: first, second.id: second})
    monkeypatch.setattr(Session, "save", lambda self, **kwargs: None)

    server.chat(ChatBody(session_id=first.id, message="first"))
    assert first_started.wait(2)
    server.chat(ChatBody(session_id=second.id, message="second"))
    deadline = time.time() + 2
    while not second.queued and time.time() < deadline:
        time.sleep(0.01)
    assert second.queued and not second.running
    persisted_jobs = json.loads(server.JOBS_FILE.read_text(encoding="utf-8"))
    assert {job["state"] for job in persisted_jobs} == {"running", "queued"}
    jobs = server.list_jobs()
    assert [job["session_id"] for job in jobs] == [first.id, second.id]
    assert jobs[1]["position"] == 1

    server.stop_session(second.id)
    assert not second.queued
    assert any(item.get("text") == "Cancelled while queued."
               for item in second.display)
    release_first.set()
    deadline = time.time() + 3
    while server._jobs_active() and time.time() < deadline:
        time.sleep(0.01)
    assert not server._jobs_active()
    assert json.loads(server.JOBS_FILE.read_text(encoding="utf-8")) == []


def test_running_job_remembers_stop_requested_before_agent_starts(
        isolated_server: Path, monkeypatch: pytest.MonkeyPatch):
    stopped = threading.Event()

    class StartupAgent:
        tool_mode = True

        def request_stop(self):
            stopped.set()

        def run_turn(self, message, on_event=None):
            assert stopped.is_set()
            return "(stopped by user)"

        def context_status(self):
            return {"estimated_tokens": 0, "window": 4096,
                    "compact_threshold": 2048, "compactions": 0,
                    "last_prompt_tokens": 0, "skills_loaded": []}

    session = Session("aabbcc112233", workspace=str(isolated_server / "workspace"))
    job = server.GenerationJob(session, "work")
    job.state = "running"
    session.running = True
    session._job = job
    job.cancel()  # no session agent exists at this point
    assert not stopped.is_set()

    session._agent = StartupAgent()  # type: ignore[assignment]
    monkeypatch.setattr(Session, "save", lambda self, **kwargs: None)
    with server.JOBS_LOCK:
        server.ACTIVE_JOBS[job.id] = job
        server.JOB_ORDER.append(job.id)
    job.run()

    assert stopped.is_set()
    assert job.state == "cancelled"
    assert any(item.get("t") == "text"
               and item.get("text") == "(stopped by user)"
               for item in session.display)


def test_job_is_not_accepted_when_durable_queue_write_fails(
        isolated_server: Path, monkeypatch: pytest.MonkeyPatch):
    session = Session("ddeeff112233", workspace=str(isolated_server / "workspace"))
    server.SESSIONS[session.id] = session
    original_title, original_updated = session.title, session.updated

    def fail_write(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(server, "atomic_write_text", fail_write)
    with pytest.raises(HTTPException) as failure:
        server._enqueue_job(session, "work")
    assert failure.value.status_code == 500
    assert not session.running and not session.queued and session._job is None
    assert session.title == original_title
    assert session.updated == original_updated
    assert not server._jobs_active()


def test_crash_recovery_does_not_replay_a_possibly_destructive_running_job(
        isolated_server: Path, monkeypatch: pytest.MonkeyPatch):
    session = Session("333333cccccc", workspace=str(isolated_server / "workspace"))
    server.SESSIONS[session.id] = session
    saved = []
    monkeypatch.setattr(
        Session, "save", lambda self, **kwargs: saved.append(True))
    server.JOBS_FILE.write_text(json.dumps([{
        "id": "aabbccddeeff0011", "session_id": session.id,
        "message": "change important files", "created": time.time(),
        "state": "running",
    }]), encoding="utf-8")

    server._recover_jobs()
    assert session.display[0] == {
        "t": "user", "text": "change important files"}
    assert "not automatically replayed" in session.display[1]["text"]
    assert saved
    assert json.loads(server.JOBS_FILE.read_text(encoding="utf-8")) == []


def test_session_settings_memory_and_workspace_api_lifecycle(
        isolated_server: Path, monkeypatch: pytest.MonkeyPatch):
    default_workspace = isolated_server / "default-workspace"
    settings_path = isolated_server / "user_settings.json"
    memory_path = isolated_server / "memory.md"
    monkeypatch.setattr(config, "USER_SETTINGS", settings_path)
    monkeypatch.setattr(memory, "MEMORY_FILE", memory_path)
    monkeypatch.setattr(server, "_sync_window", lambda: None)

    with local_client() as client:
        saved = client.post("/api/settings", json={
            "temperature": 0.7,
            "workspace": str(default_workspace),
            "base_url": "http://localhost:9999/v1/",
            "model": "test-model",
            "api_key": "secret",
            "context_window": 8192,
            "max_output_tokens": 3072,
        })
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["temperature"] == 0.7
        assert body["base_url"] == "http://localhost:9999/v1"
        assert body["context_window"] == 8192
        assert body["max_output_tokens"] == 3072
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        assert persisted["model"] == "test-model"
        assert persisted["max_output_tokens"] == 3072

        created = client.post("/api/sessions")
        assert created.status_code == 200
        sid = created.json()["id"]
        assert Path(created.json()["workspace"]) == default_workspace

        renamed = client.patch(
            f"/api/sessions/{sid}", json={"title": "Renamed", "pinned": True})
        assert renamed.status_code == 200
        assert renamed.json()["title"] == "Renamed"
        assert renamed.json()["pinned"] is True
        assert client.get(f"/api/sessions/{sid}").status_code == 200
        assert client.get("/api/sessions").json()[0]["id"] == sid

        session = server.SESSIONS[sid]
        session.display = [{"t": "user", "text": "unique needle"}]
        search_result = client.get("/api/search", params={"q": "needle"})
        assert search_result.status_code == 200
        assert search_result.json()[0]["id"] == sid

        memory_path.write_text("- durable fact\n", encoding="utf-8")
        memory_result = client.get("/api/memory")
        assert memory_result.status_code == 200
        assert "durable fact" in memory_result.json()["content"]

        chosen = isolated_server / "chosen-workspace"
        monkeypatch.setattr(server, "_native_folder_dialog", lambda start: str(chosen))
        browsed = client.post("/api/workspace/browse", json={"sid": sid})
        assert browsed.status_code == 200
        assert Path(browsed.json()["workspace"]) == chosen.resolve()

        deleted = client.delete(f"/api/sessions/{sid}")
        assert deleted.status_code == 200
        assert sid not in server.SESSIONS
        assert not (server.SESSIONS_DIR / f"{sid}.json").exists()


def test_invalid_settings_do_not_partially_mutate_live_config(
        isolated_server: Path):
    before = (server.CFG.temperature, server.CFG.base_url, server.CFG.model)
    with local_client() as client:
        response = client.post("/api/settings", json={
            "temperature": 1.7,
            "base_url": "file:///etc/passwd",
            "model": "should-not-apply",
        })
    assert response.status_code == 400
    assert (server.CFG.temperature, server.CFG.base_url, server.CFG.model) == before


def test_workspace_file_api_full_lifecycle(
        isolated_server: Path):
    workspace = isolated_server / "workspace"
    workspace.mkdir()
    session = Session("a1b2c3d4e5f6", workspace=str(workspace))
    server.SESSIONS[session.id] = session

    with local_client() as client:
        made = client.post("/api/files/mkdir", json={
            "sid": session.id, "path": "nested"})
        assert made.status_code == 200

        first_upload = client.post(
            "/api/upload", params={"sid": session.id},
            files=[("files", ("note.txt", b"hello", "text/plain"))],
        )
        second_upload = client.post(
            "/api/upload", params={"sid": session.id},
            files=[("files", ("note.txt", b"again", "text/plain"))],
        )
        assert first_upload.json()["saved"] == ["note.txt"]
        assert second_upload.json()["saved"] == ["note(1).txt"]

        files = client.get("/api/files", params={"sid": session.id})
        assert {item["name"] for item in files.json()} == {"note.txt", "note(1).txt"}
        tree = client.get("/api/tree", params={"sid": session.id})
        assert tree.status_code == 200
        assert any(item["name"] == "nested" and item["dir"]
                   for item in tree.json()["tree"])

        renamed = client.post("/api/files/rename", json={
            "sid": session.id, "path": "note.txt", "new_name": "renamed.txt"})
        assert renamed.status_code == 200
        download = client.get(
            "/api/files/renamed.txt", params={"sid": session.id})
        assert download.status_code == 200
        assert download.content == b"hello"

        preview = client.get(
            "/api/preview/renamed.txt", params={"sid": session.id})
        assert preview.status_code == 200
        assert "hello" in preview.text
        assert preview.headers["content-security-policy"] == "sandbox"

        huge = workspace / "huge.html"
        with huge.open("wb") as f:
            f.seek(server.MAX_RENDER_BYTES)
            f.write(b"x")
        too_large = client.get(
            "/api/preview/huge.html", params={"sid": session.id})
        assert too_large.status_code == 413

        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", b"x" * (11 * 1024 * 1024))
        (workspace / "bomb.docx").write_bytes(archive_bytes.getvalue())
        unsafe_archive = client.get(
            "/api/preview/bomb.docx", params={"sid": session.id})
        assert unsafe_archive.status_code == 413
        assert "compression ratio" in unsafe_archive.json()["detail"]

        assert client.delete(
            "/api/files/renamed.txt", params={"sid": session.id}).status_code == 200
        assert client.delete(
            "/api/files/nested", params={"sid": session.id}).status_code == 200
        assert not (workspace / "renamed.txt").exists()
        assert not (workspace / "nested").exists()


def test_upload_batch_is_atomic_and_resource_bounded(
        isolated_server: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = isolated_server / "workspace"
    workspace.mkdir()
    session = Session("abc123abc123", workspace=str(workspace))
    server.SESSIONS[session.id] = session
    monkeypatch.setattr(server, "MAX_UPLOAD", 4)
    monkeypatch.setattr(server, "MAX_UPLOAD_TOTAL", 6)

    with local_client() as client:
        rejected = client.post(
            "/api/upload", params={"sid": session.id}, files=[
                ("files", ("first.txt", b"ok", "text/plain")),
                ("files", ("second.txt", b"12345", "text/plain")),
            ])
        assert rejected.status_code == 413
        assert not (workspace / "first.txt").exists()
        assert not (workspace / "second.txt").exists()
        assert not list(workspace.glob(".__lmh_upload__.*.tmp"))

        no_files = client.post(
            "/api/upload", params={"sid": session.id}, files=[])
        assert no_files.status_code in {400, 422}


def test_chat_request_validation_and_stop_endpoint(isolated_server: Path):
    session = Session("0f1e2d3c4b5a", workspace=str(isolated_server / "workspace"))
    server.SESSIONS[session.id] = session
    with local_client() as client:
        empty = client.post("/api/chat", json={
            "session_id": session.id, "message": "   "})
        assert empty.status_code == 422
        oversized = client.post("/api/chat", json={
            "session_id": session.id,
            "message": "x" * (max(4000, server.CFG.compact_threshold * 3) + 1),
        })
        assert oversized.status_code == 413
        assert client.post(f"/api/sessions/{session.id}/stop").status_code == 200


def test_session_mode_is_created_switched_and_persisted(isolated_server: Path):
    with local_client() as client:
        created = client.post("/api/sessions", json={"mode": "chat"})
        assert created.status_code == 200
        sid = created.json()["id"]
        assert created.json()["mode"] == "chat"
        changed = client.patch(
            f"/api/sessions/{sid}", json={"mode": "agent"})
        assert changed.status_code == 200
        assert changed.json()["mode"] == "agent"
        path = server.SESSIONS_DIR / f"{sid}.json"
        assert json.loads(path.read_text(encoding="utf-8"))["mode"] == "agent"


def test_session_undo_and_targeted_revert_routes(isolated_server: Path):
    workspace = isolated_server / "workspace"
    workspace.mkdir()
    session = Session("112233aabbcc", workspace=str(workspace))
    session.display = [
        {"t": "user", "text": "first"}, {"t": "text", "text": "one"},
        {"t": "user", "text": "second"}, {"t": "text", "text": "two"},
    ]
    agent = session.agent
    agent.ctx.messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "one"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "two"},
    ]
    agent.turn_no = 2
    agent.turn_marks = [
        {"turn": 1, "msg_index": 0}, {"turn": 2, "msg_index": 2},
    ]
    server.SESSIONS[session.id] = session

    with local_client() as client:
        undo = client.post(f"/api/sessions/{session.id}/undo")
        assert undo.status_code == 200
        assert undo.json()["text"] == "second"
        assert session.display == [
            {"t": "user", "text": "first"}, {"t": "text", "text": "one"},
        ]

        session.display.extend([
            {"t": "user", "text": "replacement"},
            {"t": "text", "text": "replacement answer"},
        ])
        targeted = client.post(
            f"/api/sessions/{session.id}/revert", json={"display_index": 0})
        assert targeted.status_code == 200
        assert targeted.json()["text"] == "first"
        assert session.display == []
