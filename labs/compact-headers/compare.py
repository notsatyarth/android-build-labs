#!/usr/bin/env python3
"""Compare a compact-headers series with the original macOS series (Apple M1, JDK 26.0.1, n=4 per arm).
Usage: python3 -I compare.py RAWDIR
Absolute numbers differ between machines and are never compared. Per metric the conclusion is compared:
'lower' or 'higher' when the min-max ranges of the two arms do not overlap, 'no measurable difference'
when they overlap. Footprint is macOS phys_footprint on the Mac and VmRSS+VmSwap on Linux."""
import contextlib, io, os, re, runpy, statistics, sys, glob

RAW = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
# Per-run values of the macOS series (base B1-B4, coh C1-C4), from its published summary table.
MAC = {
    "wall": ([81, 83, 79, 66], [76, 68, 70, 75]),
    "g_rss": ([2284, 2585, 2527, 2873], [2384, 3429, 3335, 3680]),
    "g_fp": ([5209, 5173, 5056, 5180], [5163, 5199, 5194, 5189]),
    "k_rss_sum": ([2945, 2584, 2695, 2785], [2427, 2852, 2479, 2668]),
    "k_fp_sum": ([4227, 4002, 4127, 4065], [3604, 3647, 4328, 3601]),
    "g_heap_max": ([1741, 1817, 1919, 1863], [1627, 1806, 1543, 1689]),
    "g_live": ([372, 373, 381, 372], [348, 349, 341, 341]),
    "k_heap_max": ([797, 738, 831, 636], [724, 513, 793, 718]),
    "k_live": ([107, 107, 106, 109], [99, 96, 99, 95]),
    "g_gcs": ([43, 51, 45, 40], [44, 42, 39, 41]),
    "k_gcs": ([38, 40, 45, 35], [39, 36, 39, 38]),
}
LABEL = {"wall": "wall time, s", "g_rss": "Gradle daemon peak RSS, MB", "g_fp": "Gradle daemon peak footprint, MB",
         "k_rss_sum": "Kotlin daemons, sum of peak RSS, MB", "k_fp_sum": "Kotlin daemons, sum of peak footprint, MB",
         "g_heap_max": "Gradle heap, max after GC during build, MB", "g_live": "Gradle live set after full GC, MB",
         "k_heap_max": "Kotlin heap, max after GC during build, MB", "k_live": "Kotlin live set after full GC (all daemons), MB",
         "g_gcs": "GC pauses during build, Gradle", "k_gcs": "GC pauses during build, Kotlin"}


def concl(b, c):
    if max(c) < min(b):
        return "lower"
    if min(c) > max(b):
        return "higher"
    return "no measurable difference"


def fmt(v):
    return f"{statistics.median(v):g} ({min(v)}-{max(v)})"


with contextlib.redirect_stdout(io.StringIO()):
    g = runpy.run_path(os.path.join(HERE, "analyze.py"), run_name="analyze")
rows = g["rows"]
print("| metric | macOS base / coh, median (min-max) | macOS conclusion | CI base / coh, median (min-max) | CI change | CI conclusion | same? |")
print("|---|---|---|---|---|---|---|")
for k, (mb, mc) in MAC.items():
    b = [r[k] for r in rows if r["arm"] == "base" and r[k] is not None]
    c = [r[k] for r in rows if r["arm"] == "coh" and r[k] is not None]
    if not b or not c:
        print(f"| {LABEL[k]} | {fmt(mb)} / {fmt(mc)} | {concl(mb, mc)} | missing | | | **DIFFERENT** |")
        continue
    ch = (statistics.median(c) - statistics.median(b)) / statistics.median(b) * 100 if statistics.median(b) else 0
    same = concl(mb, mc) == concl(b, c)
    print(f"| {LABEL[k]} | {fmt(mb)} / {fmt(mc)} | {concl(mb, mc)} | {fmt(b)} / {fmt(c)} | {ch:+.1f}% | {concl(b, c)} | {'same' if same else '**DIFFERENT**'} |")
# Flag check: every coh daemon has the flag, no base daemon has it; Kotlin daemon count per run.
print()
print("| run | arm | Gradle daemons | Kotlin daemons | daemons with -XX:+UseCompactObjectHeaders | build |")
print("|---|---|---|---|---|---|")
for r in rows:
    cmd = open(f"{RAW}/{r['run']}.cmd").read() if os.path.exists(f"{RAW}/{r['run']}.cmd") else ""
    blocks = re.split(r"^== ", cmd, flags=re.M)[1:]
    gd = sum(b.startswith("GradleDaemon") for b in blocks)
    kd = sum(b.startswith("KotlinCompileDaemon") for b in blocks)
    fl = sum("-XX:+UseCompactObjectHeaders" in b for b in blocks)
    env = open(f"{RAW}/{r['run']}.env").read()
    print(f"| {r['run']} | {r['arm']} | {gd} | {kd} | {fl} | {env.strip().splitlines()[-1]} |")
