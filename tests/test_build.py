"""Tests for tools/build.py (run: python -m pytest tests/)."""

import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import build

PAGE = """<!DOCTYPE html>
<html><head>
<!-- jx:head -->
<!-- /jx:head -->
</head><body>
<!-- jx:header -->
old header
<!-- /jx:header -->
<div class="cards">
<!-- jx:cards things -->
stale
<!-- /jx:cards -->
</div>
<!-- jx:footer -->
<!-- /jx:footer -->
</body></html>
"""


def make_site(root: Path, things: list | None = None, page: str = PAGE) -> Path:
    """Creates a minimal site (one page, partials, data) under root and returns it."""
    (root / "partials").mkdir()
    (root / "data").mkdir()
    shutil.copy(REPO / "partials" / "header.html", root / "partials" / "header.html")
    shutil.copy(REPO / "partials" / "footer.html", root / "partials" / "footer.html")
    pages = [
        {"path": "/", "file": "index.html", "title": "jvr0x", "description": "Local AI <test> & more"},
        {"path": "/tok-sim/"},
    ]
    (root / "data" / "pages.json").write_text(json.dumps(pages), encoding="utf-8")
    if things is None:
        things = [
            {
                "title": "A <b>",
                "url": "https://example.com/a",
                "description": "desc & stuff",
                "tags": ["t1"],
                "links": [{"label": "more", "url": "/more/"}],
            }
        ]
    (root / "data" / "things.json").write_text(json.dumps(things), encoding="utf-8")
    (root / "index.html").write_text(page, encoding="utf-8")
    return root


# ── Expected use ─────────────────────────────────────────────────────────────


def test_build_renders_head_chrome_cards_and_sitemap(tmp_path):
    """Fills every marker block from partials/data and writes the sitemap."""
    site = make_site(tmp_path)
    changed = build.build(site)
    out = (site / "index.html").read_text(encoding="utf-8")

    assert set(changed) == {"index.html", "sitemap.xml"}
    assert "old header" not in out and '<header class="jx-header">' in out
    assert '<footer class="jx-footer">' in out
    assert "<title>jvr0x</title>" in out
    assert '<meta property="og:url" content="https://jvr0x.com/">' in out
    assert '<meta name="twitter:card" content="summary_large_image">' in out
    # Data is escaped, cards are divs (no nested anchors), external links get noopener.
    assert "A &lt;b&gt;" in out and "desc &amp; stuff" in out and "Local AI &lt;test&gt; &amp; more" in out
    assert '<div class="card fade-in">' in out and "stale" not in out
    assert '<a href="https://example.com/a" rel="noopener">' in out
    assert '<a href="/more/">more</a>' in out
    sitemap = (site / "sitemap.xml").read_text(encoding="utf-8")
    assert "<loc>https://jvr0x.com/</loc>" in sitemap and "<loc>https://jvr0x.com/tok-sim/</loc>" in sitemap


def test_build_is_idempotent(tmp_path):
    """A second build over its own output changes nothing."""
    site = make_site(tmp_path)
    build.build(site)
    first = (site / "index.html").read_bytes()
    assert build.build(site) == []
    assert (site / "index.html").read_bytes() == first


