#!/usr/bin/env python3
"""Per-occurrence Kotlin diagnostics from one vmatrix cell directory (cell.json plus step logs).

Usage: extract.py CELL_DIR [OUT.json]   (default OUT: CELL_DIR/diagnostics.json)

Reads the task-step logs (NN-*.log). Two formats:
  - Gradle Problems API blocks, printed with --warning-mode=all by Kotlin >= 2.4.20:
        Problem found: Kotlin compiler: NAME (id: kotlin:compiler:warning:NAME)
          Kotlin compiler warning
            <message>
            Location: /abs/path/File.kt line 64
  - classic compiler lines (older Kotlin, or without --warning-mode=all):
        w: file:///abs/path/File.kt:64:13 <message>
One record per occurrence; nothing is merged. Paths are made relative to the cell's worktree, so no runner path is
kept. The task is the last "> Task :x" line seen before the diagnostic. Schema: readiness-cell/1.
"""
import glob
import json
import os
import re
import sys

SCHEMA = "readiness-cell/1"
TASK = re.compile(r"^> Task (\S+)(?: (UP-TO-DATE|FROM-CACHE|NO-SOURCE|SKIPPED|FAILED))?\s*$")
PROBLEM = re.compile(r"^Problem found: (.*) \(id: ([^)]+)\)\s*$")
LOCATION = re.compile(r"^\s*Location: (.*?)(?: line (\d+))?\s*$")
CLASSIC = re.compile(r"^([we]): (?:file://)?(/[^:]+?\.kts?)(?::(\d+)(?::(\d+))?)? (.*)$")
CLASSIC_NOFILE = re.compile(r"^([we]): (?!file://|/)(.*)$")
FAILED = re.compile(r"Execution failed for task '([^']+)'")
LV = re.compile(r"^LAB lv=(\S+) (\S+)$")
MARKER = re.compile(r"will become an error in language version (\d+\.\d+)")
# other forward-looking wording the marker does not match; counted so an undercount is visible
FUTURE = re.compile(r"\b(in the future|will be (?:prohibited|an error|removed|forbidden)|will become)\b", re.I)
WORKTREE = re.compile(r"^.*?/out/work/[^/]+/")


def is_kotlin_compile(task):
    name = task.rsplit(":", 1)[-1]
    return name.startswith("compile") and name.endswith("Kotlin")


def rel(path, workspace):
    if not path:
        return None
    path = re.sub(r"^file://", "", path)
    if workspace and path.startswith(workspace.rstrip("/") + "/"):
        return path[len(workspace.rstrip("/")) + 1:]
    m = WORKTREE.match(path)
    if m:
        return path[m.end():]
    return "<outside-worktree>/" + os.path.basename(path)


def origin(file, task):
    if task and task.startswith(":build-logic"):
        return "build-logic"
    if not file:
        return "no-file"
    if file.startswith("<outside-worktree>"):
        return "outside"
    if file.startswith("build-logic/"):
        return "build-logic"
    if "/build/generated/" in file or file.startswith("build/"):
        return "generated"
    return "project"


def module_of(task):
    if not task or task.count(":") < 2:
        return None
    return task.rsplit(":", 1)[0]


def finish(rec, workspace):
    msg = rec["message"].strip()
    rec["message"] = msg
    rec["file"] = rel(rec.pop("abs_file", None), workspace)
    rec["origin"] = origin(rec["file"], rec["task"])
    rec["module"] = module_of(rec["task"])
    m = MARKER.search(msg)
    rec["marker"] = {"text": m.group(0), "language": m.group(1)} if m else None
    rec["future_wording_unmarked"] = bool(not m and FUTURE.search(msg))
    return rec


