#!/usr/bin/env python3
"""Attribute Gradle task time to tool owners (Gradle core, AGP, KGP/Kotlin, KSP, Hilt, Other).

Input: Gradle build operation traces (`-Dorg.gradle.internal.operations.trace=PREFIX`, file PREFIX-log.txt,
JSON lines; internal format, may change) or the reduced JSON files this script writes (`reduce`).
Owner = package of the task class recorded in the trace (ExecuteTaskBuildOperationDetails.taskClass):
  org.jetbrains.kotlin.*      -> KGP/Kotlin   (KotlinCompile also runs the Compose compiler plugin)
  com.google.devtools.ksp.*   -> KSP          (KSP processors, including Hilt/Dagger/Room, run inside these tasks)
  dagger.hilt.*               -> Hilt         (Gradle plugin tasks only; Hilt's processor time is in KSP/Java tasks)
  com.android.*               -> AGP
  org.gradle.*                -> Gradle core  (JavaCompile, Jar, Copy, Sync, Test, ...)
  anything else               -> Other
Usage:
  attribute.py reduce TRACE-log.txt OUT.json
  attribute.py report RUN1.json RUN2.json ... [--label TEXT] [--json OUT.json]
Each RUN file is one measured build. Reports median and range across runs. Standard library only.
"""
import json
import statistics
import sys

OWNERS = ["Gradle core", "AGP", "KGP/Kotlin", "KSP", "Hilt", "Other"]
RULES = [("org.jetbrains.kotlin.", "KGP/Kotlin"), ("com.google.devtools.ksp.", "KSP"), ("dagger.hilt.", "Hilt"),
         ("com.android.", "AGP"), ("org.gradle.", "Gradle core")]


def owner_of(cls):
    for prefix, owner in RULES:
        if cls.startswith(prefix):
            return owner
    return "Other"


def clean_class(cls):
    return cls.split("_Decorated")[0]