def test_real_site_build_is_idempotent(tmp_path):
    """The committed site is already built: building a copy of it changes nothing."""
    site = tmp_path / "site"
    shutil.copytree(REPO, site, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    assert build.build(site) == []


def test_list_layout_renders_rows(tmp_path):
    """`<!-- jx:cards NAME list -->` renders compact rows and keeps the layout flag."""
    site = make_site(tmp_path, page=PAGE.replace("<!-- jx:cards things -->", "<!-- jx:cards things list -->"))
    build.build(site)
    out = (site / "index.html").read_text(encoding="utf-8")
    assert '<div class="row">' in out and "<!-- jx:cards things list -->" in out


def test_parse_recipe_yaml_last_key_wins_and_strips_comments():
    """Mirrors PyYAML (last duplicate key wins) and drops quotes/inline comments."""
    text = (
        "# Model X \N{EM DASH} fast profile. Second sentence.\n#\n# more\n"
        'runtime: llama\nmodel: "org/model"      # local path\ndisplay_name: Name\nruntime: "vllm"\n'
    )
    info = build.parse_recipe_yaml(text)
    assert info == {
        "runtime": "vllm",
        "model": "org/model",
        "display_name": "Name",
        "summary": "Model X - fast profile.",
    }


# ── Edge cases ───────────────────────────────────────────────────────────────


def test_missing_chrome_marker_fails_without_writing(tmp_path):
    """A listed page without the footer markers aborts the build and leaves files untouched."""
    page = PAGE.replace("<!-- jx:footer -->\n<!-- /jx:footer -->\n", "")
    site = make_site(tmp_path, page=page)
    with pytest.raises(build.BuildError, match="missing <!-- jx:footer -->"):
        build.build(site)
    assert (site / "index.html").read_text(encoding="utf-8") == page
    assert not (site / "sitemap.xml").exists()


def test_page_without_cards_markers_is_fine(tmp_path):
    """Card blocks are optional; a page with none still builds."""
    page = PAGE.replace("<!-- jx:cards things -->\nstale\n<!-- /jx:cards -->\n", "")
    site = make_site(tmp_path, page=page)
    build.build(site)
    assert '<header class="jx-header">' in (site / "index.html").read_text(encoding="utf-8")


def test_unclosed_cards_marker_fails(tmp_path):
    """An opening jx:cards marker without its closer is an error, not silently skipped."""
    site = make_site(tmp_path, page=PAGE.replace("<!-- /jx:cards -->", ""))
    with pytest.raises(build.BuildError, match="unbalanced jx:cards"):
        build.build(site)


def test_empty_data_list_renders_empty_block(tmp_path):
    """An empty data file yields an empty (but still marked) block."""
    site = make_site(tmp_path, things=[])
    build.build(site)
    out = (site / "index.html").read_text(encoding="utf-8")
    assert "<!-- jx:cards things -->\n\n<!-- /jx:cards -->" in out


# ── Failure cases ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("things", "message"),
    [
        ([{"url": "https://x.com"}], "missing required 'title'"),
        ([{"title": "t"}], "missing required 'url'"),
        ([{"title": "t", "url": "javascript:alert(1)"}], "invalid url"),
        ([{"title": "t", "url": "/ok/", "tags": "nope"}], "'tags' must be a list"),
        ([{"title": "t", "url": "/ok/", "links": [{"label": "x", "url": "ftp://x"}]}], "invalid url"),
        ({"title": "t"}, "expected a JSON list"),
    ],
)
def test_bad_data_fails(tmp_path, things, message):
    """Invalid card data raises BuildError naming the problem."""
    site = make_site(tmp_path, things=things)
    with pytest.raises(build.BuildError, match=message):
        build.build(site)


def test_invalid_json_fails(tmp_path):
    """Malformed JSON is reported with the file name."""
    site = make_site(tmp_path)
    (site / "data" / "things.json").write_text("[{", encoding="utf-8")
    with pytest.raises(build.BuildError, match="things.json: invalid JSON"):
        build.build(site)


def test_main_returns_nonzero_on_error(tmp_path, monkeypatch, capsys):
    """The CLI exits 1 with a readable message instead of a traceback."""
    site = make_site(tmp_path, things=[{"title": "no url"}])
    monkeypatch.setattr(build, "ROOT", site)
    assert build.main([]) == 1
    assert "build failed" in capsys.readouterr().err


def test_chrome_has_home_link_and_no_footer_signup():
    """The nav links home first; only home and /newsletter carry the Substack embed, in their content."""
    header = (REPO / "partials" / "header.html").read_text(encoding="utf-8")
    footer = (REPO / "partials" / "footer.html").read_text(encoding="utf-8")
    assert '<nav class="jx-nav" aria-label="Site">\n    <a href="/">home</a>' in header
    assert "agicheckpoint.com/embed" not in footer and "jx-signup" not in footer
    with_embed = {p.relative_to(REPO).as_posix() for p in REPO.glob("**/index.html") if "agicheckpoint.com/embed" in p.read_text(encoding="utf-8")}
    assert with_embed == {"index.html", "newsletter/index.html"}


def test_hero_shows_the_name_once():
    """Home and /about head with "Javier • priv/acc" and don't repeat it on the line below."""
    for page in ("index.html", "about/index.html"):
        text = (REPO / page).read_text(encoding="utf-8")
        hero = text[text.index("$ whoami"):]
        hero = hero[: hero.index("</h1>") + 400]
        assert "Javier &bull; priv/acc</h1>" in hero, page
        assert hero.count("priv/acc") == 1, page
