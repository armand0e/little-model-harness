"""Test the stealth browser worker: selftest, search, fetch, reddit."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import browser  # noqa: E402


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("available:", browser.available())

    st = browser.self_test()
    print("selftest:", st["verdict"], "| warnings:", st["warnings"] or "none")
    print("UA:", st["fingerprint"]["userAgent"][:100])

    results = browser.search("python openpyxl freeze panes")
    print(f"\nsearch: {len(results)} results; first: "
          f"{results[0]['title'][:60]} -> {results[0]['url'][:60]}")

    text = browser.fetch("https://example.com")
    print("\nfetch example.com:", text[:80].replace("\n", " "))

    reddit = browser.fetch("https://www.reddit.com/r/LocalLLaMA/top/")
    print("\nreddit fetch (first 200):", reddit[:200].replace("\n", " | "))


if __name__ == "__main__":
    main()
