#!/usr/bin/env python3
"""Check the problems-api expectations across cells. Usage: compare.py DIR [--markdown] [--out results.json]

DIR holds one sub-directory per cell, each with summary.json (summarize.py). Expectations (where they come from):
  H1 harness   every cell has a runner outcome and the Tooling API delivered at least one problem event.
               A broken harness is the only thing that makes this script exit non-zero.
  H2 outcome   c1, c2, c3 build successfully; c4 (tryNext on Kotlin 2.4.21) fails (line 64 of SystemTrayNotifier.kt,
               KTLC-288, seen in the kotlin-readiness and kotlin-next-checks labs).
  H3 Kotlin    Kotlin compiler diagnostics reach the Problems API on Kotlin 2.4.21 (c3) but not on 2.3.0 (c1, c2).
               Source: "What's new in Kotlin 2.4.0" (compiler messages for Kotlin/JVM go to the Problems API).
  H4 AGP       no AGP problem in c1 (android.enableProblemsAPI defaults to false); c2 to c4 informational only:
               AGP reports sync issues, and a clean nowinandroid build may have none.
  H5 line 64   c4 reports the line-64 error as an ERROR problem with a file and line location.
  H6 counts    informational: Tooling API totals next to the console counts of the same run.
"""
import json
import os
import sys


def load(d):
    out = {}
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name, "summary.json")
        if os.path.exists(p):
            s = json.load(open(p, encoding="utf-8"))
            out[s["cell"]] = s
    return out


def owner_total(s, owner):
    return sum(n for o, n in s["tapi"]["by_owner"].items() if o.startswith(owner))


def main():
    d = sys.argv[1]
    cells = load(d)
    res = []

    def check(hid, cell, ok, text):
        res.append({"id": hid, "cell": cell, "result": ok, "text": text})

    for name in ("c1-k230", "c2-k230-agp", "c3-k2421-agp", "c4-k2421-agp-next"):
        s = cells.get(name)
        if not s:
            check("H1", name, "MISSING", "no summary.json")
            continue
        t = s["tapi"]
        check("H1", name, "PASS" if s["outcome"] in ("success", "failure") and t["single"] > 0 else "FAIL",
              "outcome %s, %d single problem events" % (s["outcome"], t["single"]))
        want = "failure" if name.startswith("c4") else "success"
        check("H2", name, "PASS" if s["outcome"] == want else "DIFF", "expected %s, got %s" % (want, s["outcome"]))
        kc = t["kotlin_compiler_total"]
        if name in ("c1-k230", "c2-k230-agp"):
            check("H3", name, "PASS" if kc == 0 else "DIFF", "Kotlin compiler problems on 2.3.0: %d (expected 0)" % kc)
        elif name == "c3-k2421-agp":
            check("H3", name, "PASS" if kc > 0 else "DIFF", "Kotlin compiler problems on 2.4.21: %d (expected > 0)" % kc)
        agp = owner_total(s, "AGP")
        if name == "c1-k230":
            check("H4", name, "PASS" if agp == 0 else "DIFF", "AGP problems without the flag: %d (expected 0)" % agp)
        else:
            check("H4", name, "INFO", "AGP problems with android.enableProblemsAPI=true: %d" % agp)
        if name.startswith("c4"):
            hit = [r for r in s["line64"] if r.get("severity_name") == "ERROR"]
            check("H5", name, "PASS" if hit else "DIFF",
                  "line-64 problem: %s" % ("%s (%s)" % (hit[0]["id_name"], " > ".join(hit[0]["group_path"])) if hit else "none"))
        c = s["console"]
        check("H6", name, "INFO", "Tooling API %d (single %d + summarised %d) vs console: Problem found %d, w: %d, e: %d, "
              "Gradle deprecation lines %d, javac warnings %d, WARNING: %d"
              % (t["total"], t["single"], t["summarised"], c["problem_found"], c["kotlin_w"], c["kotlin_e"],
                 c["gradle_deprecation"], c["javac_warning"], c["agp_warning"]))

    if "--markdown" in sys.argv:
        print("| Check | Cell | Result | Detail |\n|---|---|---|---|")
        for r in res:
            print("| %s | %s | %s | %s |" % (r["id"], r["cell"], r["result"], r["text"]))
    else:
        for r in res:
            print("%-3s %-18s %-7s %s" % (r["id"], r["cell"], r["result"], r["text"]))
    if "--out" in sys.argv:
        json.dump(res, open(sys.argv[sys.argv.index("--out") + 1], "w"), indent=1)
    sys.exit(1 if any(r["id"] == "H1" and r["result"] != "PASS" for r in res) else 0)


if __name__ == "__main__":
    main()
