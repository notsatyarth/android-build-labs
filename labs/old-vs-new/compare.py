"""Compare old-versus-new build times on the CI runner with the original macOS medians (Apple M1, gradle-profiler, n = 10 per cell).
Usage: python3 -I compare.py PROFILER_OUT_DIR OLD NEW   (reads agg.json written by agg.py)
Prints the old/new medians and the relative change per scenario. 'same direction' is only judged when both the macOS
and the CI change are larger than 5 %; smaller changes are reported as 'within noise'."""
import json, statistics as st, sys
from pathlib import Path
MAC = {  # median seconds, 'total execution time'
    "c5b604f72": {"config": 1.46, "clean": 34.49, "nonabi": 3.10}, "83d6dbb85": {"config": 1.51, "clean": 35.09, "nonabi": 3.36},
    "7d45eae4f": {"config": 1.31, "clean": 35.58, "nonabi": 3.10}, "94571e675": {"config": 1.20, "clean": 37.67, "nonabi": 3.11},
    "ade8065442": {"config": 1.71, "clean": 37.63, "nonabi": 3.56}, "2c56ce13b": {"config": 1.24, "clean": 36.59, "nonabi": 3.16},
}
out, old, new = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
agg = json.load(open(out / "agg.json"))
def med(c, s):
    xs = agg.get(c, {}).get(f"{s}|total execution time")
    return st.median(xs) if xs else None
print(f"| scenario | {old} CI s | {new} CI s | CI change | macOS change | verdict |\n|---|---|---|---|---|---|")
for s in ("config", "clean", "nonabi"):
    a, b = med(old, s), med(new, s)
    if a is None or b is None:
        print(f"| {s} | - | - | - | - | no data |"); continue
    ci = (b - a) / a * 100; mac = (MAC[new][s] - MAC[old][s]) / MAC[old][s] * 100
    if abs(ci) < 5 or abs(mac) < 5: v = "within noise (either change under 5 %)"
    else: v = "same direction" if (ci > 0) == (mac > 0) else "DIFFERENT direction"
    print(f"| {s} | {a:.2f} | {b:.2f} | {ci:+.1f} % | {mac:+.1f} % | {v} |")
