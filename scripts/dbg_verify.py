import re
import subprocess
from pathlib import Path

from harness.verify import CAPTURE_SCRIPT, _find_browser

b = _find_browser()
print("browser:", b)
p = Path("workspace/vdbg.html")
p.write_text("<!doctype html><html><head><title>t</title></head>"
             "<body><script>boom();</script></body></html>", encoding="utf-8")
html = p.read_text()
m = re.search(r"<head[^>]*>", html)
wrapped = html[:m.end()] + CAPTURE_SCRIPT + html[m.end():]
tmp = (p.parent / (".__lmh_check__" + p.name)).resolve()
tmp.write_text(wrapped, encoding="utf-8")
r = subprocess.run([b, "--headless=new", "--disable-gpu", "--no-first-run",
                    "--virtual-time-budget=4000", "--timeout=9000",
                    "--dump-dom", tmp.as_uri()],
                   capture_output=True, text=True, timeout=30,
                   encoding="utf-8", errors="replace")
print("rc:", r.returncode, "stdout len:", len(r.stdout or ""))
print("stderr:", (r.stderr or "")[:400])
print("errlog present:", "lmh_errlog" in (r.stdout or ""))
mm = re.search(r'id="__lmh_errlog"[^>]*data-errors="([^"]*)"', r.stdout or "")
print("match:", mm.group(1) if mm else None)
print("dom tail:", (r.stdout or "")[-400:])
tmp.unlink()
p.unlink()
