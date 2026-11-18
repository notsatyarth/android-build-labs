#!/usr/bin/env python3
"""Probe 3 analysis: old versus new per measure, with a bootstrap interval for the percent change of medians.

Usage: analyse.py OUT.json [--time PAIR AGG.json OLD NEW]... [--mem MEM.json]... [--meta KEY VALUE]...
  --time  gradle-profiler agg.json (labs/old-vs-new/agg.py shape: {side: {"scenario|metric": [seconds per measured iteration]}})
  --mem   mem-<PAIR>.json from memsum.py (5 builds per side); every memory measure is analysed twice: all builds, and
          excluding build 1 of each side (build 1 on a fresh runner can be a cold outlier; it stays in the raw data).

Method (printed with the table): for each measure, old median, new median, percent change of medians
100 * (median(new) - median(old)) / median(old), min and max per side, and a 95 % percentile bootstrap interval of that
percent change: both sides resampled independently with replacement, 10,000 resamples, random.Random(20261120) seeded
afresh per measure. "measurable" = the interval excludes 0. Numbers printed to 3 significant figures; OUT.json keeps
full precision."""
import json, math, random, statistics as st, sys

B, SEED = 10000, 20261120
METHOD = ("percent change of medians, 100*(median(new)-median(old))/median(old); 95%% percentile bootstrap interval, "
          "each side resampled independently with replacement, %d resamples, seed %d per measure; "
          "measurable = interval excludes 0" % (B, SEED))


def pct(o, n):
    mo = st.median(o)
    return 100.0 * (st.median(n) - mo) / mo if mo else float("nan")


def boot(o, n):
    r = random.Random(SEED)
    q = sorted(pct([r.choice(o) for _ in o], [r.choice(n) for _ in n]) for _ in range(B))
    return q[int(0.025 * B) - 1], q[int(0.975 * B)]


def sig(x, k=3):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    if x == 0:
        return "0"
    d = k - int(math.floor(math.log10(abs(x)))) - 1
    r = round(x, d)
    return ("%." + str(max(d, 0)) + "f") % r


def row(pair, kind, measure, unit, o, n, subset):
    o = [float(v) for v in o if v is not None]; n = [float(v) for v in n if v is not None]
    rec = dict(pair=pair, kind=kind, measure=measure, unit=unit, subset=subset, n_old=len(o), n_new=len(n), old=o, new=n)
    if len(o) < 2 or len(n) < 2:
        rec.update(note="fewer than 2 values on a side; no interval")
        if o: rec.update(old_median=st.median(o), old_min=min(o), old_max=max(o))
        if n: rec.update(new_median=st.median(n), new_min=min(n), new_max=max(n))
        return rec
    lo, hi = boot(o, n)
    rec.update(old_median=st.median(o), new_median=st.median(n), pct_change=pct(o, n), ci_low=lo, ci_high=hi,
               old_min=min(o), old_max=max(o), new_min=min(n), new_max=max(n), measurable=(lo > 0 or hi < 0))
    return rec


def main():
    a = sys.argv[1:]
    out = a.pop(0); recs = []; meta = {"method": METHOD, "pairs": {}}
    while a:
        opt = a.pop(0)
        if opt == "--time":
            pair, path, old, new = a.pop(0), a.pop(0), a.pop(0), a.pop(0)
            agg = json.load(open(path)); meta["pairs"].setdefault(pair, {})["time"] = {"source": path, "old": old, "new": new}
            for key in sorted(agg[old]):
                if key in agg[new]:
                    recs.append(row(pair, "time", key, "s", agg[old][key], agg[new][key], "measured iterations"))
        elif opt == "--mem":
            path = a.pop(0); m = json.load(open(path)); pair = m["pair"]; old, new = m["sides"]
            meta["pairs"].setdefault(pair, {})["memory"] = {"source": path, "old": old, "new": new}
            for key in sorted(set(m["measures"][old]) | set(m["measures"][new])):
                o, n = m["measures"][old].get(key, []), m["measures"][new].get(key, [])
                unit = "s" if key.endswith("_s") else ("count" if key == "kotlin_daemons" else "MB")
                recs.append(row(pair, "memory", key, unit, o, n, "all builds"))
                recs.append(row(pair, "memory", key, unit, o[1:], n[1:], "excluding build 1"))
        elif opt == "--meta":
            k = a.pop(0); meta[k] = a.pop(0)
        else:
            sys.exit("unknown option " + opt)
    json.dump({"meta": meta, "rows": recs}, open(out, "w"), indent=1)
    print("Method: " + METHOD + "\n")
    print("| pair | kind | measure | subset | n old/new | old median | new median | change | 95% interval | old min-max | new min-max | measurable |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in recs:
        r = dict(r, measure=r["measure"].replace("|", " / "))
        if "pct_change" not in r:
            print("| %s | %s | %s (%s) | %s | %d/%d | %s | %s | - | - | - | - | %s |" % (r["pair"], r["kind"], r["measure"], r["unit"], r["subset"], r["n_old"], r["n_new"],
                  sig(r.get("old_median")), sig(r.get("new_median")), r.get("note", "")))
            continue
        print("| %s | %s | %s (%s) | %s | %d/%d | %s | %s | %s %% | [%s, %s] %% | %s-%s | %s-%s | %s |" % (
            r["pair"], r["kind"], r["measure"], r["unit"], r["subset"], r["n_old"], r["n_new"], sig(r["old_median"]), sig(r["new_median"]),
            sig(r["pct_change"]), sig(r["ci_low"]), sig(r["ci_high"]), sig(r["old_min"]), sig(r["old_max"]), sig(r["new_min"]), sig(r["new_max"]),
            "yes" if r["measurable"] else "no"))


if __name__ == "__main__":
    main()
