#!/usr/bin/env python3
"""Compare every build of readiness probe 1 with the baseline build of the same run, task by task.

Usage: compare.py PARTS_DIR --run-id ID [--csv OUT.csv] [--json OUT.json]
PARTS_DIR holds one build.json per build (any depth; the workflow downloads one artifact per build).

For each build: new failures = tasks that failed in the build but not in the baseline, minus the known baseline failures
of probe_config.json; tasks that ran in the baseline but did not run in the build (not-run, or absent from the task
graph); configuration failure; harness fault. Prints Markdown. --csv writes one line per build (header included), the
format appended to the probe-data branch. A harness fault is never reported as a pass."""
import argparse
import csv
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = json.load(open(os.path.join(HERE, "probe_config.json")))
ORDER = list(CONFIG["builds"])
FIELDS = ["date", "run_id", "nia_commit", "build", "mode", "tool", "gradle", "agp", "kotlin", "jvm", "gradle_raised_from",
          "build_exit", "configuration_failed", "failed", "not_run", "passed", "planned", "new_failures_vs_baseline",
          "known_baseline_failures_seen", "harness_fault", "baseline_usable"]


def load(parts):
    builds = {}
    for root, _, files in os.walk(parts):
        if "build.json" in files:
            b = json.load(open(os.path.join(root, "build.json")))
            builds[b["build"]] = b
    return builds


def failed_set(b):
    return {t for t, o in b["outcomes"].items() if o == "failed"}


def first_line(b, task):
    d = b["failed"].get(task, {})
    lines = d.get("compiler_errors") or d.get("messages") or []
    # Gradle's "Execution failed for task" wrapper says nothing; prefer the first more specific message.
    specific = [l for l in lines if not l.startswith("Execution failed for task")]
    return (specific or lines or [""])[0][:300]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts")
    ap.add_argument("--run-id", default="local")
    ap.add_argument("--csv")
    ap.add_argument("--json")
    a = ap.parse_args()
    builds = load(a.parts)
    known = set(CONFIG["known_failures"])
    base = builds.get("baseline")
    md = []
    rows = []
    report = {"run_id": a.run_id, "builds": {}}

    base_failed = failed_set(base) if base else set()
    base_unknown = sorted(base_failed - known) if base else []
    baseline_usable = bool(base) and not base["harness_fault"] and not base["configuration_failed"] and not base_unknown
    if base is None:
        md.append("**Baseline missing: no comparison possible.**")
    elif not baseline_usable:
        why = "harness fault" if base["harness_fault"] else ("configuration failed" if base["configuration_failed"]
                                                             else "failures outside the known list: " + ", ".join(base_unknown))
        md.append("**Baseline red (%s): main must pass first; new-failure counts below are not meaningful.**" % why)
    md.append("")
    md.append("| Build | Mode | Gradle / AGP / Kotlin | Config failed | Failed | Not run | Passed | New failures vs baseline | Markers | Exit |")
    md.append("|---|---|---|---|---|---|---|---|---|---|")
    details = []
    for name in ORDER + sorted(set(builds) - set(ORDER)):
        b = builds.get(name)
        if b is None:
            md.append("| %s | | | | | | | no build.json (job failed before writing it) | harness fault | |" % name)
            rows.append({"date": "", "run_id": a.run_id, "build": name, "harness_fault": True})
            continue
        e = b["expected"]
        fs = failed_set(b)
        known_seen = sorted(fs & known)
        new = sorted(fs - base_failed - known) if (base and name != "baseline") else []
        lost = []
        if base and name != "baseline":
            for t, o in base["outcomes"].items():
                if o not in ("failed", "not-run") and b["outcomes"].get(t) in (None, "not-run"):
                    lost.append(t)
        c = b["counts"]
        raised = b.get("gradle_raised") or {}
        vers = "%s / %s / %s" % (e["gradle"], e["agp"], e["kotlin"])
        if raised.get("to") == e["gradle"]:
            vers += " (Gradle raised from %s)" % raised["from"]
        markers = "HARNESS FAULT: " + "; ".join(b["harness_faults"]) if b["harness_fault"] else "ok"
        newcell = "n/a (baseline)" if name == "baseline" else (str(len(new)) if not b["configuration_failed"] else "configuration failed")
        md.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            name, b["mode"], vers, "yes" if b["configuration_failed"] else "no", c["failed"], c["not_run"], c["passed"],
            newcell, markers, b["build_exit"]))
        rows.append({"date": b["resolved_at"][:10], "run_id": a.run_id, "nia_commit": b["nia_commit"], "build": name,
                     "mode": b["mode"], "tool": b["tool"], "gradle": e["gradle"], "agp": e["agp"], "kotlin": e["kotlin"],
                     "jvm": (b.get("proof") or {}).get("jvm") or (b["jvm"][0].split(" ")[0] if b["jvm"] else ""),
                     "gradle_raised_from": raised.get("from", "") if raised.get("to") == e["gradle"] else "",
                     "build_exit": b["build_exit"], "configuration_failed": b["configuration_failed"],
                     "failed": c["failed"], "not_run": c["not_run"], "passed": c["passed"], "planned": c["planned"],
                     "new_failures_vs_baseline": "" if name == "baseline" or b["configuration_failed"] else len(new),
                     "known_baseline_failures_seen": len(known_seen), "harness_fault": b["harness_fault"],
                     "baseline_usable": baseline_usable})
        report["builds"][name] = {"new_failures": {t: first_line(b, t) for t in new}, "lost_vs_baseline": len(lost),
                                  "known_seen": known_seen, "configuration_failed": b["configuration_failed"],
                                  "harness_faults": b["harness_faults"], "proof": b["proof"]}
        sec = ["#### %s" % name, ""]
        sec.append("- Command: `%s`" % b["command"])
        sec.append("- Proof: `%s`" % json.dumps(b["proof"]))
        if b["edits"]:
            sec.append("- Edits: `%s`" % json.dumps(b["edits"]))
        if raised:
            sec.append("- Gradle raise: %s" % json.dumps(raised))
        if b["configuration_failed"] or (b["build_exit"] not in (0, "0") and not fs):
            for blk in b["build_errors"][:2]:
                sec.append("- Build error: `%s`" % " / ".join(blk)[:400])
        for t in new:
            sec.append("- NEW failure `%s`: `%s`" % (t, first_line(b, t)))
        if name == "baseline":
            for t in sorted(fs):
                sec.append("- baseline failure `%s`%s: `%s`" % (t, " (known)" if t in known else "", first_line(b, t)))
        if known_seen and name != "baseline":
            sec.append("- Known baseline failures present (not counted as new): %s" % ", ".join(known_seen))
        if lost:
            sec.append("- %d task(s) that ran in the baseline did not run here (not-run or absent from the task graph)" % len(lost))
        if b["test_failures"]:
            sec.append("- Failed tests (first %d): %s" % (len(b["test_failures"]), "; ".join(b["test_failures"][:5])))
        details += sec + [""]
    print("\n".join(md + [""] + details))
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
    if a.json:
        json.dump(report, open(a.json, "w"), indent=1, sort_keys=True)
    # Exit 0 even when builds fail: a red probe build is a result. Exit 1 only when no build.json was found at all.
    sys.exit(0 if builds else 1)


if __name__ == "__main__":
    main()
