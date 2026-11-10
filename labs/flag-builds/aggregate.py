#!/usr/bin/env python3
"""Combine the per-flag vmatrix reports into one JSON file (tier 2 flag probe results).
Usage: aggregate.py CELLS_DIR SKIPPED.json OUT.json --agp V --kotlin V --ref SHA
CELLS_DIR holds one report.json per flag (as uploaded by the flag-builds jobs, any depth).
States: pass, fail, inconclusive (reason), not_applicable (flag absent in this version), not_run (no test value)."""
import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools", "version-matrix"))
from probes import result  # noqa: E402


def first_line(x):
    if isinstance(x, dict):
        x = x.get("text") or ""
    return (x or "").strip().split("\n")[0][:300] or None


def one(cell):
    flag, value = next(iter(cell["flags"].items()))
    base = {"flag": flag, "value": value, "duration_s": cell.get("duration_s"), "outcome": cell.get("outcome"),
            "failed_step": cell.get("failed_step"), "first_error": first_line(cell.get("first_error")),
            "by_owner": cell.get("by_owner"), "guard": (cell.get("guard") or {}).get("result")}
    o = cell.get("outcome")
    if o == "PASS":
        return dict(result("pass", None), **base)
    if o == "FAIL":
        return dict(result("fail", "failed with %s=%s at step %s" % (flag, value, cell.get("failed_step"))), **base)
    why = {"INVALID": "tool versions that ran differ from the requested ones (guard %s)" % base["guard"],
           "TIMEOUT": "timed out", "ERROR": cell.get("error") or "harness error", "SKIPPED": cell.get("skip_reason")}
    return dict(result("inconclusive", why.get(o, "unknown outcome %r" % o)), **base)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cells_dir")
    ap.add_argument("skipped")
    ap.add_argument("out")
    ap.add_argument("--agp")
    ap.add_argument("--kotlin")
    ap.add_argument("--ref")
    a = ap.parse_args()
    results = []
    for f in sorted(glob.glob(os.path.join(a.cells_dir, "**", "report.json"), recursive=True)):
        for c in json.load(open(f))["cells"]:
            if c.get("flags"):
                results.append(one(c))
    for s in json.load(open(a.skipped)):
        st = "not_applicable" if s["reason"].startswith("not_applicable") else "not_run"
        results.append(dict(result(st, s["reason"]), flag=s["flag"], value=None))
    counts = {}
    for r in results:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    out = {"schema": 1, "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "agp": a.agp,
           "kotlin": a.kotlin, "project_ref": a.ref, "counts": counts, "results": results}
    json.dump(out, open(a.out, "w"), indent=1)
    print("| flag | value | state | detail |\n|---|---|---|---|")
    for r in results:
        print("| %s | %s | %s | %s |" % (r["flag"], r.get("value"), r["state"], (r.get("first_error") or r.get("reason") or "")[:140].replace("|", "/")))
    print("\ncounts:", counts)


if __name__ == "__main__":
    main()
