#!/usr/bin/env python3
"""Combine per-commit history-series artifacts into one history.json (the data behind the history charts).

Usage: aggregate_history.py PARTS_DIR OUT.json [--project android/nowinandroid]
PARTS_DIR holds one directory per commit job, each with meta.json ({sha, date, subject}) and report.json (vmatrix).
A commit whose report is missing is kept as an inconclusive row, never dropped: a gap is a result."""
import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools", "version-matrix"))
from probes import result  # noqa: E402


def row(meta, rep):
    base = {"sha": meta["sha"], "date": meta.get("date"), "subject": meta.get("subject")}
    cells = (rep or {}).get("cells") or []
    if not cells:
        return dict(base, outcome=None, pins=None, duration_s=None, guard=None, first_error=None,
                    probes={"configuration_cache": result("inconclusive", "no report for this commit (the job did not finish)"),
                            "deprecations": result("inconclusive", "no report for this commit (the job did not finish)")})
    c = cells[0]
    fe = c.get("first_error")
    fe = (fe.get("text") if isinstance(fe, dict) else fe) or None
    p = c.get("probes") or {}

    def slim(x, keep):
        return {k: x[k] for k in ("state", "reason") + keep if k in x}
    return dict(base, outcome=c.get("outcome"), pins=c.get("pins"), duration_s=c.get("duration_s"),
                guard=(c.get("guard") or {}).get("result"),
                first_error=(fe or "").split("\n")[0][:300] or None,
                failed_step=c.get("failed_step"),
                probes={"configuration_cache": slim(p.get("configuration_cache") or result("inconclusive", "probe did not run"),
                                                    ("total_problems", "unique_problems", "cache_action")),
                        "deprecations": slim(p.get("deprecations") or result("inconclusive", "probe did not run"),
                                             ("total", "distinct"))})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts")
    ap.add_argument("out")
    ap.add_argument("--project", default="android/nowinandroid")
    a = ap.parse_args()
    rows = []
    for mf in sorted(glob.glob(os.path.join(a.parts, "**", "meta.json"), recursive=True)):
        d = os.path.dirname(mf)
        meta = json.load(open(mf))
        rp = os.path.join(d, "report.json")
        rep = json.load(open(rp)) if os.path.isfile(rp) else None
        if rep is None:
            # the report step failed but the cell finished: keep what the cell itself recorded
            cj = sorted(glob.glob(os.path.join(d, "*", "cell.json")))
            if cj:
                c = json.load(open(cj[0]))
                r = row(meta, None)
                r.update(outcome=c.get("outcome"), pins=c.get("pins"), duration_s=c.get("duration_s"),
                         guard=(c.get("guard") or {}).get("result"), failed_step=c.get("failed_step"))
                why = "the report step failed for this commit (cell finished with %s); see the job logs" % c.get("outcome")
                r["probes"] = {k: result("inconclusive", why) for k in ("configuration_cache", "deprecations")}
                rows.append(r)
                continue
        rows.append(row(meta, rep))
    rows.sort(key=lambda r: r.get("date") or "")
    out = {"schema": 1, "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "project": a.project,
           "commits": rows}
    json.dump(out, open(a.out, "w"), indent=1)
    print("| commit | date | gradle | agp | kotlin | outcome | s | config cache | deprecations |\n|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        pin = r.get("pins") or {}
        cc, dp = r["probes"]["configuration_cache"], r["probes"]["deprecations"]
        print("| %s | %s | %s | %s | %s | %s | %s | %s %s | %s %s |" % (
            r["sha"][:8], (r.get("date") or "")[:10], pin.get("gradle"), pin.get("agp"), pin.get("kotlin"), r.get("outcome"),
            r.get("duration_s"), cc["state"], cc.get("total_problems", ""), dp["state"], dp.get("total", "")))


if __name__ == "__main__":
    main()
