"""Daemon lifecycle: which processes outlive a nowinandroid build, and what ends them.
Usage: python3 -I compare.py DIR   (DIR holds, at any depth, a1.csv a2.csv a3.csv a4.csv a5.csv a6.csv from procwatch.py
--meta, each with its .meta.json; a5 also has a5.stop_at). Missing cells are reported as "no data".
Times are seconds after the build command exited ("build end"). "alive" = still sampled at the end of the tail.
Hypotheses come from the 2026-11-12 discussion; a verdict that disagrees is a finding, not a failure (exit code 0)."""
import csv, json, sys
from pathlib import Path

root = Path(sys.argv[1])
SETUP = {"a1": "default settings, 300 s tail", "a2": "second build right after a1 (warm), 30 s tail",
         "a3": "org.gradle.daemon.idletimeout=60000, 300 s tail", "a4": "kotlin.daemon.options autoshutdownIdleSeconds=60, 300 s tail",
         "a5": "./gradlew --stop 20 s after the build, 120 s tail", "a6": "--no-daemon, 120 s tail"}


def find(name):
    hits = sorted(root.rglob(name))
    return hits[0] if hits else None


def load(cell):
    p = find(f"{cell}.csv")
    if not p or not Path(str(p) + ".meta.json").exists():
        return None
    meta = json.load(open(str(p) + ".meta.json"))
    procs, totals = {}, {}
    for r in csv.DictReader(open(p)):
        t, key, rss = float(r["elapsed_s"]), (int(r["pid"]), r["kind"]), float(r["rss_mb"])
        d = procs.setdefault(key, {"first": t, "last": t, "peak": 0.0, "rss": []})
        d["last"] = t; d["peak"] = max(d["peak"], rss); d["rss"].append((t, rss))
        totals[t] = totals.get(t, 0.0) + rss
    end = meta["cmd_exit_s"]
    # End of sampling = command exit + tail (from the meta file), not the last sample with a process in it: when every
    # process has exited there are no rows, and the last rows would otherwise look "alive".
    tail_end = end + float(meta.get("tail_s", 6))
    for d in procs.values():
        d["alive"] = d["last"] >= tail_end - 2.5
        at = [rss for t, rss in d["rss"] if t <= end]
        d["rss_at_end"] = at[-1] if at else None
    marks = {}
    for m in ("build_end", "stop_at"):
        f = p.parent / f"{cell}.{m}"
        if f.exists():
            marks[m] = round(float(f.read_text().strip()) - meta["t0_epoch"], 1)
    def held(t0):  # total RSS at the last sample at or before t0
        return next((totals[t] for t in sorted(totals, reverse=True) if t <= t0), 0.0)
    return {"meta": meta, "procs": procs, "end": end, "tail_end": tail_end, "marks": marks,
            "rss_end": held(end), "rss_tail": sum(d["rss"][-1][1] for d in procs.values() if d["alive"]), "dir": p.parent}


cells = {c: load(c) for c in SETUP}
print("### Process lifetimes per cell (CI: x86 Linux runner; seconds relative to build end)\n")
for c, what in SETUP.items():
    d = cells[c]
    if not d:
        print(f"**{c}** ({what}): no data\n"); continue
    rel_end = d["marks"].get("build_end", d["end"])
    print(f"**{c}** ({what}). Command exit at {d['end']} s (exit code {d['meta']['exit_code']})"
          + (f"; build end {d['marks']['build_end']} s, --stop at {d['marks']['stop_at']} s" if d["marks"] else "")
          + f". Total RSS of sampled processes at build end {d['rss_end']:.0f} MB, at the end of the tail {d['rss_tail']:.0f} MB.\n")
    print("| kind | pid | started | last seen | status | RSS at build end MB | peak RSS MB |\n|---|---|---|---|---|---|---|")
    for (pid, kind), p in sorted(d["procs"].items(), key=lambda x: (x[0][1], x[1]["first"])):
        st = "alive at end of tail" if p["alive"] else f"gone after {p['last'] - rel_end:+.0f} s"
        r = f"{p['rss_at_end']:.0f}" if p["rss_at_end"] is not None else "-"
        print(f"| {kind} | {pid} | {p['first'] - rel_end:+.0f} | {p['last'] - rel_end:+.0f} | {st} | {r} | {p['peak']:.0f} |")
    kd = d["dir"] / f"{c}.kotlin-daemons.txt"
    if c == "a4" and kd.exists():
        txt = kd.read_text()
        print(f"\nKotlin daemon command lines contain autoshutdownIdleSeconds=60: {'yes' if 'autoshutdownIdleSeconds=60' in txt else 'no (or none alive at the end)'}")
    print()


def of(d, kind):
    return [(pid, p) for (pid, k), p in d["procs"].items() if k == kind] if d else []


checks = []


def check(name, cond, detail):
    checks.append((name, "no data" if cond is None else ("agrees" if cond else "DISAGREES"), detail))


