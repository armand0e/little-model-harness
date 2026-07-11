"""Synthetic test: mid-turn fading + compaction in a MONO-TURN agentic
session (one user message, many tool rounds) — the shape that previously
defeated both context defenses."""
from harness.config import load_config
from harness.context import ContextManager, FADE_STUB
from harness.llm import LLMClient

cfg = load_config()
cfg.context_window = 32768
cfg.output_reserve = 16384
ctx = ContextManager(cfg)
llm = LLMClient(cfg.base_url, cfg.model)

# ONE user message, then 40 assistant/tool rounds (like a long debug session)
ctx.add_user("Make me a 3D model of a plane and animate it taking off.")
for i in range(40):
    ctx.add_assistant({"role": "assistant", "content": "", "tool_calls": [
        {"id": f"c{i}", "type": "function",
         "function": {"name": "run", "arguments": '{"command": "blender"}'}}]})
    ctx.add_tool_result(f"c{i}", "run",
                        f"Blender output round {i}: " + "Error trace line. " * 80)
    ctx.add_assistant({"role": "assistant", "content": f"Attempt {i} analysis."})

before = ctx.estimated_tokens(1900)
print(f"threshold={ctx.threshold()}  before={before}")
events = []
ctx.ensure_budget(llm, 1900, lambda t, d: events.append((t, d)))
after = ctx.estimated_tokens(1900)
faded = sum(1 for m in ctx.messages
            if isinstance(m.get("content"), str) and m["content"] == FADE_STUB)
print(f"after={after}  events={events}")
print(f"messages={len(ctx.messages)}  faded={faded}  compactions={ctx.compactions}")
ok = all(ctx.messages[i - 1].get("tool_calls")
         for i, m in enumerate(ctx.messages) if m["role"] == "tool" and i > 0)
first_tool_ok = not (ctx.messages and ctx.messages[0]["role"] == "tool")
print("tool-pairing intact:", ok and first_tool_ok)
assert after < before, "budget did not shrink!"
assert faded > 0 or ctx.compactions > 0, "no defense fired in mono-turn!"
print("PASS")
