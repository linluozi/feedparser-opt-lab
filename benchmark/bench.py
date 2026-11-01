#!/usr/bin/env python3
"""Benchmark feedparser.resolve_relative_uris across scales.

Self-contained: it builds both sides from `../src/feedparser`.
  - optimized = a copy of ../src/feedparser (carries the _resolve_cache)
  - baseline  = ../src/feedparser with ../patch.diff reverse-applied (upstream)

Both packages are imported side by side and each scale's documents (generated
from a fixed seed so both sides see identical input) are timed with
time.perf_counter(). Raw samples are written to benchmark/raw/<impl>-<scale>-<i>.json.

Usage:
    python benchmark/bench.py [--iters 5]
"""
import sys, os, json, time, random, shutil, subprocess, tempfile, argparse

p = argparse.ArgumentParser()
p.add_argument("--iters", type=int, default=5)
args = p.parse_args()

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SRC_PKG = os.path.join(REPO, "src", "feedparser")
PATCH = os.path.join(REPO, "patch.diff")

tmp = tempfile.mkdtemp(prefix="fpbench_")
base_root = os.path.join(tmp, "base_root")
opt_root = os.path.join(tmp, "opt_root")
for root in (base_root, opt_root):
    shutil.copytree(SRC_PKG, os.path.join(root, "feedparser"))
# reverse-apply to make the baseline the original
r = subprocess.run(["patch", "-p1", "-R", os.path.join(base_root, "feedparser", "urls.py")],
                   input=open(PATCH, encoding="utf-8").read(), capture_output=True, text=True)
assert r.returncode == 0, f"reverse-apply failed: {r.stderr}"
os.rename(os.path.join(base_root, "feedparser"), os.path.join(base_root, "baselib"))
os.rename(os.path.join(opt_root, "feedparser"), os.path.join(opt_root, "optlib"))

sys.path.insert(0, base_root)
sys.path.insert(0, opt_root)
import baselib.urls as base_mod     # noqa: E402
import optlib.urls as opt_mod       # noqa: E402
RESOLVERS = {"baseline": base_mod, "optimized": opt_mod}

BASE = "http://example.com/"
RESOLVING = [("a", "href"), ("img", "src"), ("iframe", "src"), ("link", "href"),
             ("script", "src"), ("area", "href"), ("form", "action"),
             ("video", "poster"), ("source", "src"), ("blockquote", "cite"),
             ("object", "codebase"), ("audio", "src")]
POOL = ["/category/tech", "/category/news", "/archive", "#top", "/about", "/feed",
        "/tags/python", "/p/2026", "../index", "./latest", "/doc/guide", "/sitemap"]


def make_doc(n_links):
    rnd = random.Random(7)
    out = []
    for _ in range(n_links):
        tag, attr = rnd.choice(RESOLVING)
        if rnd.random() < 0.8:
            val = rnd.choice(POOL)
        else:
            val = "/item/" + str(rnd.randint(1, 200))
        out.append(f'<{tag} {attr}="{val}"/>')
    return "".join(out)


SCALES = [200, 1000, 4000]
OUTDIR = os.path.join(HERE, "raw")
os.makedirs(OUTDIR, exist_ok=True)


def timing(mod, doc, impl, scale, n):
    for _ in range(3):
        pkg = mod.RelativeURIResolver(BASE, "utf-8", "text/html")
        pkg.feed(doc)
    samples = []
    for i in range(n):
        t0 = time.perf_counter()
        pkg = mod.RelativeURIResolver(BASE, "utf-8", "text/html")
        pkg.feed(doc)
        d = time.perf_counter() - t0
        samples.append(d)
        with open(os.path.join(OUTDIR, f"{impl}-{scale}-{i}.json"), "w") as f:
            json.dump({"impl": impl, "scale": scale, "i": i,
                       "seconds": d, "seed": 7}, f)
    return samples


all_results = {}
# deterministic: both impls share identical docs
docs = {scale: make_doc(scale) for scale in SCALES}
for impl in ("baseline", "optimized"):
    results = {}
    for scale in SCALES:
        samples = timing(RESOLVERS[impl], docs[scale], impl, scale, args.iters)
        s = sorted(samples)
        n = len(s)
        results[scale] = {"median": s[n // 2], "p25": s[(n * 1) // 4], "p75": s[(n * 3) // 4]}
        print(f"{impl} scale={scale} median={s[n//2]*1000:.3f}ms p25={s[n//4]*1000:.3f} p75={s[n*3//4]*1000:.3f}")
    all_results[impl] = results
print(json.dumps(all_results))