a1, a2, a3, a4, a5, a6 = (cells[c] for c in SETUP)
if a1:
    cl = of(a1, "gradle-client")
    check("H1 the Gradle client (./gradlew JVM) ends with the build (a1)",
          all(p["last"] <= a1["end"] + 2 for _, p in cl) if cl else None, f"client last seen {[round(p['last'] - a1['end']) for _, p in cl]} s")
    gd, kds = of(a1, "gradle-daemon"), of(a1, "kotlin-daemon")
    check("H2 the Gradle daemon and every Kotlin daemon are still alive 300 s after the build (a1)",
          bool(gd) and bool(kds) and all(p["alive"] for _, p in gd + kds), f"{len(gd)} Gradle daemon(s), {len(kds)} Kotlin daemon(s); alive: {[k for (pid, k), p in a1['procs'].items() if p['alive']]}")
    others = [(k, round(p["last"] - a1["end"]), p["alive"]) for (pid, k), p in a1["procs"].items() if k not in ("gradle-daemon", "kotlin-daemon", "gradle-client")]
    check("H3 workers, AAPT2 and other helper processes end at or soon after the build (a1, within 30 s)",
          all(not alive and last <= 30 for _, last, alive in others) if others else None, f"(kind, last seen s, alive): {others}")
if a1 and a2:
    g1, g2 = {pid for pid, _ in of(a1, "gradle-daemon")}, {pid for pid, _ in of(a2, "gradle-daemon")}
    k1, k2 = {pid for pid, _ in of(a1, "kotlin-daemon")}, {pid for pid, _ in of(a2, "kotlin-daemon")}
    check("H4 a second build reuses the warm Gradle daemon and starts no new Kotlin daemon (a2)",
          g2 == g1 and k2 <= k1 and bool(k2), f"Gradle daemon a1 {sorted(g1)} a2 {sorted(g2)}; Kotlin a1 {sorted(k1)} a2 {sorted(k2)}")
if a3:
    gd = of(a3, "gradle-daemon")
    lasts = [round(p["last"] - a3["end"]) for _, p in gd]
    check("H5 with idletimeout=60000 the Gradle daemon ends 50 to 150 s after the build (a3)",
          bool(gd) and all(not p["alive"] and 50 <= p["last"] - a3["end"] <= 150 for _, p in gd), f"Gradle daemon last seen {lasts} s; Kotlin daemons alive at end: {sum(p['alive'] for _, p in of(a3, 'kotlin-daemon'))} of {len(of(a3, 'kotlin-daemon'))}")
if a4:
    kds, gd = of(a4, "kotlin-daemon"), of(a4, "gradle-daemon")
    # A Kotlin daemon idles from its own last compile, so the build-logic daemon can stop before the build ends.
    check("H6 with autoshutdownIdleSeconds=60 every Kotlin daemon ends by 150 s after the build while the Gradle daemon stays (a4)",
          bool(kds) and all(not p["alive"] and p["last"] - a4["end"] <= 150 for _, p in kds) and all(p["alive"] for _, p in gd),
          f"Kotlin daemons last seen {[round(p['last'] - a4['end']) for _, p in kds]} s; Gradle daemon alive: {[p['alive'] for _, p in gd]}")
if a5 and "stop_at" in a5["marks"]:
    s = a5["marks"]["stop_at"]
    gd, kds = of(a5, "gradle-daemon"), of(a5, "kotlin-daemon")
    check("H7 ./gradlew --stop ends the Gradle daemon within 15 s (a5)",
          bool(gd) and all(not p["alive"] and p["last"] <= s + 15 for _, p in gd), f"Gradle daemon last seen {[round(p['last'] - s) for _, p in gd]} s after --stop")
    check("H8 ./gradlew --stop also ends the Kotlin daemons within 60 s (a5)",
          bool(kds) and all(not p["alive"] and p["last"] <= s + 60 for _, p in kds), f"Kotlin daemons last seen {[round(p['last'] - s) for _, p in kds]} s after --stop; alive at end: {[p['alive'] for _, p in kds]}")
if a6:
    gd, kds = of(a6, "gradle-daemon"), of(a6, "kotlin-daemon")
    check("H9 with --no-daemon the (single-use) Gradle daemon ends with the build (a6, within 5 s)",
          bool(gd) and all(not p["alive"] and p["last"] <= a6["end"] + 5 for _, p in gd), f"Gradle daemon last seen {[round(p['last'] - a6['end']) for _, p in gd]} s")
    check("H10 with --no-daemon the Kotlin daemons also end within 60 s of the build (a6)",
          bool(kds) and all(not p["alive"] and p["last"] <= a6["end"] + 60 for _, p in kds), f"Kotlin daemons last seen {[round(p['last'] - a6['end']) for _, p in kds]} s; alive at end: {[p['alive'] for _, p in kds]}")

print("### Hypotheses\n\n| hypothesis | verdict | evidence |\n|---|---|---|")
for n, v, e in checks:
    print(f"| {n} | {v} | {e} |")
print(f"\n{sum(v == 'agrees' for _, v, _ in checks)} of {len(checks)} hypotheses agree; {sum(v == 'DISAGREES' for _, v, _ in checks)} disagree.")
