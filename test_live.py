"""Live smoke test against the local model. Usage: python test_live.py "prompt" """
import sys
import time

from harness.agent import Agent


def emit(etype, data):
    if etype == "reasoning_delta":
        return
    if etype == "content_delta":
        print(data, end="", flush=True)
    elif etype == "tool_call":
        print(f"\n[TOOL CALL] {data['name']} {data['arguments'][:300]}")
    elif etype == "tool_result":
        r = data["result"]
        print(f"[RESULT] {r[:400]}{'...' if len(r) > 400 else ''}")
    elif etype == "usage":
        print(f"[USAGE] prompt={data['prompt']} completion={data['completion']}")
    else:
        print(f"\n[{etype.upper()}] {data}")


agent = Agent()
t0 = time.time()
final = agent.run_turn(sys.argv[1], on_event=emit)
print(f"\n\n=== FINAL ({time.time() - t0:.0f}s) ===\n{final}")
print(f"=== STATUS === {agent.context_status()}")
