#!/usr/bin/env python3
"""Per-build memory measures from probe-3 procwatch CSVs. Usage: memsum.py OUT_DIR PAIR
Reads OUT_DIR/sides.txt ("OLD NEW") and OUT_DIR/<side>-build<i>.csv (+ .csv.meta.json), writes OUT_DIR/mem-<PAIR>.json:
{"pair", "sides": [old, new], "builds": {side: [per-build dict, ...]}, "measures": {side: {measure: [v1..vN]}}}
Per build (one sample = one ps snapshot, every 0.5 s; RSS in MB as ps reports it):
  gradle_daemon_peak_mb      peak RSS of the Gradle daemon
  kotlin_daemon_<k>_peak_mb  peak RSS of the k-th Kotlin daemon, by order of first sighting
  gradle_workers_peak_mb     peak over samples of the summed RSS of all Gradle worker processes
  aapt2_peak_mb              peak over samples of the summed RSS of all AAPT2 daemons
  total_peak_mb, total_peak_at_s  peak summed RSS of every sampled process and when it occurred (s from start)
  kotlin_daemons             number of distinct Kotlin daemon processes seen
  wall_s                     seconds from start to the exit of ./gradlew (procwatch meta cmd_exit_s)"""
import csv, collections, glob, json, os, re, sys


def one(path):
    by_t = collections.OrderedDict(); first = {}
    for r in csv.DictReader(open(path)):
        t = float(r["elapsed_s"]); rss = int(r["rss_mb"])
        by_t.setdefault(t, []).append((r["pid"], r["kind"], rss))
        first.setdefault((r["pid"], r["kind"]), t)
    peak = collections.Counter()
    for rows in by_t.values():
        for pid, kind, rss in rows:
            peak[(pid, kind)] = max(peak[(pid, kind)], rss)
    m = {}
    gd = [v for (p, k), v in peak.items() if k == "gradle-daemon"]
    m["gradle_daemon_peak_mb"] = max(gd) if gd else None
    kds = sorted([pk for pk in peak if pk[1] == "kotlin-daemon"], key=lambda pk: first[pk])
    for i, pk in enumerate(kds, 1):
        m["kotlin_daemon_%d_peak_mb" % i] = peak[pk]
    m["kotlin_daemons"] = len(kds)
    sums = lambda kind: [sum(r for _, k, r in rows if k == kind) for rows in by_t.values()]
    m["gradle_workers_peak_mb"] = max(sums("gradle-worker") or [0])
    m["aapt2_peak_mb"] = max(sums("aapt2-daemon") or [0])
    tot = [(sum(r for _, _, r in rows), t) for t, rows in by_t.items()]
    best = max(tot) if tot else (None, None)
    m["total_peak_mb"], m["total_peak_at_s"] = best
    meta = path + ".meta.json"
    if os.path.exists(meta):
        mj = json.load(open(meta)); m["wall_s"] = mj.get("cmd_exit_s"); m["exit_code"] = mj.get("exit_code")
    m["other_kinds"] = sorted({k for (_, k) in peak} - {"gradle-daemon", "kotlin-daemon", "gradle-worker", "aapt2-daemon"})
    return m


def main(d, pair):
    old, new = open(os.path.join(d, "sides.txt")).read().split()
    builds = {}
    for s in (old, new):
        files = sorted(glob.glob(os.path.join(d, "%s-build*.csv" % s)), key=lambda p: int(re.search(r"build(\d+)\.csv$", p).group(1)))
        builds[s] = [dict(one(p), build=int(re.search(r"build(\d+)\.csv$", p).group(1))) for p in files]
    keys = sorted({k for s in builds for b in builds[s] for k in b if k not in ("build", "other_kinds", "exit_code")})
    measures = {s: {k: [b.get(k) for b in builds[s]] for k in keys} for s in builds}
    json.dump({"pair": pair, "sides": [old, new], "builds": builds, "measures": measures}, open(os.path.join(d, "mem-%s.json" % pair), "w"), indent=1)
    for s in (old, new):
        print("%s: %d builds" % (s, len(builds[s])))
        for k in keys:
            print("  %-26s %s" % (k, measures[s][k]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
