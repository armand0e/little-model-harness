"""Manual smoke test for write-time verification."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.verify import check_written_file  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="lmh-verify-") as scratch_dir:
        scratch = Path(scratch_dir)
        bad = scratch / "vtest.html"
        bad.write_text(
            '<!doctype html><html><head><title>t</title></head><body>\n'
            '<script type="module">import * as THREE from \'three\';</script>\n'
            '<script>renderScene();</script>\n'
            '</body></html>', encoding="utf-8")
        print("--- broken html (bare module import + undefined fn) ---")
        print(check_written_file(bad))

        good = scratch / "vtest_ok.html"
        good.write_text(
            '<!doctype html><html><head><title>ok</title></head><body>'
            '<h1>hi</h1><script>console.log(1+1)</script></body></html>',
            encoding="utf-8")
        print("--- good html ---")
        print(check_written_file(good))

        badjs = scratch / "vtest.js"
        badjs.write_text("function f( { return 1; }", encoding="utf-8")
        print("--- broken js ---")
        print(check_written_file(badjs))


if __name__ == "__main__":
    main()
