"""Differential test: patched feedparser vs the upstream-HEAD original.

Self-contained. From `../src/feedparser` (the patched source tree) it builds two
importable packages in a temp directory, using distinct top-level package names:
  - `fppatched`  = a copy of the patched source tree (has `_resolve_cache`)
  - `fporig`     = the same tree with `../patch.diff` reverse-applied, which
                   restores the upstream `resolve_uri` one-liner.
The two packages are imported side by side (each keeps its relative-import
structure intact) and resolve the same HTML; outputs must be byte-identical.
"""
import os
import random
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SRC_PKG = os.path.join(REPO, "src", "feedparser")
PATCH = os.path.join(REPO, "patch.diff")

_tmp = tempfile.mkdtemp(prefix="fpdiff_")
_pt_root = os.path.join(_tmp, "pt_root")
_og_root = os.path.join(_tmp, "og_root")
for root in (_pt_root, _og_root):
    # copy under the name `feedparser` so the patch path (feedparser/urls.py) matches
    shutil.copytree(SRC_PKG, os.path.join(root, "feedparser"))

# reverse-apply the patch on the original package, then rename the package dir
r = subprocess.run(
    ["patch", "-p1", "-R", os.path.join(_og_root, "feedparser", "urls.py")],
    input=open(PATCH, encoding="utf-8").read(),
    capture_output=True, text=True,
)
assert r.returncode == 0, f"reverse-apply failed: {r.stderr}"
os.rename(os.path.join(_og_root, "feedparser"), os.path.join(_og_root, "fporig"))
os.rename(os.path.join(_pt_root, "feedparser"), os.path.join(_pt_root, "fppatched"))

sys.path.insert(0, _og_root)
sys.path.insert(0, _pt_root)
import fporig.urls as orig      # noqa: E402
import fppatched.urls as patched  # noqa: E402


def resolve_impl(pkg, html, base, encoding="utf-8", type_="text/html"):
    p = pkg.RelativeURIResolver(base, encoding, type_)
    p.feed(html)
    return p.output()


BASES = ["http://example.com/", "https://sub.example.org/a/b/", "feed://feeds.x.net/t",
         "https://example.com/path dir with space/x", ""]
ATTRS = ["href", "src", "usemap", "data", "cite", "action", "poster", "classid",
         "longdesc", "codebase", "profile"]
TAGS = ["a", "img", "iframe", "object", "blockquote", "link", "script", "form",
        "ins", "source", "video"]
POOL = ["/cat/tech", "/cat/news", "/archive", "#top", "/about", "/feed/rss",
        "/p/2026", "../index", "./latest", "?page=2", "images/logo.png",
        "../../../up/", "mailto:a@b.c", "ftp://host/x", "//cdn.example/x.js"]


def one_doc():
    rnd = random.Random(4321)
    parts = []
    for _ in range(rnd.randint(0, 40)):
        tag = rnd.choice(TAGS)
        attr = rnd.choice(ATTRS)
        if rnd.random() < 0.7:
            val = rnd.choice(POOL)
        else:
            val = "/".join(rnd.choice(["a", "bb", "ccc", "d2"])
                           for _ in range(rnd.randint(1, 4)))
            val += rnd.choice(["/", "", ".html", "?x=1"])
        if rnd.random() < 0.1:
            val = " " + val + "\t"
        parts.append(f'<{tag} {attr}="{val}">x</{tag}>')
        if rnd.random() < 0.2:
            parts.append(f'<{rnd.choice(["p", "div", "span"])}>plain</{rnd.choice(["p", "div", "span"])}>')
    return "".join(parts)


def test_diff_byte_identical():
    rnd = random.Random(99)
    mismatches = 0
    total = 2000
    for i in range(total):
        base = rnd.choice(BASES)
        html = one_doc()
        a = resolve_impl(orig, html, base)
        b = resolve_impl(patched, html, base)
        if a != b:
            mismatches += 1
            if mismatches <= 5:
                print(f"[mismatch {i}] base={base!r}")
                print("ORIG :", a[:200])
                print("PATCH:", b[:200])
    assert mismatches == 0, f"{mismatches}/{total} mismatched"


def test_edges_identical():
    edges = [
        ("", "http://e.com/"),
        ("<a href='/x'>a</a>", "http://e.com/"),
        ("<a href=''></a>", "http://e.com/"),
        ("no tags at all here", "http://e.com/"),
        ("<a href='m&eacute;'></a>", "https://s.s/x"),
        ("<a href='/caf\u00e9/x'></a>", "https://e.com/"),
        ("<a href='#top'>", "http://e.com/"),
        ("<a href='  //example.com/x  '></a>", "http://e.com/"),
        ("<a href='javascript:alert(1)'></a>", "http://e.com/"),
        ("<img src=unquoted>", "http://e.com/"),
        ("<a href='a/../b'>", ""),
        ("<script src='/main.js'></script>", "https://e.com/"),
        ("<a href='data:text/html,x'>", "http://e.com/"),
        ("<x href='/weird'>", "http://e.com/"),
        ("<iframe src='//x/'>", "feed://f/"),
    ]
    for html, base in edges:
        a = resolve_impl(orig, html, base)
        b = resolve_impl(patched, html, base)
        assert a == b, (html, base, a, b)


def test_repeat_within_doc_equal():
    html = ("<a href='/same/page'>x</a><a href='/same/page'>y</a>"
            "<img src='/same/page'>") * 60
    for base in BASES:
        a = resolve_impl(orig, html, base)
        b = resolve_impl(patched, html, base)
        assert a == b, (base, a, b)