def reduce_trace(path):
    start, end, parent, name, task = {}, {}, {}, {}, {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if "startTime" in d:
                i = d["id"]
                start[i], parent[i], name[i] = d["startTime"], d.get("parentId"), d.get("displayName", "")
                det = d.get("details") or {}
                if "taskPath" in det and "taskClass" in det:
                    task[i] = (det["buildPath"], det["taskPath"], clean_class(det["taskClass"]))
            elif "endTime" in d:
                end[d["id"]] = d["endTime"]
    main = next((i for i in start if name[i] == "Run main tasks"), None)

    def inside_main(i):
        while i is not None:
            if i == main:
                return True
            i = parent.get(i)
        return False

    root = next(i for i in start if parent[i] is None)
    out = {"source": path.split("/")[-1], "wall_ms": end[root] - start[root],
           "pre_tasks_ms": (start[main] - start[root]) if main else None,
           "main_tasks_ms": (end[main] - start[main]) if main in end else None, "tasks": []}
    for i, (bp, tp, cls) in task.items():
        if i in end:
            out["tasks"].append({"build": bp, "path": tp, "class": cls, "start": start[i] - start[root],
                                 "end": end[i] - start[root], "in_main": inside_main(i)})
    return out


def union_ms(intervals):
    total, cur_s, cur_e = 0, None, None
    for s, e in sorted(intervals):
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return total


def analyse(run):
    res = {"wall_ms": run["wall_ms"], "pre_tasks_ms": run["pre_tasks_ms"], "main_tasks_ms": run["main_tasks_ms"],
           "tasks": len(run["tasks"]), "owners": {}}
    allsum = sum(t["end"] - t["start"] for t in run["tasks"]) or 1
    for o in OWNERS:
        ts = [t for t in run["tasks"] if owner_of(t["class"]) == o]
        s = sum(t["end"] - t["start"] for t in ts)
        res["owners"][o] = {"tasks": len(ts), "sum_ms": s, "share_of_task_sum": s / allsum,
                            "busy_ms": union_ms([(t["start"], t["end"]) for t in ts]),
                            "in_config_phase_ms": sum(t["end"] - t["start"] for t in ts if not t["in_main"])}
    res["task_sum_ms"] = allsum
    res["busy_all_ms"] = union_ms([(t["start"], t["end"]) for t in run["tasks"]])
    return res


def top_classes(runs, n=12):
    acc = {}
    for run in runs:
        for t in run["tasks"]:
            a = acc.setdefault(t["class"], [0, 0])
            a[0] += t["end"] - t["start"]
            a[1] += 1
    k = len(runs)
    return sorted(((c, v[0] / k, v[1] / k) for c, v in acc.items()), key=lambda x: -x[1])[:n]


def med_rng(vals):
    return statistics.median(vals), min(vals), max(vals)


def fmt(vals, scale=1000.0, nd=1):
    m, lo, hi = med_rng(vals)
    return "%.*f (%.*f to %.*f)" % (nd, m / scale, nd, lo / scale, nd, hi / scale)


def report(files, label=""):
    runs = [json.load(open(f)) for f in files]
    an = [analyse(r) for r in runs]
    lines = []
    if label:
        lines.append("### " + label)
    lines.append("Runs: %d. Values are median (min to max) over runs. Seconds unless stated." % len(runs))
    lines.append("")
    lines.append("- Wall time (root build operation): %s s" % fmt([a["wall_ms"] for a in an]))
    pre = [a["pre_tasks_ms"] for a in an if a["pre_tasks_ms"] is not None]
    if pre:
        lines.append("- Before task execution (configuration or configuration-cache load, up to 'Run main tasks'): %s s" % fmt(pre))
    mt = [a["main_tasks_ms"] for a in an if a["main_tasks_ms"] is not None]
    if mt:
        lines.append("- 'Run main tasks' window: %s s" % fmt(mt))
    lines.append("- Tasks recorded: %s; sum of task durations: %s s; time with at least one task running: %s s" % (
        fmt([a["tasks"] for a in an], 1, 0), fmt([a["task_sum_ms"] for a in an]), fmt([a["busy_all_ms"] for a in an])))
    cfg = [sum(o["in_config_phase_ms"] for o in a["owners"].values()) for a in an]
    lines.append("- Task time spent in included builds during configuration (build-logic compile): %s s" % fmt(cfg))
    lines.append("")
    lines.append("| Owner | Tasks | Sum of task time, s | Share of task sum | Busy wall time, s (union) | Busy as share of wall |")
    lines.append("|---|---|---|---|---|---|")
    for o in OWNERS:
        d = [a["owners"][o] for a in an]
        if not any(x["tasks"] for x in d):
            continue
        sh = [x["share_of_task_sum"] * 100 for x in d]
        bw = [x["busy_ms"] / a["wall_ms"] * 100 for x, a in zip(d, an)]
        lines.append("| %s | %s | %s | %s %% | %s | %s %% |" % (
            o, fmt([x["tasks"] for x in d], 1, 0), fmt([x["sum_ms"] for x in d]), fmt(sh, 1, 1),
            fmt([x["busy_ms"] for x in d]), fmt(bw, 1, 1)))
    lines.append("")
    lines.append("Top task classes by mean summed time per run:")
    lines.append("")
    lines.append("| Task class | Owner | Mean sum, s | Mean count |")
    lines.append("|---|---|---|---|")
    for c, ms, n in top_classes(runs):
        lines.append("| `%s` | %s | %.1f | %.0f |" % (c, owner_of(c), ms / 1000, n))
    return "\n".join(lines), {"files": files, "per_run": an}


def main(argv):
    if len(argv) >= 4 and argv[1] == "reduce":
        json.dump(reduce_trace(argv[2]), open(argv[3], "w"), separators=(",", ":"))
        return 0
    if len(argv) >= 3 and argv[1] == "report":
        args, label, out = argv[2:], "", None
        if "--label" in args:
            i = args.index("--label"); label = args[i + 1]; del args[i:i + 2]
        if "--json" in args:
            i = args.index("--json"); out = args[i + 1]; del args[i:i + 2]
        text, data = report(args, label)
        print(text)
        if out:
            json.dump(data, open(out, "w"), indent=1)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
