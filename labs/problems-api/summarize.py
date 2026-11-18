#!/usr/bin/env python3
"""Summarise one problems-api cell: Tooling API problems versus what console parsing finds in the same run.

Usage: summarize.py CELL_DIR [--markdown]
Reads CELL_DIR/problems.jsonl, runner.json, console.log, cell.txt. Writes CELL_DIR/summary.json (schema problems-cell/1).

Tooling API side: single problem events (at most 15 per problem id by default; Gradle's
org.gradle.internal.problem.summary.threshold) plus the counts of ProblemSummariesEvent (the ones beyond that).
Console side, from the same build's console.log:
  problem_found     lines starting "Problem found:" (Gradle's console rendering of a problem, --warning-mode=all)
  kotlin_w / kotlin_e  classic Kotlin compiler lines "w: ..." / "e: ..."
  gradle_deprecation lines saying a feature "will fail with an error in Gradle N" or "is scheduled to be removed in Gradle N"
  javac_warning     lines with ": warning:" (javac)
  agp_warning       lines starting "WARNING:" (AGP's own console warnings)
"""
import collections
import json
import os
import re
import sys

SCHEMA = "problems-cell/1"
CONSOLE = {
    "problem_found": re.compile(r"^Problem found: "),
    "kotlin_w": re.compile(r"^w: "),
    "kotlin_e": re.compile(r"^e: "),
    "gradle_deprecation": re.compile(r"(will fail with an error in Gradle \d+|is scheduled to be removed in Gradle \d+)"),
    "javac_warning": re.compile(r": warning: "),
    "agp_warning": re.compile(r"^WARNING: "),
}


def owner(path):
    """Coarse owner from the group path (the group names are the reporter's; this mapping is the lab's)."""
    low = [p.lower() for p in path]
    if not low:
        return "none"
    if any("agp" in p or "android" in p for p in low):
        return "AGP"
    if any("kotlin" in p or p.startswith("kgp") for p in low):
        return "Kotlin"
    if any(p.startswith("compiler") for p in low):  # KGP compiler groups, in case the Kotlin parent is missing
        return "Kotlin?"
    return "Gradle"


def kotlin_compiler(r):
    low = [p.lower() for p in r["group_path"]]
    dn = (r.get("id_display_name") or "").lower()
    return dn.startswith("kotlin compiler") or (any("compiler" in p for p in low) and owner(r["group_path"]).startswith("Kotlin"))


def load_kv(path):
    out = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if "=" in line:
                k, v = line.rstrip("\n").split("=", 1)
                out[k] = v
    return out


