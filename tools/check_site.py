#!/usr/bin/env python3
"""Checks the built site offline: head/OG tags, internal links and the OG image size.

Usage: python3 tools/check_site.py      (exit code 1 on any problem; stdlib only)

- Every page in sitemap.xml that this repo serves must carry the full OG/Twitter set
  with absolute URLs, and canonical == og:url with a trailing slash.
- Every root-relative or relative href/src in those pages must resolve to a file in the
  repo, except paths served by other repos (PROJECT_PREFIXES).
- assets/og-default.png must be exactly 1200x630.
"""

from __future__ import annotations

import re
import struct
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://jvr0x.com"
# Served by other repos on the same domain (GitHub Pages project sites).
PROJECT_PREFIXES = ("/tok-sim/", "/dgx-spark-bench/", "/murmur/", "/soldecode-extension/")
REQUIRED_META = (
    ("property", "og:title"),
    ("property", "og:description"),
    ("property", "og:url"),
    ("property", "og:image"),
    ("name", "twitter:card"),
    ("name", "twitter:site"),
    ("name", "twitter:creator"),
    ("name", "twitter:title"),
    ("name", "twitter:description"),
    ("name", "twitter:image"),
)


class PageScan(HTMLParser):
    """Collects meta tags, the canonical link, the title and every href/src of a page."""

    def __init__(self) -> None:
        """Initializes empty collections."""
        super().__init__()
        self.meta: dict[tuple[str, str], str] = {}
        self.canonical: str | None = None
        self.refs: list[str] = []
        self.has_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Records the attributes we check."""
        a = {k: v or "" for k, v in attrs}
        if tag == "meta":
            for kind in ("property", "name"):
                if kind in a:
                    self.meta[(kind, a[kind])] = a.get("content", "")
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        if tag == "title":
            self.has_title = True
        for attr in ("href", "src"):
            if attr in a and tag in ("a", "link", "script", "img", "iframe"):
                self.refs.append(a[attr])


def sitemap_paths() -> list[str]:
    """Returns the URL paths listed in sitemap.xml."""
    xml = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    return [urlparse(u).path for u in re.findall(r"<loc>([^<]+)</loc>", xml)]


def resolve(path: str) -> Path | None:
    """Maps a URL path to the file GitHub Pages would serve, or None if missing."""
    target = ROOT / path.lstrip("/")
    if path.endswith("/") or target.is_dir():
        target = target / "index.html"
    return target if target.is_file() else None


def check_page(path: str) -> list[str]:
    """Returns the problems found on one served page."""
    file = resolve(path)
    if file is None:
        return [f"{path}: no file in repo"]
    scan = PageScan()
    scan.feed(file.read_text(encoding="utf-8"))
    problems = []
    url = SITE + path
    if not scan.has_title:
        problems.append(f"{path}: missing <title>")
    for key in REQUIRED_META:
        if not scan.meta.get(key):
            problems.append(f"{path}: missing {key[1]}")
    if scan.meta.get(("property", "og:url")) != url:
        problems.append(f"{path}: og:url should be {url}")
    if scan.canonical != url:
        problems.append(f"{path}: canonical should be {url}")
    for key in (("property", "og:image"), ("name", "twitter:image")):
        if not scan.meta.get(key, "").startswith("https://"):
            problems.append(f"{path}: {key[1]} must be absolute")
    if scan.meta.get(("name", "twitter:card")) != "summary_large_image":
        problems.append(f"{path}: twitter:card should be summary_large_image")
    for ref in scan.refs:
        target = urlparse(urljoin(url, ref))
        if target.scheme not in ("http", "https") or target.netloc != "jvr0x.com":
            continue
        if target.path.startswith(PROJECT_PREFIXES):
            continue
        if resolve(target.path) is None:
            problems.append(f"{path}: broken internal link {ref}")
    return problems


def png_size(path: Path) -> tuple[int, int]:
    """Reads width/height from a PNG's IHDR chunk."""
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    return struct.unpack(">II", head[16:24])


def main() -> int:
    """Runs all checks and prints a summary."""
    problems: list[str] = []
    paths = sitemap_paths()
    for path in paths:
        if path.startswith(PROJECT_PREFIXES):
            continue
        problems += check_page(path)
    size = png_size(ROOT / "assets" / "og-default.png")
    if size != (1200, 630):
        problems.append(f"assets/og-default.png is {size[0]}x{size[1]}, expected 1200x630")
    for p in problems:
        print("FAIL", p)
    print(f"checked {len(paths)} sitemap URLs, og-default.png {size[0]}x{size[1]}: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
