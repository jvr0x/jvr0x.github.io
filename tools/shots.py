"""Checks horizontal overflow and takes full-page screenshots of every site page.

Usage (needs Playwright + Chromium; serve the repo root first):
    python3 -m http.server 8000 &
    python tools/shots.py http://localhost:8000 OUT_DIR

Fails (exit 1) if any page scrolls horizontally or has an element sticking out past the
viewport at 390x844 or 1280x800, or if the homepage signup embed starts below the fold.
"""

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
VIEWPORTS = ((390, 844), (1280, 800))
PROJECT_PREFIXES = ("/tok-sim/", "/dgx-spark-bench/", "/murmur/", "/soldecode-extension/")

# Reason: style.css sets body{overflow-x:hidden}, which hides overflow from scrollWidth.
# Lift it and also list elements whose box pokes past the viewport, unless an ancestor
# clips them (e.g. the voxel hub's scaled 1920px preview iframes).
OVERFLOW_JS = """(vw) => {
  document.documentElement.style.overflowX = 'visible';
  document.body.style.overflowX = 'visible';
  const clipped = (el) => {
    for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) {
      const o = getComputedStyle(e).overflowX;
      if (o === 'hidden' || o === 'auto' || o === 'scroll' || o === 'clip') return true;
    }
    return false;
  };
  const wide = [...document.body.querySelectorAll('*')]
    .filter((e) => e.getBoundingClientRect().right > vw + 0.5 && !clipped(e))
    .slice(0, 5)
    .map((e) => e.tagName.toLowerCase() + '.' + String(e.className) + ' right=' + Math.round(e.getBoundingClientRect().right));
  const sw = document.documentElement.scrollWidth;
  document.documentElement.style.overflowX = '';
  document.body.style.overflowX = '';
  return { scrollWidth: sw, wide };
}"""


def site_paths() -> list[str]:
    """Returns sitemap paths served by this repo."""
    xml = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    paths = [re.sub(r"^https://jvr0x\.com", "", u) for u in re.findall(r"<loc>([^<]+)</loc>", xml)]
    return [p for p in paths if not p.startswith(PROJECT_PREFIXES)]


def main(base: str, out_dir: Path) -> int:
    """Visits each page at each viewport, records problems and saves screenshots."""
    out_dir.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for w, h in VIEWPORTS:
            for path in site_paths():
                page = browser.new_page(viewport={"width": w, "height": h})
                page.goto(base + path, wait_until="networkidle")
                if path == "/":
                    box = page.locator(".hero-signup iframe").bounding_box()
                    if not box or box["y"] > h - 200:
                        problems.append(f"{path} @{w}: signup embed starts below the fold ({box})")
                    else:
                        print(f"{path} @{w}x{h}: embed top={box['y']:.0f} bottom={box['y'] + box['height']:.0f}")
                # Show fade-in content and trigger lazy iframes before the full-page shot.
                page.evaluate("document.querySelectorAll('.fade-in').forEach(e => e.classList.add('visible'))")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2500)
                page.evaluate("window.scrollTo(0, 0)")
                info = page.evaluate(OVERFLOW_JS, w)
                if info["scrollWidth"] > w or info["wide"]:
                    problems.append(f"{path} @{w}: overflow {info}")
                name = path.strip("/").replace("/", "_") or "home"
                page.screenshot(path=str(out_dir / f"{name}-{w}.png"), full_page=True)
                page.close()
        browser.close()
    for problem in problems:
        print("FAIL", problem)
    print(f"{len(site_paths())} pages x {len(VIEWPORTS)} viewports: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1].rstrip("/"), Path(sys.argv[2])))
