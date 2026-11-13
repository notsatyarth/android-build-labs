"""One vs two Kotlin daemons: per-cell medians and the hypotheses from the 2026-11-12 discussion.
Usage: python3 -I compare.py DIR   (DIR holds, at any depth, one directory per cell written by run.sh: setup.txt, runN.csv with
.meta.json, gc/kd-<pid>.log). Medians over the builds of a cell; [min-max] in brackets. A build counts only if it succeeded
and its Kotlin daemon count is the one the cell intends (1 for d1, 2 for d2 and shipped). Verdicts that disagree are findings.
Metrics per build:
  wall          seconds from start to the exit of ./gradlew
  kd            distinct Kotlin daemon pids
  peak total    highest sum of RSS over all sampled processes (Gradle client and daemon, Kotlin daemons, workers, AAPT2)
  peak kotlin   highest sum of RSS over the Kotlin daemons in one sample
  kotlin held   sum of Kotlin daemon RSS at the last sample before the build ended (memory held once the build is done)
  committed     sum over Kotlin daemons of the committed heap after their last GC (from -Xlog:gc, the number in brackets)
  GC pause      sum over Kotlin daemons of all GC pause times (ms), and the number of pauses
  kotlin CPU    sum over Kotlin daemons of CPU seconds"""
import csv, json, re, statistics, sys
from pathlib import Path

root = Path(sys.argv[1])
ORDER = ["d1_lo_2g", "d2_lo_2g", "d1_hi_2g", "d2_hi_2g", "d1_lo_4g", "d2_lo_4g", "d1_hi_4g", "d2_hi_4g", "shipped_4g"]
UNIT = {"M": 1, "G": 1024, "K": 1 / 1024}
PAUSE = re.compile(r"Pause .*?(\d+)([KMG])->(\d+)([KMG])\((\d+)([KMG])\)\s+([\d.]+)ms")


def gc_stats(log):
    pauses, committed = [], None
    for line in log.read_text(errors="replace").splitlines():
        m = PAUSE.search(line)
        if m:
            pauses.append(float(m.group(7)))
            committed = float(m.group(5)) * UNIT[m.group(6)]
    return sum(pauses), len(pauses), committed


def build(csvp, gcdir):
    meta_p = Path(str(csvp) + ".meta.json")
    log = csvp.with_suffix(".log")
    if not meta_p.exists() or not log.exists() or "BUILD SUCCESSFUL" not in log.read_text(errors="replace"):
        return None
    meta = json.load(open(meta_p))
    end = meta["cmd_exit_s"]
    tot, kot, kpids, cpu, at_end = {}, {}, set(), {}, {}
    for r in csv.DictReader(open(csvp)):
        t, rss = float(r["elapsed_s"]), float(r["rss_mb"])
        tot[t] = tot.get(t, 0) + rss
        if r["kind"] == "kotlin-daemon":
            pid = r["pid"]; kpids.add(pid)
            kot[t] = kot.get(t, 0) + rss
            c = float(r["cpu_s"]) if r.get("cpu_s") not in (None, "") else None
            if c is not None:
                lo, hi = cpu.get(pid, (c, c)); cpu[pid] = (min(lo, c), max(hi, c))
    last_t = max((t for t in tot if t <= end), default=None)
    held = kot.get(last_t, 0) if last_t is not None else 0
    gp, gn, com = 0.0, 0, 0.0
    for pid in kpids:
        f = gcdir / f"kd-{pid}.log"
        if f.exists():
            p, n, c = gc_stats(f); gp += p; gn += n; com += c or 0
    return {"wall": end, "kd": len(kpids), "peak_total": max(tot.values(), default=0), "peak_kotlin": max(kot.values(), default=0),
            "held": held, "committed": com, "gc_ms": gp, "gc_n": gn, "kcpu": sum(hi - lo for lo, hi in cpu.values())}


cells = {}
for setup in root.rglob("setup.txt"):
    first = setup.read_text().splitlines()[0]
    cell = first.lstrip("# ").strip()
    want = 1 if cell.startswith("d1") else 2
    rows, rejected = [], []
    for c in sorted(setup.parent.glob("run*.csv"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0)):
        b = build(c, setup.parent / "gc")
        if b and b["kd"] == want:
            rows.append(b)
        else:
            rejected.append((c.stem, "failed or incomplete" if not b else f"{b['kd']} Kotlin daemons"))
    cells[cell] = {"rows": rows, "rejected": rejected, "want": want}


def med(cell, k):
    v = [r[k] for r in cells.get(cell, {}).get("rows", [])]
    return round(statistics.median(v), 1) if v else None


def fmt(cell, k, nd=0):
    v = [r[k] for r in cells.get(cell, {}).get("rows", [])]
    if not v:
        return "-"
    f = lambda x: f"{x:.{nd}f}"
    return f"{f(statistics.median(v))} [{f(min(v))}-{f(max(v))}]"


