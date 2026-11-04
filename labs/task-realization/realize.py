#!/usr/bin/env python3
"""Count task registrations and realizations in a Gradle build operation trace, and say who caused them.

Input: PREFIX-log.txt written by `-Dorg.gradle.internal.operations.trace=PREFIX` (internal Gradle format,
JSON lines; may change between Gradle versions). Checked against Gradle 9.7.1.

Gradle records:
  "Register task :p:x"  (RegisterTaskBuildOperationType)  task known, object not created
  "Realize task :p:x"   (RealizeTaskBuildOperationType)   task object created and configured;
                         details.eager = true when created by an eager API (create, task x {}),
                         and also for every task loaded from the configuration cache (Gradle's own test
                         ConfigurationCacheTaskRealizationBuildOperationIntegrationTest asserts eager == true on load).
For each realization the script records:
  phase:  configuration | task-graph | cc-store | cc-load | tooling-model | execution | other
          (from the nearest enclosing operation with a known name)
  context: the nearest enclosing plugin or script application ("Apply plugin X", "Apply build file", ...),
          resolved through the applicationId of container callbacks. This is WHERE it happened, not always who
          asked: an eager all/withType {} subscription realizes each task inside the plugin call that registers it.
  trigger: at-registration (an earlier eager subscription fired when the task was registered),
           cascade:<task> (inside the configuration of another task), or direct.
  Who subscribed is not in the trace; the lab attributes injected patterns by difference against a baseline.
Usage:
  realize.py summary TRACE-log.txt [--json OUT.json] [--label TEXT]
Standard library only.
"""
import collections
import json
import re
import sys

PHASES = [  # first match walking up from the realization wins
    ("Load configuration cache state", "cc-load"),
    ("Load configuration cache", "cc-load"),
    ("Store configuration cache state", "cc-store"),
    ("Calculate task graph", "task-graph"),
    ("Calculate build tree task graph", "task-graph"),
    ("Build model", "tooling-model"),
    ("Fetch model", "tooling-model"),
    ("Run main tasks", "execution"),
    ("Run tasks", "execution"),
    ("Configure project", "configuration"),
    ("Configure build", "configuration"),
    ("Apply initialization script", "configuration"),
    ("Apply settings file", "configuration"),
]


def short_plugin(det, display):
    pid = det.get("pluginId")
    cls = det.get("pluginClass") or ""
    if pid:
        return pid
    if cls:
        return cls.split("$")[0]
    return display


def owner_of(name):
    n = name.lower()
    for key, owner in (("com.android", "AGP"), ("com.google.devtools.ksp", "KSP"), ("org.jetbrains.kotlin", "KGP"),
                       ("dagger.hilt", "Hilt"), ("org.gradle", "Gradle core"), ("kotlin", "KGP"),
                       ("initialization script", "init script (lab)"), ("init.gradle", "init script (lab)"),
                       ("build file", "build script"), ("script", "script"), ("nowinandroid", "build-logic")):
        if key in n:
            return owner
    return "other plugin"


def load(path):
    ops = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if "startTime" in d:
                ops[d["id"]] = {"parent": d.get("parentId"), "name": d.get("displayName", ""),
                                "details": d.get("details") or {}, "cls": d.get("detailsClassName", ""),
                                "start": d["startTime"]}
            elif "endTime" in d and d.get("id") in ops:
                ops[d["id"]]["end"] = d["endTime"]
    return ops


