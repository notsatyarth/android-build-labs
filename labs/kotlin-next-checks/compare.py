#!/usr/bin/env python3
"""Check the kotlin-next-checks predictions against the cell results.

Usage: compare.py PARTS_DIR   (PARTS_DIR holds one downloaded artifact per cell: <x>/<cell>/cell.json and *.log)
The line under test is nowinandroid core/notifications SystemTrayNotifier.kt:64, a `return` inside a function with an
expression body and no explicit return type (Kotlin language feature KTLC-288,
ForbidReturnInExpressionBodyWithoutExplicitTypeEdgeCases). Predictions come from the Kotlin compiler source:
in 2.3.0 the feature is due in language 2.4 and flagged for progressive mode; in 2.4.21 it is due in 2.5 and not flagged.
Exit code 0 when every prediction agrees, 1 otherwise. A missing cell counts as disagreeing."""
import glob
import json
import os
import re
import sys

ERR = re.compile(r"^e: .*SystemTrayNotifier\.kt:64", re.M)
WARN = re.compile(r"^w: .*SystemTrayNotifier\.kt:64", re.M)
PROG = re.compile(r"^LAB progressiveMode=true on (\S+)", re.M)
TRYNEXT = re.compile(r"Experimental 'kotlin\.experimental\.tryNext' Option Enabled")

# cell -> (expected outcome, expected state of line 64: "error" | "warning" | "clean" | None = record only)
PREDICT = {
    "k230-plain": ("PASS", "warning"),          # measured before: a warning in Kotlin 2.3
    "k230-trynext": ("FAIL", "error"),          # measured before (flag-builds follow-up)
    "k230-progressive": ("FAIL", "error"),      # prediction: progressive turns KTLC-288 on in 2.3.0
    "k2421-plain": ("PASS", None),              # record only
    "k2421-trynext": ("FAIL", "error"),         # prediction: language 2.5 turns KTLC-288 on
    "k2421-progressive": ("PASS", None),        # prediction: KTLC-288 not flagged for progressive in 2.4.21
}


def load(parts):
    cells = {}
    for cj in glob.glob(os.path.join(parts, "**", "cell.json"), recursive=True):
        d = os.path.dirname(cj)
        c = json.load(open(cj))
        logs = "".join(open(p, errors="replace").read() for p in sorted(glob.glob(os.path.join(d, "*.log"))))
        line = "error" if ERR.search(logs) else "warning" if WARN.search(logs) else "clean"
        cells[c["name"]] = {"outcome": c.get("outcome"), "guard": (c.get("guard") or {}).get("result"),
                            "line64": line, "progressive_tasks": len(set(PROG.findall(logs))),
                            "trynext_warning": bool(TRYNEXT.search(logs)),
                            "first_error": next(iter(re.findall(r"^e: .*$", logs, re.M)), "")[:240]}
    return cells


def main():
    cells = load(sys.argv[1])
    ok_all = True
    print("| cell | outcome | guard | line 64 | progressive tasks | tryNext warning | expected | agrees |")
    print("|---|---|---|---|---|---|---|---|")
    for name, (exp_out, exp_line) in PREDICT.items():
        c = cells.get(name)
        if not c:
            print("| %s | missing | | | | | %s | no |" % (name, exp_out)); ok_all = False; continue
        ok = c["outcome"] == exp_out and (exp_line is None or c["line64"] == exp_line)
        if name.endswith("progressive") and c["progressive_tasks"] == 0:
            ok = False  # the init script did not take effect, so the cell proves nothing
        if name.endswith("trynext") and not c["trynext_warning"]:
            ok = False
        ok_all &= ok
        print("| %s | %s | %s | %s | %d | %s | %s%s | %s |" % (
            name, c["outcome"], c["guard"], c["line64"], c["progressive_tasks"], c["trynext_warning"],
            exp_out, (", line 64 " + exp_line) if exp_line else "", "yes" if ok else "NO"))
    print()
    for name, c in sorted(cells.items()):
        if c["first_error"]:
            print("- %s first error: `%s`" % (name, c["first_error"]))
    print("\nAll predictions agree: %s" % ok_all)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