def parse_log(text, workspace=None):
    diags, tasks, failed, lv = [], {}, [], {}
    task = None
    cur = None  # open Problems API block

    def close():
        nonlocal cur
        if cur is not None:
            diags.append(finish(cur, workspace))
            cur = None

    for line in text.splitlines():
        m = TASK.match(line)
        if m:
            close()
            task = m.group(1)
            tasks[task] = m.group(2) or "EXECUTED"
            continue
        m = PROBLEM.match(line)
        if m:
            close()
            pid = m.group(2)
            parts = pid.split(":")
            if len(parts) >= 4 and parts[0] == "kotlin" and parts[1] == "compiler":
                sev, name = parts[2], ":".join(parts[3:])
                cur = {"source": "kotlin-compiler", "severity": sev,
                       "name": None if name in ("compiler-warning", "compiler-error") else name,
                       "id": pid, "task": task, "abs_file": None, "line": None, "column": None,
                       "message": "", "format": "problems-api", "label": m.group(1)}
            else:
                cur = {"source": "other", "severity": None, "name": None, "id": pid, "task": task,
                       "abs_file": None, "line": None, "column": None, "message": "", "format": "problems-api",
                       "label": m.group(1)}
            continue
        if cur is not None:
            if line.startswith(" ") or line.startswith("\t"):
                lm = LOCATION.match(line)
                if lm:
                    loc = lm.group(1)
                    if loc.startswith(":"):  # a task path, not a file
                        cur["location_task"] = loc
                    else:
                        cur["abs_file"] = loc
                        cur["line"] = int(lm.group(2)) if lm.group(2) else None
                elif line.strip() and line.strip() not in ("Kotlin compiler warning", "Kotlin compiler error"):
                    cur["message"] += (" " if cur["message"] else "") + line.strip()
                continue
            close()
        m = CLASSIC.match(line)
        if m:
            diags.append(finish({"source": "kotlin-compiler", "severity": "warning" if m.group(1) == "w" else "error",
                                 "name": None, "id": None, "task": task, "abs_file": m.group(2),
                                 "line": int(m.group(3)) if m.group(3) else None,
                                 "column": int(m.group(4)) if m.group(4) else None,
                                 "message": m.group(5), "format": "classic"}, workspace))
            continue
        m = CLASSIC_NOFILE.match(line)
        if m and task and is_kotlin_compile(task):
            diags.append(finish({"source": "kotlin-compiler", "severity": "warning" if m.group(1) == "w" else "error",
                                 "name": None, "id": None, "task": task, "abs_file": None, "line": None,
                                 "column": None, "message": m.group(2), "format": "classic"}, workspace))
            continue
        m = FAILED.search(line)
        if m and m.group(1) not in failed:
            failed.append(m.group(1))
            continue
        m = LV.match(line)
        if m:
            lv[m.group(2)] = m.group(1)
    close()
    return diags, tasks, failed, lv


def extract(cell_dir):
    cj = os.path.join(cell_dir, "cell.json")
    cell = json.load(open(cj)) if os.path.exists(cj) else {}
    ws = cell.get("workspace")
    diags, tasks, failed, lv = [], {}, [], {}
    logs = sorted(glob.glob(os.path.join(cell_dir, "[0-9][0-9]-*.log")))
    for p in logs:
        d, t, f, l = parse_log(open(p, errors="replace").read(), ws)
        diags += d
        tasks.update(t)
        failed += [x for x in f if x not in failed]
        lv.update(l)
    kc = {t: s for t, s in tasks.items() if is_kotlin_compile(t) and not t.startswith(":build-logic")}
    expected = sorted(lv)  # every compile task the init script saw at configuration time
    executed = sorted(t for t, s in kc.items() if s in ("EXECUTED", "FAILED"))
    not_run = sorted(t for t in expected if t not in kc)
    no_source = sorted(t for t, s in kc.items() if s == "NO-SOURCE")
    skipped = sorted(t for t, s in kc.items() if s not in ("EXECUTED", "FAILED", "NO-SOURCE"))
    return {
        "schema": SCHEMA,
        "cell": cell.get("name") or os.path.basename(cell_dir.rstrip("/")),
        "requested": cell.get("requested"), "flags": cell.get("flags"),
        "gradle_args": [os.path.basename(a) if a.endswith(".gradle") else a for a in cell.get("gradle_args", [])],
        "outcome": cell.get("outcome"), "failed_step": cell.get("failed_step"),
        "duration_s": cell.get("duration_s"), "guard": (cell.get("guard") or {}).get("status"),
        "logs": [os.path.basename(p) for p in logs],
        "compile_tasks": {"expected": len(expected), "executed": len(executed), "not_run": not_run,
                          "no_source": no_source, "up_to_date_or_cached": skipped,
                          "complete": bool(expected) and not not_run and not skipped, "failed": [t for t in failed if is_kotlin_compile(t)]},
        "executed_compile_tasks": executed,
        "failed_tasks": failed,
        "language_versions": sorted(set(lv.values())),
        "language_by_task": lv,
        "diagnostics": diags,
    }


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cell_dir = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(cell_dir, "diagnostics.json")
    r = extract(cell_dir)
    json.dump(r, open(out, "w"), indent=1)
    k = [d for d in r["diagnostics"] if d["source"] == "kotlin-compiler"]
    print("%s: %s, %d Kotlin diagnostics (%d errors), compile tasks %d/%d executed, language %s -> %s" % (
        r["cell"], r["outcome"], len(k), sum(d["severity"] == "error" for d in k),
        r["compile_tasks"]["executed"], r["compile_tasks"]["expected"], ",".join(r["language_versions"]) or "?", out))


if __name__ == "__main__":
    main()
