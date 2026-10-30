#!/usr/bin/env python3
"""Summarise the compact object headers lab. Run: python3 -I analyze.py RAWDIR
Per run: build wall time, peak RSS and peak phys_footprint (macOS; VmRSS+VmSwap on Linux) per daemon kind (sampled every ~1 s),
G1 heap occupancy from -Xlog:gc (max after-GC value during the build, number of GC pauses),
and the live set after the post-build full GC (jcmd GC.run, logged as 'Pause Full (Diagnostic Command)')."""
import csv, glob, os, re, statistics, sys

RAW = sys.argv[1]
RUNS = ["B1", "B2", "B3", "B4", "C1", "C2", "C3", "C4"]
GC = re.compile(r"GC\(\d+\) Pause (.*?) (\d+)M->(\d+)M\((\d+)M\)")


def wall(label):
    t = open(f"{RAW}/{label}.log").read()
    m = re.search(r"BUILD SUCCESSFUL in (?:(\d+)m)? ?(?:(\d+)s)?", t)
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0) if m else None


def samples(label):
    peak = {}
    with open(f"{RAW}/{label}.csv") as f:
        for r in csv.DictReader(f):
            k = (r["kind"], int(r["pid"]))
            rss, fp = int(r["rss_mb"]), int(r["footprint_mb"] or 0)
            a = peak.setdefault(k, [0, 0])
            a[0], a[1] = max(a[0], rss), max(a[1], fp)
    return peak


def gclogs(label, who):
    out = []
    for p in sorted(glob.glob(f"{RAW}/{label}.{who}-gc-*.log")):
        build_after, live, n = [], None, 0
        for line in open(p):
            m = GC.search(line)
            if not m:
                continue
            kind, before, after = m.group(1), int(m.group(2)), int(m.group(3))
            if "Diagnostic" in kind:
                live = after
            else:
                n += 1
                if "Remark" not in kind and "Cleanup" not in kind:
                    build_after.append(after)
        out.append(dict(pid=re.search(r"-(\d+)\.log$", p).group(1), max_after=max(build_after or [0]), live=live, pauses=n))
    return out


rows = []
for L in RUNS:
    if not os.path.exists(f"{RAW}/{L}.log"):
        continue
    pk = samples(L)
    gd = [v for (k, _), v in pk.items() if k == "gradle-daemon"]
    kd = sorted([v for (k, _), v in pk.items() if k == "kotlin-daemon"], key=lambda v: -v[0])
    gg, kg = gclogs(L, "gradle"), gclogs(L, "kotlin")
    rows.append(dict(
        run=L, arm="coh" if L.startswith("C") else "base", wall=wall(L),
        g_rss=max(v[0] for v in gd), g_fp=max(v[1] for v in gd),
        k_rss=kd[0][0] if kd else 0, k_fp=max(v[1] for v in kd) if kd else 0, k_n=len(kd),
        k_rss_sum=sum(v[0] for v in kd), k_fp_sum=sum(v[1] for v in kd),
        g_heap_max=max(g["max_after"] for g in gg), g_live=gg[0]["live"] if gg else None, g_gcs=sum(g["pauses"] for g in gg),
        k_heap_max=max((g["max_after"] for g in kg), default=0), k_live=sum(g["live"] or 0 for g in kg), k_gcs=sum(g["pauses"] for g in kg),
        swap=re.search(r"(?:used = |swap_used=)([\d.]+)M", open(f"{RAW}/{L}.env").read()).group(1),
    ))

cols = ["run", "arm", "wall", "g_rss", "g_fp", "k_n", "k_rss", "k_rss_sum", "k_fp_sum", "g_heap_max", "g_live", "g_gcs", "k_heap_max", "k_live", "k_gcs", "swap"]
print("| " + " | ".join(cols) + " |")
print("|" + "---|" * len(cols))
for r in rows:
    print("| " + " | ".join(str(r[c]) for c in cols) + " |")
print()
print("| metric | base median (min-max) | coh median (min-max) | median change |")
print("|---|---|---|---|")
for c in cols[2:-1]:
    if c == "k_n":
        continue
    b = [r[c] for r in rows if r["arm"] == "base" and r[c] is not None]
    k = [r[c] for r in rows if r["arm"] == "coh" and r[c] is not None]
    if not b or not k:
        continue
    mb, mk = statistics.median(b), statistics.median(k)
    ch = f"{(mk - mb) / mb * 100:+.1f}%" if mb else ""
    print(f"| {c} | {mb:g} ({min(b)}-{max(b)}) | {mk:g} ({min(k)}-{max(k)}) | {ch} |")
