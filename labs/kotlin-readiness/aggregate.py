#!/usr/bin/env python3
"""Merge the per-cell diagnostics.json files of a kotlin-readiness run into one readiness.json, compare the cells,
and check the predictions.

Usage: aggregate.py PARTS_DIR OUT.json [--run-id ID] [--harness-sha SHA] [--nia-sha SHA]

Cells (see make_config.py): A current plain, B current tryNext, C next compiler with language 2.4, D next plain.
Comparisons join on (file relative to the repo, line), never on the diagnostic name: the warning and the later error
have different names (RETURN_IN_FUNCTION_WITH_EXPRESSION_BODY_WARNING vs ..._AND_IMPLICIT_TYPE). Only project code
counts (origin "project"); build-logic is compiled by Gradle's own Kotlin, not the version under test.
Exit code 0 when every checked prediction agrees, 1 otherwise. A missing cell counts as disagreeing.
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

SCHEMA = "readiness-run/1"
LINE64 = ("core/notifications/src/main/kotlin/com/google/samples/apps/nowinandroid/core/notifications/"
          "SystemTrayNotifier.kt", 64)


def load(parts):
    cells = {}
    for p in glob.glob(os.path.join(parts, "**", "diagnostics.json"), recursive=True):
        d = json.load(open(p))
        cells[d["cell"]] = d
    return cells


def by_letter(cells):
    return {name.split("-", 1)[0]: c for name, c in cells.items()}


def kotlin(c, sev=None, project_only=True):
    out = [d for d in c["diagnostics"] if d["source"] == "kotlin-compiler"]
    if project_only:
        out = [d for d in out if d["origin"] == "project"]
    if sev:
        out = [d for d in out if d["severity"] == sev]
    return out


def key(d):
    return (d["file"], d["line"])


def index(diags):
    ix = collections.defaultdict(list)
    for d in diags:
        if d["file"] and d["line"]:
            ix[key(d)].append(d)
    return ix


def brief(d):
    return {k: d.get(k) for k in ("severity", "name", "file", "line", "task", "message", "marker")}


def modules_not_checked(c):
    return sorted({t.rsplit(":", 1)[0] for t in c["compile_tasks"]["not_run"]})


def future_errors(a, b, next_lang):
    """B's errors against A's warnings at the same file and line: predicted / warned (not marked) / silent / ambiguous.
    And A's warnings marked for next_lang that did not become errors in B."""
    aw = index(kotlin(a, "warning"))
    out = {"predicted": [], "warned_not_marked": [], "silent": [], "ambiguous": [], "marked_not_failed": []}
    berr = kotlin(b, "error")
    for e in berr:
        ws = aw.get(key(e), [])
        if len(ws) > 1:
            out["ambiguous"].append({"error": brief(e), "warnings": [brief(w) for w in ws]})
        elif ws and ws[0]["marker"] and next_lang in (None, ws[0]["marker"]["language"]):
            out["predicted"].append({"error": brief(e), "warning": brief(ws[0])})
        elif ws:
            out["warned_not_marked"].append({"error": brief(e), "warning": brief(ws[0])})
        else:
            out["silent"].append({"error": brief(e)})
    bkeys = {key(e) for e in berr}
    executed_b = {d["task"] for d in b["diagnostics"]} | set(b.get("executed_compile_tasks", []))
    for w in kotlin(a, "warning"):
        if w["marker"] and next_lang in (None, w["marker"]["language"]) and key(w) not in bkeys:
            # was the same task compiled in B? if not, the module never compiled (masked), not a schedule change
            reason = "compiled, no error" if w["task"] in executed_b else "not compiled in B (masked)"
            out["marked_not_failed"].append({"warning": brief(w), "reason": reason})
    return out


def new_warnings(a, c):
    """Warnings the next compiler (C, language pinned to today's) reports that today's compiler (A) does not, and the
    reverse. Joined on (file, line, name); a warning with no file is joined on (task, message)."""
    def k(d):
        return (d["file"], d["line"], d["name"]) if d["file"] else (d["task"], d["message"])
    aw = {k(d): d for d in kotlin(a, "warning")}
    cw = {k(d): d for d in kotlin(c, "warning")}
    return {"new": [brief(cw[x]) for x in sorted(cw, key=str) if x not in aw],
            "gone": [brief(aw[x]) for x in sorted(aw, key=str) if x not in cw]}


def failure_class(c):
    """setup: the build failed before any Kotlin compile task failed (guard, configuration, a non-Kotlin task).
    source: a Kotlin compile task failed and reported an error located in project code.
    toolchain: a Kotlin compile task failed with no located project error (plugin option, compiler crash)."""
    if c["outcome"] == "PASS":
        return None
    if c.get("guard") not in (None, "OK", "ok", "PASS"):
        return "setup"
    kfail = c["compile_tasks"]["failed"]
    if not kfail:
        return "setup"
    located = {d["task"] for d in kotlin(c, "error")}
    return "source" if any(t in located for t in kfail) else "toolchain"


def summary(c):
    k = kotlin(c, project_only=False)
    p = kotlin(c)
    return {
        "cell": c["cell"], "requested": c["requested"], "flags": c["flags"], "gradle_args": c["gradle_args"],
        "outcome": c["outcome"], "failure_class": failure_class(c), "duration_s": c["duration_s"],
        "language_versions": c["language_versions"],
        "compile_tasks": {k2: (v if isinstance(v, int) else len(v)) for k2, v in c["compile_tasks"].items()},
        "failed_tasks": c["failed_tasks"], "modules_not_checked": modules_not_checked(c),
        "counts": {"kotlin_all": len(k), "project_warnings": sum(d["severity"] == "warning" for d in p),
                   "project_errors": sum(d["severity"] == "error" for d in p),
                   "marked": sum(1 for d in p if d["marker"]),
                   "future_wording_unmarked": sum(1 for d in p if d["future_wording_unmarked"]),
                   "by_origin": dict(collections.Counter(d["origin"] for d in k)),
                   "formats": dict(collections.Counter(d["format"] for d in k))},
    }