def summarize(d):
    recs = [json.loads(l) for l in open(os.path.join(d, "problems.jsonl"), encoding="utf-8") if l.strip()]
    probs = [r for r in recs if r["kind"] == "problem"]
    sums = [r for r in recs if r["kind"] == "summary"]
    by_id = collections.OrderedDict()
    for r in probs + sums:
        key = " > ".join(r["group_path"]) + " :: " + (r["id_name"] or "")
        e = by_id.setdefault(key, {"group_path": r["group_path"], "group_display_path": r["group_display_path"],
                                   "id_name": r["id_name"], "id_display_name": r["id_display_name"],
                                   "owner": owner(r["group_path"]), "single": 0, "summarised": 0, "severities": {}})
        if r["kind"] == "problem":
            e["single"] += 1
            sv = r.get("severity_name", "?")
            e["severities"][sv] = e["severities"].get(sv, 0) + 1
        else:
            e["summarised"] += r["count"] or 0
    for e in by_id.values():
        e["total"] = e["single"] + e["summarised"]
    owners = collections.Counter()
    groups = collections.Counter()
    for e in by_id.values():
        owners[e["owner"]] += e["total"]
        groups[" > ".join(e["group_path"])] += e["total"]
    severities = collections.Counter(r.get("severity_name", "?") for r in probs)
    kc = [r for r in probs if kotlin_compiler(r)]
    kc_ids = [e for e in by_id.values() if e["id_display_name"] and e["id_display_name"].lower().startswith("kotlin compiler")]
    line64 = [r for r in probs if any((l.get("path") or "").endswith("SystemTrayNotifier.kt") and l.get("line") == 64
                                      for l in r["origin_locations"] + r["contextual_locations"])]
    console = collections.Counter()
    cpath = os.path.join(d, "console.log")
    if os.path.exists(cpath):
        for line in open(cpath, encoding="utf-8", errors="replace"):
            for k, rx in CONSOLE.items():
                if rx.search(line):
                    console[k] += 1
    runner = json.load(open(os.path.join(d, "runner.json"), encoding="utf-8"))
    cell = load_kv(os.path.join(d, "cell.txt"))
    single, summarised = len(probs), sum(r["count"] or 0 for r in sums)
    return {
        "schema": SCHEMA,
        "cell": cell.get("cell", os.path.basename(d.rstrip("/"))),
        "versions": {k: cell.get(k) for k in ("nia", "catalog_kotlin", "catalog_agp", "catalog_ksp", "resolved_agp",
                                              "resolved_kgp", "resolved_ksp", "gradle", "java")},
        "task": cell.get("task"), "args": cell.get("args"),
        "outcome": runner.get("outcome"), "wall_ms": runner.get("wall_ms"),
        "tooling_api_client": runner.get("tooling_api_client"), "gradle_version_reported": runner.get("gradle_version"),
        "failure_messages": [f.get("message") for f in runner.get("failures", [])],
        "task_outcomes": runner.get("task_outcomes"),
        "tapi": {"single": single, "summarised": summarised, "total": single + summarised,
                 "summary_records": len(sums), "other_problem_events": runner.get("other_problem_events", 0),
                 "severities_single": dict(severities), "by_owner": dict(owners), "by_group_path": dict(groups),
                 "kotlin_compiler_single": len(kc),
                 "kotlin_compiler_total": sum(e["total"] for e in kc_ids),
                 "with_failure": sum(1 for r in probs if r.get("has_failure"))},
        "console": {k: console.get(k, 0) for k in CONSOLE},
        "line64": line64[:3],
        "ids": list(by_id.values()),
    }


def markdown(s):
    t, c = s["tapi"], s["console"]
    v = s["versions"]
    out = ["#### %s: %s" % (s["cell"], s["outcome"]),
           "",
           "Gradle %s, AGP %s, KGP %s, KSP %s; %s" % (v.get("gradle"), v.get("resolved_agp") or v.get("catalog_agp"),
                                                     v.get("resolved_kgp") or v.get("catalog_kotlin"),
                                                     v.get("resolved_ksp") or v.get("catalog_ksp"), v.get("java")),
           "",
           "| Source | Count |", "|---|---|",
           "| Tooling API single problem events | %d |" % t["single"],
           "| Tooling API summarised (beyond threshold) | %d |" % t["summarised"],
           "| Tooling API total | %d |" % t["total"],
           "| of which Kotlin compiler (total) | %d |" % t["kotlin_compiler_total"],
           ] + ["| console `%s` lines | %d |" % (k, n) for k, n in c.items()] + [
           "",
           "| Owner (from group path) | Group path | Id | Total |", "|---|---|---|---|"]
    for e in sorted(s["ids"], key=lambda e: -e["total"])[:25]:
        out.append("| %s | %s | %s | %d |" % (e["owner"], " > ".join(e["group_path"]), e["id_name"], e["total"]))
    if len(s["ids"]) > 25:
        out.append("| ... | %d more ids | | |" % (len(s["ids"]) - 25))
    return "\n".join(out)


def main():
    d = sys.argv[1]
    s = summarize(d)
    json.dump(s, open(os.path.join(d, "summary.json"), "w", encoding="utf-8"), indent=1)
    print(markdown(s) if "--markdown" in sys.argv else json.dumps({k: s[k] for k in ("cell", "outcome", "tapi", "console")}, indent=1))


if __name__ == "__main__":
    main()