def summarize(ops):
    apps = {}  # applicationId -> description of the plugin or script
    for o in ops.values():
        det = o["details"]
        if "applicationId" in det and (o["name"].startswith("Apply ") or "pluginClass" in det):
            if o["name"].startswith("Apply plugin"):
                apps[det["applicationId"]] = short_plugin(det, o["name"])
            else:
                apps[det["applicationId"]] = re.sub(r" to (root )?project.*$", "", o["name"])
    registered, realized = {}, []
    for i, o in sorted(ops.items()):
        n = o["name"]
        if n.startswith("Register task "):
            registered[o["details"].get("taskPath", n[14:]) + "@" + str(o["details"].get("buildPath", ":"))] = i
        elif n.startswith("Realize task ") or "RealizeDetails" in o["cls"]:
            det = o["details"]
            phase, context, trigger = "other", None, None
            j = o["parent"]
            first = True
            while j is not None and j in ops:
                p = ops[j]
                pn, pdet = p["name"], p["details"]
                if trigger is None:
                    if first and pn.startswith("Register task "):
                        trigger = "at-registration"  # an earlier all/withType {}/whenTaskAdded subscription fired
                    elif pn.startswith("Realize task ") or "RealizeDetails" in p["cls"]:
                        trigger = "cascade:" + str(pdet.get("taskPath"))
                first = False
                if context is None:
                    if pn.startswith("Apply plugin"):
                        context = short_plugin(pdet, pn)
                    elif pn.startswith("Apply ") and ("script" in pn or "build file" in pn):
                        context = re.sub(r" to (root )?project.*$", "", pn)
                    elif "applicationId" in pdet and pdet["applicationId"] in apps:
                        context = apps[pdet["applicationId"]]
                if phase == "other":
                    for prefix, ph in PHASES:
                        if pn.startswith(prefix):
                            phase = ph
                            break
                j = p["parent"]
            path = det.get("taskPath", n[13:])
            realized.append({"task": path, "project": path.rsplit(":", 1)[0] or ":", "eager": bool(det.get("eager")),
                             "phase": phase, "context": context or "(Gradle itself)", "trigger": trigger or "direct",
                             "build": det.get("buildPath", ":")})
    build_logic = [r for r in realized if r["build"] not in (":",)]
    main = [r for r in realized if r["build"] == ":"]
    reg_main = [k for k in registered if k.endswith("@:")]
    conf = [r for r in main if r["phase"] == "configuration"]
    out = {
        "registered": len(reg_main),
        "realized": len(main),
        "realized_eager_flag": sum(r["eager"] for r in main),
        "by_phase": dict(collections.Counter(r["phase"] for r in main)),
        "configuration_phase": {
            "realized": len(conf),
            "eager_flag": sum(r["eager"] for r in conf),
            "by_trigger": dict(collections.Counter(r["trigger"].split(":")[0] for r in conf).most_common()),
            "by_owner": dict(collections.Counter(owner_of(r["context"]) for r in conf).most_common()),
            "by_context": dict(collections.Counter(r["context"] for r in conf).most_common(15)),
            "by_project": dict(collections.Counter(r["project"] for r in conf).most_common(10)),
            "sample": sorted({r["task"] for r in conf})[:25],
        },
        "registered_by_project": dict(collections.Counter((k.split("@")[0].rsplit(":", 1)[0] or ":") for k in reg_main)),
        "realized_by_project": dict(collections.Counter(r["project"] for r in main)),
        "included_builds_realized": len(build_logic),
        "configure_build_ms": None,
    }
    for o in ops.values():
        if o["name"] == "Configure build" and "end" in o:
            out["configure_build_ms"] = o["end"] - o["start"]
            break
    out["_realized"] = main
    return out


def main():
    if len(sys.argv) < 3 or sys.argv[1] != "summary":
        print(__doc__)
        sys.exit(2)
    args = sys.argv[2:]
    jout = args[args.index("--json") + 1] if "--json" in args else None
    label = args[args.index("--label") + 1] if "--label" in args else args[0]
    s = summarize(load(args[0]))
    if jout:
        with open(jout, "w") as f:
            json.dump(s, f, indent=1)
    c = s["configuration_phase"]
    print(f"{label}: registered={s['registered']} realized={s['realized']} (eager flag {s['realized_eager_flag']}) "
          f"phases={s['by_phase']} | configuration phase: realized={c['realized']} triggers={c['by_trigger']} "
          f"owners={c['by_owner']} | Configure build {s['configure_build_ms']} ms")


if __name__ == "__main__":
    main()
