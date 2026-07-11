"""Test the stealth browser worker: selftest, search, fetch, reddit."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from harness import browser  # noqa: E402

print("available:", browser.available())

st = browser.self_test()
print("selftest:", st["verdict"], "| warnings:", st["warnings"] or "none")
print("UA:", st["fingerprint"]["userAgent"][:100])

r = browser.search("python openpyxl freeze panes")
print(f"\nsearch: {len(r)} results; first: {r[0]['title'][:60]} -> {r[0]['url'][:60]}")

t = browser.fetch("https://example.com")
print("\nfetch example.com:", t[:80].replace("\n", " "))

rd = browser.fetch("https://www.reddit.com/r/LocalLLaMA/top/")
print("\nreddit fetch (first 200):", rd[:200].replace("\n", " | "))
