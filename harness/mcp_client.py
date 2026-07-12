"""Persistent local MCP client used to extend the agent tool registry.

Configured servers use the familiar Claude Desktop shape::

    {"filesystem": {"command": "npx", "args": ["-y", "..."],
                     "env": {"OPTIONAL": "value"}, "enabled": true}}

Each stdio server stays connected on a dedicated asyncio loop. Public tool
names are namespaced so an MCP server cannot replace a built-in harness tool.
"""
from __future__ import annotations

import asyncio
import atexit
import json
import os
import platform
import re
import shutil
import sys
import threading
from concurrent.futures import Future as ConcurrentFuture
from dataclasses import dataclass
from typing import Any

CONNECT_TIMEOUT = 15.0
CALL_TIMEOUT = 120.0
MAX_SERVERS = 20
MAX_TOOLS = 200
MAX_RESULT_CHARS = 100_000
MAX_ERROR_RESULT_CHARS = 4_000
MAX_SCHEMA_CHARS = 20_000
MAX_MCP_IMAGE_BASE64 = 8_000_000
MCP_IMAGE_MARKER = "__MCP_IMAGE_RESULT__:"
BUILTIN_COMPUTER_SERVER = "_little_harness_computer"


def validate_mcp_servers(value: object) -> dict[str, dict]:
    """Return a normalized, JSON-safe stdio server configuration."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("MCP servers must be a JSON object")
    if len(value) > MAX_SERVERS:
        raise ValueError(f"configure at most {MAX_SERVERS} MCP servers")
    out: dict[str, dict] = {}
    for raw_name, raw in value.items():
        if not isinstance(raw_name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,50}", raw_name):
            raise ValueError("MCP server names must use 1-50 letters, numbers, dot, dash, or underscore")
        if not isinstance(raw, dict):
            raise ValueError(f"MCP server {raw_name!r} must be an object")
        unknown = set(raw) - {"command", "args", "env", "enabled"}
        if unknown:
            raise ValueError(
                f"MCP server {raw_name!r} has unsupported fields: {', '.join(sorted(unknown))}")
        command = raw.get("command")
        args = raw.get("args", [])
        env = raw.get("env", {})
        enabled = raw.get("enabled", True)
        if not isinstance(command, str) or not command.strip() or len(command) > 1000:
            raise ValueError(f"MCP server {raw_name!r} needs a command")
        if (not isinstance(args, list) or len(args) > 100
                or not all(isinstance(arg, str) and len(arg) <= 4000 for arg in args)):
            raise ValueError(f"MCP server {raw_name!r} args must be a list of strings")
        if (not isinstance(env, dict) or len(env) > 100
                or not all(isinstance(k, str) and isinstance(v, str)
                           and len(k) <= 200 and len(v) <= 10_000
                           for k, v in env.items())):
            raise ValueError(f"MCP server {raw_name!r} env must map strings to strings")
        if not isinstance(enabled, bool):
            raise ValueError(f"MCP server {raw_name!r} enabled must be true or false")
        out[raw_name] = {
            "command": command.strip(), "args": args, "env": env,
            "enabled": enabled,
        }
    return out


def load_user_mcp_servers() -> dict[str, dict]:
    from .config import load_user_settings
    try:
        return validate_mcp_servers(load_user_settings().get("mcp_servers", {}))
    except ValueError:
        return {}


def computer_backend_info() -> dict[str, object]:
    """Locate the trusted cross-platform computer-use runtime.

    Packaged builds carry the pinned native binary. Source checkouts may opt
    in with LMH_COMPUTER_USE_BIN or a system installation; tests and ordinary
    source imports never start an untracked file from build/ implicitly.
    """
    if os.environ.get("LMH_DISABLE_COMPUTER_USE"):
        return {"available": False, "backend": platform.system(),
                "source": "disabled", "command": None}
    override = os.environ.get("LMH_COMPUTER_USE_BIN", "").strip()
    command: str | None = None
    source = "unavailable"
    if override:
        candidate = os.path.abspath(os.path.expanduser(override))
        if os.path.isfile(candidate):
            command, source = candidate, "environment"
    elif getattr(sys, "frozen", False):
        from .config import ROOT
        name = "open-computer-use.exe" if sys.platform == "win32" \
            else "open-computer-use"
        bundle_candidate = ROOT / "computer-use" / name
        if bundle_candidate.is_file():
            command, source = str(bundle_candidate), "bundled"
    else:
        found = shutil.which("open-computer-use")
        if found:
            command, source = found, "system"
    return {"available": command is not None,
            "backend": {"Windows": "Windows UI Automation",
                        "Darwin": "macOS Accessibility",
                        "Linux": "Linux AT-SPI"}.get(platform.system(),
                                                       platform.system()),
            "source": source, "command": command}


def merge_builtin_mcp_servers(user_servers: dict[str, dict]) -> dict[str, dict]:
    # This namespace is reserved so a user MCP cannot impersonate the trusted
    # facade or feed it spoofed computer-state results.
    merged = {name: cfg for name, cfg in user_servers.items()
              if name != BUILTIN_COMPUTER_SERVER}
    info = computer_backend_info()
    command = info.get("command")
    if info.get("available") and isinstance(command, str):
        computer_env = {}
        if platform.system() == "Windows":
            # Chrome and other Chromium apps often require UIA ValuePattern
            # text entry. This can foreground the target, which is expected
            # while the user has explicitly enabled first-class computer use.
            computer_env["OPEN_COMPUTER_USE_WINDOWS_ALLOW_UIA_TEXT_FALLBACK"] = "1"
            computer_env["OPEN_COMPUTER_USE_WINDOWS_ALLOW_FOCUS_ACTIONS"] = "1"
        merged[BUILTIN_COMPUTER_SERVER] = {
            "command": command, "args": ["mcp"], "env": computer_env,
            "enabled": True,
        }
    return merged


def load_mcp_servers() -> dict[str, dict]:
    return merge_builtin_mcp_servers(load_user_mcp_servers())


@dataclass
class _Worker:
    name: str
    requests: asyncio.Queue
    task: asyncio.Task


class MCPHub:
    """Thread-safe bridge from synchronous agent tools to async MCP sessions."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._configure_lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._workers: dict[str, _Worker] = {}
        self._schemas: list[dict] = []
        self._routes: dict[str, tuple[str, str]] = {}
        self._schema_sources: dict[str, str] = {}
        self._status: dict[str, dict] = {}
        self._config_json = ""

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is not None and self._thread and self._thread.is_alive():
                return self._loop
            ready = threading.Event()

            def run() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                with self._lock:
                    self._loop = loop
                ready.set()
                loop.run_forever()
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.close()

            self._thread = threading.Thread(
                target=run, name="lmh-mcp", daemon=True)
            self._thread.start()
        ready.wait(5)
        if self._loop is None:
            raise RuntimeError("could not start the MCP event loop")
        return self._loop

    def configure(self, servers: object, timeout: float = 30.0,
                  force: bool = False) -> list[dict]:
        config = validate_mcp_servers(servers)
        config_json = json.dumps(config, sort_keys=True)
        with self._configure_lock:
            with self._lock:
                if not force and config_json == self._config_json:
                    return self.status()
            loop = self._ensure_loop()
            future = asyncio.run_coroutine_threadsafe(self._configure(config), loop)
            try:
                future.result(timeout=timeout)
            except Exception as exc:
                raise RuntimeError(
                    f"could not configure MCP servers: {exc}") from exc
            with self._lock:
                self._config_json = config_json
            return self.status()

    async def _configure(self, config: dict[str, dict]) -> None:
        workers = list(self._workers.values())
        self._workers = {}
        for worker in workers:
            worker.task.cancel()
        if workers:
            await asyncio.gather(
                *(worker.task for worker in workers), return_exceptions=True)

        ready: dict[str, asyncio.Future] = {}
        with self._lock:
            self._schemas = []
            self._routes = {}
            self._schema_sources = {}
            self._status = {
                name: {"name": name, "enabled": cfg["enabled"],
                       "state": "disabled" if not cfg["enabled"] else "connecting",
                       "error": None, "tools": 0}
                for name, cfg in config.items()
            }
        for name, cfg in config.items():
            if not cfg["enabled"]:
                continue
            requests: asyncio.Queue = asyncio.Queue()
            result = asyncio.get_running_loop().create_future()
            task = asyncio.create_task(
                self._server_worker(name, cfg, requests, result),
                name=f"mcp:{name}",
            )
            self._workers[name] = _Worker(name, requests, task)
            ready[name] = result

        async def wait_ready(name: str, result: asyncio.Future) -> tuple[str, list[dict], str | None]:
            try:
                tools = await asyncio.wait_for(
                    asyncio.shield(result), CONNECT_TIMEOUT)
                return name, tools, None
            except Exception as exc:
                message = str(exc) or type(exc).__name__
                return name, [], message

        discovered: dict[str, list[dict]] = {}
        results = await asyncio.gather(
            *(wait_ready(name, result) for name, result in ready.items()))
        for name, tools, error in results:
            discovered[name] = tools
            if error:
                self._set_status(name, "error", error, 0)
                failed_worker = self._workers.get(name)
                if failed_worker:
                    self._workers.pop(name)
                    failed_worker.task.cancel()
                    await asyncio.gather(
                        failed_worker.task, return_exceptions=True)

        schemas: list[dict] = []
        routes: dict[str, tuple[str, str]] = {}
        sources: dict[str, str] = {}
        for server_name in sorted(discovered):
            for tool in discovered[server_name]:
                if len(schemas) >= MAX_TOOLS:
                    break
                original = str(tool.get("name", ""))
                if not original:
                    continue
                public = _public_tool_name(server_name, original, set(routes))
                input_schema = (tool.get("inputSchema")
                                if isinstance(tool.get("inputSchema"), dict)
                                else {"type": "object", "properties": {}})
                try:
                    if len(json.dumps(input_schema, ensure_ascii=False)) \
                            > MAX_SCHEMA_CHARS:
                        input_schema = {"type": "object", "properties": {}}
                except (TypeError, ValueError):
                    input_schema = {"type": "object", "properties": {}}
                schema = {
                    "type": "function",
                    "function": {
                        "name": public,
                        "description": (
                            f"MCP server {server_name}: "
                            f"{tool.get('description') or original}")[:1000],
                        "parameters": input_schema,
                    },
                }
                schemas.append(schema)
                routes[public] = (server_name, original)
                sources[public] = server_name
            self._set_status(server_name, "ready", None,
                             len(discovered[server_name]))
        with self._lock:
            self._schemas = schemas
            self._routes = routes
            self._schema_sources = sources

    async def _server_worker(
            self, name: str, cfg: dict, requests: asyncio.Queue,
            ready: asyncio.Future) -> None:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            command, args = _resolved_command(cfg["command"], cfg["args"])
            params = StdioServerParameters(
                command=command,
                args=args,
                env={**os.environ, **cfg["env"]} if cfg["env"] else None,
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.list_tools()
                    tools = [tool.model_dump(by_alias=True) for tool in response.tools]
                    if not ready.done():
                        ready.set_result(tools)
                    while True:
                        tool_name, arguments, result = await requests.get()
                        try:
                            value = await session.call_tool(tool_name, arguments=arguments)
                            if not result.done():
                                result.set_result(value)
                        except Exception as exc:
                            if not result.done():
                                result.set_exception(exc)
        except asyncio.CancelledError:
            if not ready.done():
                ready.cancel()
            raise
        except Exception as exc:
            if not ready.done():
                ready.set_exception(exc)
            self._set_status(name, "error", str(exc), 0)
        finally:
            while True:
                try:
                    _, _, result = requests.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if not result.done():
                    result.set_exception(
                        RuntimeError(f"MCP server {name!r} disconnected"))

    def _set_status(self, name: str, state: str,
                    error: str | None, tools: int) -> None:
        with self._lock:
            previous = self._status.get(name, {"name": name, "enabled": True})
            self._status[name] = {
                **previous, "state": state,
                "error": error[:500] if error else None, "tools": tools,
            }

    def ensure_configured(self) -> None:
        with self._lock:
            configured = bool(self._config_json)
        if not configured:
            self.configure(load_mcp_servers())

    def schemas(self, include_builtin: bool = True) -> list[dict]:
        self.ensure_configured()
        with self._lock:
            if include_builtin:
                return list(self._schemas)
            return [schema for schema in self._schemas
                    if self._schema_sources.get(
                        schema["function"]["name"]) != BUILTIN_COMPUTER_SERVER]

    def search(self, query: str, limit: int = 10) -> str:
        """Return a compact catalog so large MCP sets need not fill context."""
        query = " ".join(query.casefold().split())
        terms = set(re.findall(r"[a-z0-9_-]{2,}", query))
        schemas = self.schemas(include_builtin=False)
        ranked: list[tuple[int, str, dict]] = []
        for schema in schemas:
            function = schema.get("function", {})
            if not isinstance(function, dict):
                continue
            name = str(function.get("name", ""))
            description = str(function.get("description", ""))
            haystack = f"{name} {description}".casefold()
            if terms and not all(term in haystack for term in terms):
                continue
            score = (100 if query and query in haystack else 0)
            score += sum(10 for term in terms if term in name.casefold())
            ranked.append((-score, name, function))
        ranked.sort(key=lambda item: (item[0], item[1]))
        if not ranked:
            return f"No MCP tools matched {query!r}."
        lines = ["Available MCP tools (call with mcp action='call'):"]
        for _, name, function in ranked[:max(1, min(20, limit))]:
            params = function.get("parameters", {})
            required = params.get("required", []) if isinstance(params, dict) else []
            requirement = (f" required={','.join(map(str, required))}"
                           if required else "")
            lines.append(
                f"- {name}{requirement}: {str(function.get('description', ''))[:240]}")
        if len(ranked) > limit:
            lines.append(f"...{len(ranked) - limit} more matches; narrow the query.")
        return "\n".join(lines)

    def has_tool(self, name: str) -> bool:
        self.ensure_configured()
        with self._lock:
            return name in self._routes

    def is_user_tool(self, name: str) -> bool:
        self.ensure_configured()
        with self._lock:
            return (name in self._routes
                    and self._schema_sources.get(name) != BUILTIN_COMPUTER_SERVER)

    def call(self, public_name: str, arguments: dict,
             timeout: float = CALL_TIMEOUT) -> str:
        self.ensure_configured()
        with self._lock:
            route = self._routes.get(public_name)
        if route is None:
            return f"Error: MCP tool {public_name!r} is unavailable."
        server_name, tool_name = route
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._call(server_name, tool_name, arguments), loop)
        try:
            result = future.result(timeout=timeout)
            return _format_result(result)
        except Exception as exc:
            future.cancel()
            return f"Error running MCP tool {public_name}: {type(exc).__name__}: {exc}"

    async def _call(self, server_name: str, tool_name: str,
                    arguments: dict) -> Any:
        worker = self._workers.get(server_name)
        if worker is None or worker.task.done():
            raise RuntimeError(f"MCP server {server_name!r} is not connected")
        result = asyncio.get_running_loop().create_future()
        await worker.requests.put((tool_name, arguments, result))
        return await asyncio.wait_for(result, CALL_TIMEOUT)

    def status(self) -> list[dict]:
        with self._lock:
            return [dict(self._status[name]) for name in sorted(self._status)]

    def close(self) -> None:
        with self._configure_lock:
            with self._lock:
                loop, thread = self._loop, self._thread
            if loop is None or thread is None:
                return
            try:
                future: ConcurrentFuture = asyncio.run_coroutine_threadsafe(
                    self._configure({}), loop)
                future.result(timeout=5)
            except Exception:
                pass
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=5)
            with self._lock:
                if not thread.is_alive() and self._thread is thread:
                    self._loop = None
                    self._thread = None
                    self._config_json = ""


