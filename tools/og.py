"""Renders assets/og-default.png (1200x630) from tools/og-template.html with Playwright.

Usage (needs Playwright + Chromium and network for Google Fonts):
    python tools/og.py
"""

import struct
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "tools" / "og-template.html"
OUT = ROOT / "assets" / "og-default.png"
WIDTH, HEIGHT = 1200, 630


def render() -> tuple[int, int]:
    """Screenshots the template at exactly 1200x630 and returns the PNG's size."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Reason: device_scale_factor=1 keeps the PNG at 1200x630 instead of 2x on HiDPI defaults.
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
        page.goto(TEMPLATE.as_uri(), wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        if not page.evaluate("document.fonts.check('700 112px \"JetBrains Mono\"')"):
            raise RuntimeError("JetBrains Mono did not load; refusing to render with a fallback font")
        page.screenshot(path=str(OUT), clip={"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT})
        browser.close()
    return struct.unpack(">II", OUT.read_bytes()[16:24])


if __name__ == "__main__":
    w, h = render()
    print(f"wrote {OUT.relative_to(ROOT)} ({w}x{h})")
