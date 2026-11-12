#!/usr/bin/env python3
"""Per-process table from procwatch --cpu CSVs. Usage: summarize.py OUT_DIR
A process is labelled kind + order of first sighting (kotlin-daemon-1 is the one seen first). Wall = first to last sighting
(daemons outlive the build, so for them it is the build span plus procwatch's 6 s tail). CPU = last minus first cumulative CPU.
Median across runs; processes seen in fewer runs are listed with the run count."""
import csv, glob, statistics, sys, collections, os

def one(path):
    d = collections.OrderedDict()
    for r in csv.DictReader(open(path)):
        d.setdefault((r["pid"], r["kind"]), []).append(r)
    seen = collections.Counter(); out = {}
    for (pid, kind), rs in sorted(d.items(), key=lambda x: float(x[1][0]["elapsed_s"])):
        seen[kind] += 1; cpu = [float(r["cpu_s"]) for r in rs if r.get("cpu_s", "") != ""]
        out["%s-%d" % (kind, seen[kind])] = dict(start=float(rs[0]["elapsed_s"]), wall=float(rs[-1]["elapsed_s"]) - float(rs[0]["elapsed_s"]),
                                                  cpu=(cpu[-1] - cpu[0]) if cpu else float("nan"), rss=max(int(r["rss_mb"]) for r in rs))
    return out

def main(d):
    runs = [one(p) for p in sorted(glob.glob(os.path.join(d, "run*.csv")))]
    labels = sorted({k for r in runs for k in r})
    print("| Process | Runs | Start (s) | Wall (s) | CPU (s) | CPU / wall | Peak RSS (MB) |\n|---|---|---|---|---|---|---|")
    for k in labels:
        rs = [r[k] for r in runs if k in r]; m = lambda f: statistics.median(x[f] for x in rs)
        print("| %s | %d of %d | %.1f | %.1f | %.1f | %.2f | %d |" % (k, len(rs), len(runs), m("start"), m("wall"), m("cpu"), m("cpu") / m("wall") if m("wall") else float("nan"), m("rss")))
    tot = [sum(v["cpu"] for v in r.values()) for r in runs]
    print("\nSum of CPU over all sampled processes, per run (s): " + ", ".join("%.0f" % t for t in tot))

if __name__ == "__main__":
    main(sys.argv[1])
