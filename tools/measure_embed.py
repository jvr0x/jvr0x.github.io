"""Measures the content height of the AGI Checkpoint Substack embed at several iframe widths.

The embed is cross-origin, so the parent page can't read its height. This script loads the
embed as a top-level page at each width and reports how tall its content is, which is what
the iframe heights in assets/chrome.css are derived from.

Usage (needs Playwright + Chromium):
    python tools/measure_embed.py [width ...]
"""

import sys

from playwright.sync_api import sync_playwright

EMBED_URL = "https://agicheckpoint.com/embed"
DEFAULT_WIDTHS = (300, 326, 358, 400, 448, 480)

# Reason: the embed centers its content in a min-height:100vh box and pins a
# watermark (position:absolute) plus a toast list (position:fixed) to the bottom edge, so
# document height just equals the viewport.
# Measure the extent of visible, non-fixed leaf elements in a tall viewport instead.
CONTENT_HEIGHT_JS = """() => {
  const isPinned = (el) => {
    for (let e = el; e && e !== document.body; e = e.parentElement) {
      const pos = getComputedStyle(e).position;
      if (pos === 'fixed' || pos === 'absolute') return true;
    }
    return false;
  };
  const leaves = [...document.body.querySelectorAll('*')].filter((e) => {
    const r = e.getBoundingClientRect();
    const cs = getComputedStyle(e);
    return e.children.length === 0 && r.width > 0 && r.height > 0 &&
      cs.visibility !== 'hidden' && cs.display !== 'none' && !isPinned(e);
  });
  const top = Math.min(...leaves.map((e) => e.getBoundingClientRect().top));
  const bottom = Math.max(...leaves.map((e) => e.getBoundingClientRect().bottom));
  return Math.ceil(bottom - top);
}"""


def measure(widths: list[int]) -> dict[int, int]:
    """Returns {iframe width: content height in px} for each requested width."""
    heights: dict[int, int] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in widths:
            page = browser.new_page(viewport={"width": width, "height": 1400})
            page.goto(EMBED_URL, wait_until="networkidle")
            page.wait_for_timeout(1000)
            heights[width] = page.evaluate(CONTENT_HEIGHT_JS)
            page.close()
        browser.close()
    return heights


if __name__ == "__main__":
    requested = [int(w) for w in sys.argv[1:]] or list(DEFAULT_WIDTHS)
    for w, h in measure(requested).items():
        print(f"width {w}px: content {h}px")