def _resolved_command(command: str, args: list[str]) -> tuple[str, list[str]]:
    if getattr(sys, "frozen", False) and command.lower() in {"python", "python3"}:
        from .tools.shell import _frozen_cli_exe
        return _frozen_cli_exe(), ["--runpy", *args]
    resolved = shutil.which(command) if not os.path.isabs(command) else command
    if not resolved:
        raise FileNotFoundError(f"MCP command not found: {command}")
    return resolved, list(args)


def _public_tool_name(server: str, tool: str, used: set[str]) -> str:
    raw = (f"computer_{tool}" if server == BUILTIN_COMPUTER_SERVER
           else f"mcp_{server}_{tool}")
    base = re.sub(r"[^A-Za-z0-9_-]", "_", raw)[:60].strip("_")
    base = base or "mcp_tool"
    name, suffix = base, 2
    while name in used:
        tail = f"_{suffix}"
        name = base[:64 - len(tail)] + tail
        suffix += 1
    return name


def _format_result(result: Any) -> str:
    parts: list[str] = []
    images: list[dict[str, str]] = []
    image_chars = 0
    for block in getattr(result, "content", []) or []:
        kind = getattr(block, "type", "")
        if kind == "text":
            parts.append(str(getattr(block, "text", "")))
        elif kind == "image":
            mime = str(getattr(block, "mimeType", "") or "")
            data = str(getattr(block, "data", "") or "")
            if (mime in {"image/png", "image/jpeg", "image/webp"} and data
                    and image_chars + len(data) <= MAX_MCP_IMAGE_BASE64
                    and len(images) < 3):
                images.append({"mime": mime, "data": data})
                image_chars += len(data)
            else:
                parts.append(f"[MCP image omitted: {mime or 'unknown type'}, "
                             f"{len(data)} base64 characters]")
        else:
            try:
                parts.append(json.dumps(block.model_dump(by_alias=True), ensure_ascii=False))
            except Exception:
                parts.append(str(block))
    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if structured is not None and not parts:
        parts.append(json.dumps(structured, ensure_ascii=False, indent=2))
    text = "\n".join(part for part in parts if part) or "(MCP tool returned no content)"
    if getattr(result, "isError", False) or getattr(result, "is_error", False):
        text = "Error: " + text
        if len(text) > MAX_ERROR_RESULT_CHARS:
            text = text[:MAX_ERROR_RESULT_CHARS] + "\n...[MCP error truncated]"
    elif len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + "\n...[MCP result truncated]"
    if images:
        # The agent removes image bytes from the tool result before inserting
        # it into context, then attaches validated image parts in a following
        # user message so OpenAI-compatible tool-call ordering stays valid.
        return MCP_IMAGE_MARKER + json.dumps(
            {"report": text, "images": images}, separators=(",", ":"))
    if text.startswith(MCP_IMAGE_MARKER):
        text = "[MCP text] " + text
    return text


MCP_HUB = MCPHub()
atexit.register(MCP_HUB.close)
