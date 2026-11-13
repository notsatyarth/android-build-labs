"""Same-runner pairs from pair.sh: each pair directory holds runner.txt and two cell directories built alternately on one runner.
Usage: python3 -I compare_pairs.py DIR   (finds every runner.txt at any depth whose directory has two cell subdirectories)
For each pair: medians of both cells and the paired difference (second cell minus first) of builds with the same number.
A build counts only if it succeeded and has the cell's intended Kotlin daemon count; a pair position counts only if both do.
Metrics as in compare.py (wall, peak total RSS, Kotlin RSS held at build end, Kotlin GC pause, Kotlin CPU)."""
import re, statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare import build  # noqa: E402

METRICS = [("wall", "wall s", 1), ("peak_total", "peak total RSS MB", 0), ("held", "Kotlin RSS held at build end MB", 0),
           ("committed", "Kotlin committed heap MB", 0), ("gc_ms", "Kotlin GC pause ms", 0), ("gc_n", "GC pauses", 0),
           ("kcpu", "Kotlin CPU s", 1)]


def cell_builds(d):
    name = (d / "setup.txt").read_text().splitlines()[0].lstrip("# ").strip()
    want = 1 if name.startswith("d1") else 2
    out = {}
    for c in d.glob("run*.csv"):
        b = build(c, d / "gc")
        if b and b["kd"] == want:
            out[int(re.sub(r"\D", "", c.stem))] = b
    return name, out


def m(v, nd):
    return f"{statistics.median(v):+.{nd}f}" if v else "-"


def main():
    pairs = []
    for rt in sorted(Path(sys.argv[1]).rglob("runner.txt")):
        subs = sorted(p.parent for p in rt.parent.glob("*/setup.txt"))
        if len(subs) != 2:
            continue
        (na, a), (nb, b) = cell_builds(subs[0]), cell_builds(subs[1])
        if na.startswith("d2") and nb.startswith("d1"):  # always first = one daemon
            (na, a), (nb, b) = (nb, b), (na, a)
        cpu = next((l.split(": ", 1)[1] for l in rt.read_text().splitlines() if l.startswith("cpu: ")), "?")
        pairs.append((na, a, nb, b, cpu))
    print("### Same-runner pairs (CI: x86 Linux runner; builds alternate A B A B on one machine)\n")
    print("| pair (A vs B) | runner CPU | builds A/B/paired | " + " | ".join(f"{lab}: A, B, median B-A" for _, lab, _ in METRICS) + " |")
    print("|---|---|---|" + "---|" * len(METRICS))
    for na, a, nb, b, cpu in pairs:
        idx = sorted(set(a) & set(b))
        cells = []
        for k, _, nd in METRICS:
            va, vb = [x[k] for x in a.values()], [x[k] for x in b.values()]
            diff = [b[i][k] - a[i][k] for i in idx]
            f = lambda v: f"{statistics.median(v):.{nd}f}" if v else "-"
            spread = f" [{min(diff):+.{nd}f}..{max(diff):+.{nd}f}]" if diff else ""
            cells.append(f"{f(va)}, {f(vb)}, {m(diff, nd)}{spread}")
        print(f"| {na} vs {nb} | {cpu} | {len(a)}/{len(b)}/{len(idx)} | " + " | ".join(cells) + " |")
    print("\nB-A per build position is in brackets [min..max]. A difference whose bracket does not include 0 is consistent across all"
          " paired builds on that runner; one runner per pair, so compare pairs with each other only for direction, not size.")


if __name__ == "__main__":
    main()