def state(c, file_line):
    hits = [d for d in kotlin(c) if key(d) == file_line]
    if any(d["severity"] == "error" for d in hits):
        return "error"
    return "warning" if hits else "clean"


def predictions(L):
    """(letter, expected outcome, expected line-64 state, note). Expected outcome None = record only."""
    return [
        ("A", "PASS", "warning", "today's compiler: line 64 warns, marked for language 2.5 (measured 2026-11-16)"),
        ("B", "FAIL", "error", "tryNext = language 2.5: KTLC-288 is an error (measured 2026-11-16)"),
        ("C", None, "warning", "prediction: the next compiler under language 2.4 keeps line 64 a warning"),
        ("D", "FAIL", "error", "prediction: language 2.5 is the RC's default, so line 64 fails as on 2.5.0-Beta2"),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts")
    ap.add_argument("out")
    ap.add_argument("--run-id")
    ap.add_argument("--harness-sha")
    ap.add_argument("--nia-sha")
    a = ap.parse_args()
    cells = load(a.parts)
    L = by_letter(cells)
    ok = True
    checks = []
    for letter, outcome, s64, note in predictions(L):
        c = L.get(letter)
        if c is None:
            checks.append({"cell": letter, "agree": False, "note": "missing cell"})
            ok = False
            continue
        got64 = state(c, LINE64)
        agree = (outcome is None or c["outcome"] == outcome) and got64 == s64
        checks.append({"cell": c["cell"], "expected": [outcome, s64], "got": [c["outcome"], got64],
                       "agree": agree, "note": note})
        ok &= agree
    comps = {}
    if "A" in L and "B" in L:
        # language of B from the init script's LAB lv lines; None (unknown) = accept any marker language
        nl = (L["B"]["language_versions"] or [None])[-1]
        # compile tasks A ran that B did not: B's masked modules, even when the expected list is missing
        masked = sorted(set(L["A"].get("executed_compile_tasks", [])) - set(L["B"].get("executed_compile_tasks", [])))
        nc = sorted(set(modules_not_checked(L["B"])) | {t.rsplit(":", 1)[0] for t in masked})
        comps["A_vs_B_future_errors"] = dict(future_errors(L["A"], L["B"], nl), language=nl or "unknown",
                                             lower_bound=bool(nc), modules_not_checked=nc)
    if "A" in L and "C" in L:
        comps["A_vs_C_next_compiler_warnings"] = new_warnings(L["A"], L["C"])
    if "B" in L and "D" in L:
        be, de = {key(d) for d in kotlin(L["B"], "error")}, {key(d) for d in kotlin(L["D"], "error")}
        comps["B_vs_D_same_language_rules"] = {"both": len(be & de), "only_B": sorted(map(list, be - de)),
                                               "only_D": sorted(map(list, de - be))}
    out = {"schema": SCHEMA, "run_id": a.run_id, "harness_sha": a.harness_sha, "nowinandroid_sha": a.nia_sha,
           "line_under_test": {"file": LINE64[0], "line": LINE64[1]},
           "cells": [summary(cells[n]) for n in sorted(cells)], "predictions": checks, "comparisons": comps,
           "diagnostics": {n: cells[n]["diagnostics"] for n in sorted(cells)}}
    text = json.dumps(out, indent=1)
    if re.search(r"/home/runner|RUNNER_TEMP|/out/work/", text):
        print("ERROR: a runner path leaked into the aggregate")
        ok = False
    open(a.out, "w").write(text)

    print("| cell | outcome | class | language | compile tasks run/expected | project warnings | errors | marked | not checked |")
    print("|---|---|---|---|---|---|---|---|---|")
    for s in out["cells"]:
        ct = s["compile_tasks"]
        print("| %s | %s | %s | %s | %s/%s | %d | %d | %d | %s |" % (
            s["cell"], s["outcome"], s["failure_class"] or "", ",".join(s["language_versions"]),
            ct["executed"], ct["expected"], s["counts"]["project_warnings"], s["counts"]["project_errors"],
            s["counts"]["marked"], ", ".join(s["modules_not_checked"]) or "-"))
    print()
    for ch in checks:
        print("- %s %s: %s" % ("AGREE" if ch["agree"] else "DISAGREE", ch["cell"],
                              ch.get("note") if "got" not in ch else "expected %s, got %s (%s)" % (
                                  ch["expected"], ch["got"], ch["note"])))
    fe = comps.get("A_vs_B_future_errors")
    if fe:
        print("\nB errors vs A warnings (language %s%s): predicted %d, warned not marked %d, silent %d, ambiguous %d;"
              " marked but not failed %d" % (fe["language"], ", lower bound" if fe["lower_bound"] else "",
                                             len(fe["predicted"]), len(fe["warned_not_marked"]), len(fe["silent"]),
                                             len(fe["ambiguous"]), len(fe["marked_not_failed"])))
    nw = comps.get("A_vs_C_next_compiler_warnings")
    if nw:
        print("Next compiler vs today's (language 2.4): %d new warnings, %d gone" % (len(nw["new"]), len(nw["gone"])))
        for d in nw["new"][:15]:
            print("  new: %s %s:%s %s" % (d["name"], d["file"], d["line"], (d["message"] or "")[:90]))
    bd = comps.get("B_vs_D_same_language_rules")
    if bd:
        print("B vs D errors (same language rules, different compiler): both %d, only B %d, only D %d" % (
            bd["both"], len(bd["only_B"]), len(bd["only_D"])))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
