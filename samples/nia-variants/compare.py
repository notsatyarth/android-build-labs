#!/usr/bin/env python3
"""Compare a run of run.sh with the original macOS run (expected.json). Usage: compare.py OUT_DIR
Prints a markdown table: metric, macOS, CI, same/DIFFERENT. Timings are compared by direction and
range overlap only (different machines)."""
import json, os, re, statistics, sys
from collections import Counter

OUT = sys.argv[1]
E = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "expected.json")))
rd = lambda n: open(os.path.join(OUT, n + ".log"), errors="replace").read() if os.path.exists(os.path.join(OUT, n + ".log")) else ""
variants = lambda t: re.findall(r"^VARIANT (\S+) (\S+) (\S+)", t, re.M)
counts = lambda t: [(m[0], int(m[1])) for m in re.findall(r"^TASKCOUNT (\S+) (\d+)", t, re.M)]  # list: ":" appears for the root build and build-logic
dry = lambda t: len(re.findall(r"^:", t, re.M))
va, vk = variants(rd("print-all")), variants(rd("print-keep"))
ca, ck = counts(rd("count-all")), counts(rd("count-keep"))
ta, tk = rd("tasks-all"), rd("tasks-keep")
rows = []
def row(name, mac, ci, same=None):
    same = (mac == ci) if same is None else same
    rows.append(f"| {name} | {mac} | {ci} | {'same' if same else '**DIFFERENT**'} |")
row("variants, all", E["variants_all"], len(va))
row("variants by plugin, all", E["variants_all_by_plugin"], dict(sorted(Counter(v[1] for v in va).items())))
row("variants, demoDebug/debug kept", E["variants_keep"], len(vk))
row("projects counted", E["projects_counted"], len(ca))
row("registered tasks, all variants", E["tasks_all"], sum(v for _, v in ca))
row("registered tasks, kept", E["tasks_keep"], sum(v for _, v in ck))
row(":app tasks, all / kept", f"{E['app_tasks_all']} / {E['app_tasks_keep']}", f"{dict(ca).get(':app')} / {dict(ck).get(':app')}")
row(":app:assembleDemoDebug --dry-run tasks, all / kept", f"{E['dryrun_all']} / {E['dryrun_keep']}", f"{dry(rd('dryrun-all'))} / {dry(rd('dryrun-keep'))}")
row("tasks --all, all variants", "succeeds", "fails" if ("FAILURE:" in ta or "BUILD FAILED" in ta or not ta) else "succeeds")
ci_err = E["tasks_keep_error"] if E["tasks_keep_error"] in tk else ("fails, other error" if "BUILD FAILED" in tk else "succeeds")
row("tasks --all, kept", "fails: " + E["tasks_keep_error"], ci_err if ci_err != E["tasks_keep_error"] else "fails: " + ci_err)
ct = json.load(open(os.path.join(OUT, "config-time.json")))
def med(v): return f"{statistics.median(v):.2f} s ({min(v)}-{max(v)}), n={len(v)}"
mac_t, ci_t = E["config_time_s"], ct
def shape(t):
    a, k = t["all"], t["keep"]
    faster = statistics.median(k) < statistics.median(a)
    overlap = not (max(k) < min(a) or max(a) < min(k))
    return faster, overlap
mf, mo = shape(mac_t); cf, co = shape(ci_t)
row("help -q, all variants (median, range)", med(mac_t["all"]), med(ci_t["all"]), True)
row("help -q, kept (median, range)", med(mac_t["keep"]), med(ci_t["keep"]), True)
row("kept faster by median / ranges overlap", f"{mf} / {mo}", f"{cf} / {co}", (mf, mo) == (cf, co))
print("| metric | macOS (M1) | CI (x86 Linux runner) | same? |\n|---|---|---|---|")
print("\n".join(rows))
print("\nTimings are per machine; only the direction and the overlap are compared (absolute numbers rows are marked same by design).")
