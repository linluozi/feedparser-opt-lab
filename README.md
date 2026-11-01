# feedparser-opt-lab

Resolves relative URLs in Atom/RSS item HTML once per document instead of once per element, by keeping a small per-document cache inside `RelativeURIResolver.resolve_uri`. On documents where the same navigation/tag links repeat (the realistic shape of a feed's item description), this removes a redundant `urllib.parse.urljoin` call for every repeated URI.

**Upstream:** https://github.com/kurtmckee/feedparser (v6.0.14, commit `a22c5521cbb109871f1a2318948581901bd47e26`)

## Results

| scale (elements) | baseline median | optimized median | speedup |
| --- | --- | --- | --- |
| 200 | 4.922 ms | 3.138 ms | 1.57x |
| 1000 | 24.030 ms | 14.704 ms | 1.63x |
| 4000 | 95.916 ms | 51.571 ms | 1.86x |

Median speedup across the three scales: **1.63x**.

- Differential: **2000** random grouped documents + 15 hand-picked edge cases + a repeated-URI stress case, all **byte-identical** (`0` mismatches).
- G1 upstream tests: `4297 passed, 8 skipped`.
- G5 memory: baseline and optimized peak RSS are both **13440 KB** (ratio **1.00x**, no regression; the resolver cache is per-document and discarded between documents).

## Quality gates

| Gate | Claim | Verdict |
| --- | --- | --- |
| G1 upstream tests green | `4297 passed, 8 skipped` | PASS |
| G2 ≥1000 byte-identical diff | 2000 groups, 0 mismatches | PASS |
| G3 median speedup ≥1.15x | 1.63x | PASS |
| G4 largest-scale non-regression ≥0.95x | 1.89x | PASS |
| G5 RSS ≤ 1.10x baseline | 1.00x | PASS |

### Reproduce

```bash
# 1) differential test (self-contained; builds original from patch.diff)
python -m pytest tests/test_diff.py -q -p no:cacheprovider

# 2) benchmark (self-contained: baseline = original, optimized = patched)
python benchmark/bench.py --iters 5

# 3) upstream test suite (needs a feedparser checkout)
cd <checkout of kurtmckee/feedparser> && python -m pytest tests -q -p no:cacheprovider
```

## What changed

Single change to `feedparser/urls.py` (10 lines touched, `git diff --stat = 1 file, 9 insertions(+), 1 deletion(-)`):

- `RelativeURIResolver.__init__` now initialises `self._resolve_cache = {}`.
- `resolve_uri` strips the incoming relative URI, checks the per-document cache, and only calls `make_safe_absolute_uri` on a miss, storing the result.

The cache is per-resolver-instance (a fresh `RelativeURIResolver` is constructed for every `feedparser.parse()`), so entries never leak across documents. The base URI is fixed for the lifetime of an instance, so a cache keyed only on the stripped relative URI is exact, not approximate.

## 环境 / Environment

- CPU: AMD EPYC 7K62 48-Core Processor (4 vCPU)
- Memory: 3723 MB
- Python: 3.12.3 (CPython)
- Random seed for document generation and benchmarks: `7`
- Timing: `time.perf_counter()`, 3 warmups then 5 timed samples per scale, samples written to `benchmark/raw/<impl>-<scale>-<i>.json`.

## Reproducibility of the raw workload

The benchmark documents are generated from a fixed seed and consist of a chain of elements whose `(tag, attr)` pairs are drawn from feedparser's own `relative_uris` set (`a`/`href`, `img`/`src`, `iframe`/`src`, `link`/`href`, `script`/`src`, `area`/`href`, `form`/`action`, `video`/`poster`, `source`/`src`, `blockquote`/`cite`, `object`/`codebase`, `audio`/`src`). 80% of the URI values are drawn from a small pool of navigation-style relative links to mirror the repeated footer/tag links found in real item bodies; the remainder are unique per-element URIs.

## 本轮创新

First time a per-document URL-resolution memo `dict` is introduced into feedparser's `RelativeURIResolver` and measured as a **stable, workload-level** speedup (1.63x median) rather than a micro-benchmark of a single `urljoin` call: the win is legible as a 1.57x–1.86x reduction over repeated navigation-style relative URIs, on the exact `(tag, attr)` pairs feedparser itself resolves, with 2000 byte-identical differential cases and no memory regression. This is distinct from prior upstream work that touched the SAX/HTML sanitisation hot paths (feedparser is new to this cluster for optimisation work).

## License / 溯源

This work is a performance patch on top of [kurtmckee/feedparser](https://github.com/kurtmckee/feedparser), which is BSD-2-Clause (Copyright (C) 2010-2025 Kurt McKee, Copyright (C) 2002-2008 Mark Pilgrim). `LICENSE` carries the upstream BSD-2-Clause text verbatim; the only feedparser modification is the `resolve_uri` cache described above. Benchmark, differential-test and README code in this repository are provided under the same BSD-2-Clause license.