"""Dump a session display log compactly. Usage: python dump_session.py <id> [start] [end]"""
import json
import sys
from pathlib import Path


def one(value, length):
    return (value or "").replace("\n", " ")[:length]


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.config import SESSIONS_DIR  # noqa: E402 - path bootstrap above

sid = sys.argv[1]
start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
end = int(sys.argv[3]) if len(sys.argv) > 3 else 10**9

d = json.load(open(SESSIONS_DIR / f"{sid}.json", encoding="utf-8"))
print("TITLE:", d["title"], "| items:", len(d["display"]))
for i, it in enumerate(d["display"]):
    if not (start <= i <= end):
        continue
    t = it.get("t")
    if t == "user":
        print(f"\n=== [{i}] USER: {one(it['text'], 300)}")
    elif t == "tool":
        err = "ERR" if (it.get("result") or "").strip().startswith("Error") else "ok"
        print(f"[{i}] {it['name']}({one(it.get('args'), 90)}) [{err}] -> {one(it.get('result'), 140)}")
    elif t == "error":
        print(f"[{i}] !!ERROR: {one(it['text'], 200)}")
    elif t == "notice":
        print(f"[{i}] notice: {one(it['text'], 100)}")
    elif t == "text":
        print(f"[{i}] text: {one(it['text'], 160)}")
