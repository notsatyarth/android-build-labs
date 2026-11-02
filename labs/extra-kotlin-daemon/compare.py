"""Count Kotlin daemons per run of the extra-Kotlin-daemon 2x2 and compare with the original macOS runs.
Usage: python3 -I compare.py OUT_DIR   (reads run1.csv, run2.csv, run3b.csv, run4.csv written by procwatch.py)
A run's Kotlin daemon count is the number of distinct pids of kind kotlin-daemon in the samples."""
import csv, sys
from pathlib import Path
out = Path(sys.argv[1])
EXPECT = {"run1": (2, "as shipped, Kotlin 2.3.0"), "run2": (2, "Kotlin 2.4.0 + KSP 2.3.12"),
          "run3b": (1, "Kotlin 2.4.0 + matching kotlin.daemon.jvmargs in build-logic"), "run4": (2, "Kotlin 2.3.0 + matching kotlin.daemon.jvmargs in build-logic")}
print("| run | setup | Kotlin daemons macOS | CI | peak Kotlin daemon RSS MB (CI) | verdict |\n|---|---|---|---|---|---|")
ok = 0
for r, (n, what) in EXPECT.items():
    p = out / f"{r}.csv"
    if not p.exists():
        print(f"| {r} | {what} | {n} | - | - | no data |"); continue
    rows = [x for x in csv.DictReader(open(p)) if x["kind"] == "kotlin-daemon"]
    pids = {x["pid"] for x in rows}
    peak = max((float(x["rss_mb"]) for x in rows), default=0)
    v = "match" if len(pids) == n else "DIFFERS"
    ok += v == "match"
    print(f"| {r} | {what} | {n} | {len(pids)} | {peak:.0f} | {v} |")
print(f"\n{ok} of {len(EXPECT)} runs match the macOS daemon counts.")