print("### One vs two Kotlin daemons (CI: x86 Linux runner; medians [min-max])\n")
print("| cell | builds used | Kotlin daemons | wall s | peak total RSS MB | peak Kotlin RSS MB | Kotlin RSS held at build end MB | Kotlin committed heap MB | Kotlin GC pause ms | GC pauses | Kotlin CPU s |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for c in ORDER:
    d = cells.get(c)
    if not d:
        print(f"| {c} | no data |" + " |" * 9); continue
    print(f"| {c} | {len(d['rows'])} | {d['want']} | {fmt(c, 'wall', 1)} | {fmt(c, 'peak_total')} | {fmt(c, 'peak_kotlin')} | {fmt(c, 'held')} | {fmt(c, 'committed')} | {fmt(c, 'gc_ms')} | {fmt(c, 'gc_n')} | {fmt(c, 'kcpu', 1)} |")
rej = [(c, r) for c in ORDER if c in cells for r in cells[c]["rejected"]]
if rej:
    print("\nBuilds not used: " + "; ".join(f"{c} {s}: {why}" for c, (s, why) in rej))

checks = []


def check(name, a, b, cond, detail):
    ok = None if a is None or b is None else cond(a, b)
    checks.append((name, "no data" if ok is None else ("agrees" if ok else "DISAGREES"), detail))


def spread(cell, k):
    v = [r[k] for r in cells.get(cell, {}).get("rows", [])]
    return (max(v) - min(v)) if v else 0


for x in ("2g", "4g"):
    xmb = 2048 if x == "2g" else 4096
    d1h, d2h, d1l, d2l = med(f"d1_hi_{x}", "held"), med(f"d2_hi_{x}", "held"), med(f"d1_lo_{x}", "held"), med(f"d2_lo_{x}", "held")
    check(f"H1 Xms = Xmx = {x}: two daemons hold more Kotlin RSS at build end than one (by at least 512 MB)", d1h, d2h,
          lambda a, b: b - a >= 512, f"one {d1h} MB, two {d2h} MB")
    check(f"H2 Xmx {x}: the extra memory held by a second daemon is smaller with Xms 256m than with Xms = Xmx",
          None if None in (d1l, d2l) else d2l - d1l, None if None in (d1h, d2h) else d2h - d1h,
          lambda lo, hi: lo < hi, f"extra with Xms 256m: {None if None in (d1l, d2l) else round(d2l - d1l)} MB; with Xms = Xmx: {None if None in (d1h, d2h) else round(d2h - d1h)} MB")
    for xs in ("lo", "hi"):
        g1, g2 = med(f"d1_{xs}_{x}", "gc_ms"), med(f"d2_{xs}_{x}", "gc_ms")
        check(f"H3 Xms {'256m' if xs == 'lo' else '= Xmx'}, Xmx {x}: one daemon spends at least as much time in GC pauses as two", g1, g2,
              lambda a, b: a >= b, f"one {g1} ms, two {g2} ms")
        w1, w2 = med(f"d1_{xs}_{x}", "wall"), med(f"d2_{xs}_{x}", "wall")
        noise = max(spread(f"d1_{xs}_{x}", "wall"), spread(f"d2_{xs}_{x}", "wall"))
        check(f"H4 Xms {'256m' if xs == 'lo' else '= Xmx'}, Xmx {x}: wall time of one vs two daemons differs by less than the run-to-run spread", w1, w2,
              lambda a, b: abs(a - b) < noise, f"one {w1} s, two {w2} s, largest spread {round(noise, 1)} s")
        p1, p2 = med(f"d1_{xs}_{x}", "peak_total"), med(f"d2_{xs}_{x}", "peak_total")
        check(f"H5 Xms {'256m' if xs == 'lo' else '= Xmx'}, Xmx {x}: two daemons raise the peak total RSS by less than 10%", p1, p2,
              lambda a, b: b < a * 1.10, f"one {p1} MB, two {p2} MB")
s, d = med("shipped_4g", "wall"), med("d2_hi_4g", "wall")
check("H6 as shipped (Kotlin 2.3.0 + 2.4.0) vs d2_hi_4g (2.4.0 only, also two daemons): wall time within the run-to-run spread", s, d,
      lambda a, b: abs(a - b) < max(spread("shipped_4g", "wall"), spread("d2_hi_4g", "wall")), f"shipped {s} s, d2_hi_4g {d} s")

print("\n### Hypotheses\n\n| hypothesis | verdict | evidence |\n|---|---|---|")
for n, v, e in checks:
    print(f"| {n} | {v} | {e} |")
print(f"\n{sum(v == 'agrees' for _, v, _ in checks)} of {len(checks)} hypotheses agree; {sum(v == 'DISAGREES' for _, v, _ in checks)} disagree; {sum(v == 'no data' for _, v, _ in checks)} without data.")
