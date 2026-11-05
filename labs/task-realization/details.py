#!/usr/bin/env python3
"""Print the evidence behind compare.py's verdicts from run.py's logs, so it can be read in the job log:
errors, deprecation lines, which tasks were realized during configuration and by what, and which tasks a
dry run realizes without scheduling them. Usage: details.py LOGS_DIR"""
import collections
import json
import os
import re
import sys

logs = sys.argv[1]


def load(n):
    p = os.path.join(logs, n + ".json")
    return json.load(open(p)) if os.path.exists(p) else None


def kind(task):  # task name without variant words, for grouping
    name = task.rsplit(":", 1)[-1]
    return re.sub(r"(Demo|Prod)?(Debug|Release|BenchmarkRelease|NonMinifiedRelease|Benchmark|NonMinified)"
                  r"(UnitTest|AndroidTest|ScreenshotTest)?", "<V>", name)


def console_tail(n, pattern):
    p = os.path.join(logs, n + ".console")
    if not os.path.exists(p):
        return []
    return [l.rstrip() for l in open(p, errors="replace") if re.search(pattern, l)][:12]


for n in sorted(f[:-5] for f in os.listdir(logs) if f.endswith(".json") and f != "timing.json"):
    r = load(n)
    print("==", n, "exit", r.get("exit"))
    if r.get("what_went_wrong"):
        print("   error:", r["what_went_wrong"].replace("\n", " | ")[:400])
    if n.endswith("warnfail"):
        for l in r.get("deprecation_lines", [])[:8]:
            print("   deprecation:", l)
    c = r.get("configuration_phase") or {}
    if c.get("realized"):
        print("   configuration phase: %d realized; by context %s" % (c["realized"], c.get("by_context")))
        conf = [x for x in r.get("_realized", []) if x["phase"] == "configuration"]
        print("   by task kind:", dict(collections.Counter(kind(x["task"]) for x in conf).most_common(12)))
        print("   by project:", dict(collections.Counter(x["project"] for x in conf).most_common(6)))
        print("   first:", [x["task"] for x in conf][:6])

for n in ("dryrun-miss", "side-effect"):
    r = load(n)
    if not r:
        continue
    real = r["_realized"]
    scheduled = {x["task"] for x in real if x["phase"] == "cc-load"}
    graph_only = [x for x in real if x["phase"] == "task-graph" and x["task"] not in scheduled]
    print("== %s: %d realized while building the task graph, %d scheduled (loaded from the entry), "
          "%d realized but not scheduled" % (n, sum(1 for x in real if x["phase"] == "task-graph"), len(scheduled),
                                             len(graph_only)))
    print("   not scheduled, by task kind:", dict(collections.Counter(kind(x["task"]) for x in graph_only).most_common(15)))
    print("   not scheduled, by trigger:", dict(collections.Counter(x["trigger"].split(":")[0] for x in graph_only)))
    cas = collections.Counter(kind(x["trigger"].split(":", 1)[1]) for x in graph_only if x["trigger"].startswith("cascade"))
    print("   cascades from:", dict(cas.most_common(10)))
    cs = [x for x in real if x["phase"] == "cc-store"]
    print("   realized while storing the entry:", dict(collections.Counter(kind(x["task"]) for x in cs).most_common(8)))

for n in ("all",):
    print("== %s console:" % n)
    for l in console_tail(n, r"What went wrong|^> |Exception|failed|FAILED"):
        print("  ", l[:300])


# ---- follow-ups (bead droidcon-led) ----
def frame_owner(chain):
    """Owner of a realization: the first stack frame outside Gradle, else Gradle core."""
    for f in chain:
        if not f.startswith("org.gradle."):
            for key, owner in (("com.android.", "AGP"), ("com.google.devtools.ksp", "KSP"), ("org.jetbrains.kotlin", "KGP"),
                               ("dagger.hilt", "Hilt"), ("com.dropbox", "Dependency Guard")):
                if f.startswith(key):
                    return owner + " (" + f + ")"
            return "other (" + f + ")"
    return "Gradle core"


w = load("who-dryrun")
if w:
    print("== who-dryrun: %d traced realizations" % len(w.get("realized_by", [])))
    by_kind = collections.defaultdict(list)
    for line in w.get("realized_by", []):
        path, _, frames = line.partition(" | ")
        by_kind[kind(path.strip())].append(frames.split(" < "))
    for k, chains in sorted(by_kind.items(), key=lambda kv: -len(kv[1])):
        owners = collections.Counter(frame_owner(c).split(" (")[0] for c in chains)
        top = collections.Counter(" < ".join(c[:5]) for c in chains).most_common(1)[0]
        print("   %-34s n=%-4d owners=%s" % (k, len(chains), dict(owners)))
        print("      first owner frame: %s" % frame_owner(chains[0]))
        print("      most common caller (%d): %s" % (top[1], top[0][:600]))
        full = collections.Counter(" < ".join(c) for c in chains).most_common(1)[0][0]
        print("      full chain of one sample: %s" % full[:3500])

a = load("all-stacktrace")
if a:
    print("== all-stacktrace exit %s" % a.get("exit"))
    for l in a.get("caused_by", []):
        print("   ", l)
    for l in console_tail("all-stacktrace", r"dropbox|dependencyguard|DependencyGuard")[:12]:
        print("    frame:", l.strip()[:250])
