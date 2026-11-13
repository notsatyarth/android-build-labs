#!/usr/bin/env python3
"""Kotlin DSL vs Groovy DSL scripts. Usage: compare.py OUT_DIR  (OUT_DIR holds kts-<run>/ and groovy-<run>/ from run.sh)
Per step: median wall time (s, from procwatch cmd_exit_s), per-variant list, and for the clean build the number of distinct
Kotlin daemon pids, peak RSS of each process kind and the peak total RSS. Same machine only; this is not a CI comparison."""
import csv, json, statistics as st, sys
from pathlib import Path
root = Path(sys.argv[1])
STEPS = {"s1": "help, cold script cache", "s2": "clean assembleDemoDebug", "s3": "no-op, config cache hit", "s4": "no-op, config cache deleted (full configuration)"}
def load(d, step):
    p = d / f"{step}.csv"
    if not p.exists() or not Path(str(p) + ".meta.json").exists(): return None
    meta = json.load(open(str(p) + ".meta.json"))
    kinds, pids, tot = {}, {}, {}
    for r in csv.DictReader(open(p)):
        t, k, rss = float(r["elapsed_s"]), r["kind"], float(r["rss_mb"])
        kinds[k] = max(kinds.get(k, 0), rss); pids.setdefault(k, set()).add(r["pid"]); tot[t] = tot.get(t, 0) + rss
    return {"wall": meta["cmd_exit_s"], "ok": meta.get("exit_code") == 0, "kinds": kinds, "kd": len(pids.get("kotlin-daemon", ())), "peak": max(tot.values()) if tot else 0}
res = {v: {s: [] for s in STEPS} for v in ("kts", "groovy")}
for d in sorted(root.glob("*-*")):
    v = d.name.split("-")[0]
    if v in res:
        for s in STEPS:
            r = load(d, s)
            if r: res[v][s].append(r)
for s, name in STEPS.items():
    print(f"\n== {s} {name}")
    for v in res:
        rs = res[v][s]
        if not rs: print(f"  {v:7s} no data"); continue
        w = [r["wall"] for r in rs]
        print(f"  {v:7s} n={len(rs)} wall median {st.median(w):7.1f}s  runs {[round(x,1) for x in w]}  failed {sum(not r['ok'] for r in rs)}  "
              f"kotlin daemons {[r['kd'] for r in rs]}  peak total RSS {[round(r['peak']) for r in rs]} MB")
print("\n== peak RSS per process kind, clean build (MB, max over runs)")
for v in res:
    k = {}
    for r in res[v]["s2"]:
        for a, b in r["kinds"].items(): k[a] = max(k.get(a, 0), b)
    print(f"  {v:7s} " + ", ".join(f"{a} {round(b)}" for a, b in sorted(k.items())))
