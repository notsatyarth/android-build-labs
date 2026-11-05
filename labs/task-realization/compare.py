#!/usr/bin/env python3
"""Check the task-realization hypotheses against the logs written by run.py.

The hypotheses come from Gradle 9.7.1/9.8.2 source and docs and from a plain-Gradle harness check; this lab
has no macOS run to compare with, so each line states the expectation and whether the CI run agrees.
Verdicts: AGREES, DIFFERS, MISSING (scenario did not run or produced no trace). Exit code 0 always:
a DIFFERS line is a finding, not a harness failure.
Usage: compare.py LOGS_DIR [--markdown]
"""
import json
import os
import statistics
import sys


def load(logs, name):
    p = os.path.join(logs, name + ".json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def cfg(r):
    return (r or {}).get("configuration_phase", {}).get("realized")


def main():
    logs = sys.argv[1]
    md = "--markdown" in sys.argv
    S = {n[:-5]: load(logs, n[:-5]) for n in os.listdir(logs) if n.endswith(".json") and n != "timing.json"}
    g = S.get
    rows = []

    def check(hid, claim, fn, detail):
        try:
            ok = fn()
            v = "AGREES" if ok else "DIFFERS"
        except (TypeError, KeyError, ZeroDivisionError, AttributeError):
            v, ok = "MISSING", None
        try:
            d = detail()
        except (TypeError, KeyError, AttributeError, ZeroDivisionError):
            d = "-"
        rows.append((hid, claim, v, d))

    b = g("help-miss")
    check("T1", "help: most registered tasks are never realized",
          lambda: b["realized"] < 0.1 * b["registered"],
          lambda: "registered %d, realized %d (configuration phase %d, by owner %s)" % (
              b["registered"], b["realized"], cfg(b), b["configuration_phase"]["by_owner"]))
    h = g("help-hit")
    check("T2", "configuration cache hit: nothing registered, every realization carries eager=true",
          lambda: h["registered"] == 0 and h["realized"] == h["realized_eager_flag"] and h["cc_reused"],
          lambda: "registered %d, realized %d, eager flag %d, cc reused %s" % (
              h["registered"], h["realized"], h["realized_eager_flag"], h["cc_reused"]))
    dm, dh = g("dryrun-miss"), g("dryrun-hit")
    check("T3", "dry run of :app:assembleDemoDebug: a hit reports all graph tasks as eager realizations",
          lambda: dh["realized_eager_flag"] == dh["realized"] > int(os.environ.get("LAB_MIN_GRAPH", "100")) and dh["registered"] == 0,
          lambda: "miss: realized %d (eager flag %d, phases %s); hit: realized %d (eager flag %d)" % (
              dm["realized"], dm["realized_eager_flag"], dm["by_phase"], dh["realized"], dh["realized_eager_flag"]))
    app = os.environ.get("LAB_APP", ":app")
    t = g("app-tasks-all")
    check("T4", ":app:tasks --all realizes every task registered in :app",
          lambda: t["realized_by_project"][app] >= t["registered_by_project"][app],
          lambda: ":app registered %d, realized %d; whole build realized %d" % (
              t["registered_by_project"][app], t["realized_by_project"][app], t["realized"]))
    e, l = g("eager-withtype"), g("lazy-withtype")
    check("E1", "Kotlin DSL tasks.withType<JavaCompile> { } (no configureEach) realizes JavaCompile tasks in every project",
          lambda: cfg(e) > cfg(b),
          lambda: "configuration-phase realizations %d vs baseline %d (+%d; triggers %s)" % (
              cfg(e), cfg(b), cfg(e) - cfg(b), e["configuration_phase"]["by_trigger"]))
    check("E2", "tasks.withType<JavaCompile>().configureEach { } realizes nothing extra",
          lambda: cfg(l) == cfg(b),
          lambda: "configuration-phase realizations %d vs baseline %d" % (cfg(l), cfg(b)))
    m = g("matching")
    check("E3", "tasks.matching { name == ... }.configureEach { } realizes nothing extra (docs: matching() needs all tasks created)",
          lambda: cfg(m) == cfg(b),
          lambda: "configuration-phase realizations %d vs baseline %d" % (cfg(m), cfg(b)))
    a = g("all")
    check("E4", "tasks.all { } realizes (almost) every registered task during configuration",
          lambda: cfg(a) >= 0.9 * a["registered"],
          lambda: "configuration-phase realizations %d of %d registered; build exit %d %s" % (
              cfg(a), a["registered"], a["exit"], ("(" + a["what_went_wrong"].replace("\n", " ")[:160] + ")") if a["exit"] else ""))
    bw, cw = g("baseline-warnfail"), g("create-warnfail")
    check("W1", "tasks.create(...) (@Deprecated in the API) adds no run-time deprecation: --warning-mode=fail behaves as baseline",
          lambda: cw["exit"] == bw["exit"] and not (set(cw["deprecation_lines"]) - set(bw["deprecation_lines"]) - {
              x for x in cw["deprecation_lines"] if x.startswith("w: ")}),
          lambda: "baseline exit %d, with create exit %d; Kotlin compiler warning printed: %s" % (
              bw["exit"], cw["exit"], cw["kotlin_deprecation_warning"]))
    rw = g("registering-warnfail")
    check("W2", "the lazy delegate 'by tasks.registering' fails --warning-mode=fail (deprecated in Gradle 9.6)",
          lambda: rw["exit"] != 0 and rw["deprecation_failure"] and bw["exit"] == 0,
          lambda: "exit %d, deprecation failure %s (baseline exit %d)" % (rw["exit"], rw["deprecation_failure"], bw["exit"]))
    bl, bt, be = g("broken-lazy-help"), g("broken-lazy-tasks"), g("broken-eager-help")
    check("F1", "a registered task with a throwing configuration action does not fail help",
          lambda: bl["exit"] == 0, lambda: "exit %d" % bl["exit"])
    check("F2", "... but fails as soon as something realizes it (:core:data:tasks --all)",
          lambda: bt["exit"] != 0 and bt["labBroken_error"], lambda: "exit %d: %s" % (bt["exit"], bt["what_went_wrong"][:160]))
    check("F3", "the same action on an eagerly created task fails every build, help included",
          lambda: be["exit"] != 0 and be["labBroken_error"], lambda: "exit %d" % be["exit"])
    se, sa = g("side-effect"), g("side-effect-plus-all")
    check("S1", "docs antipattern: check.get().dependsOn(this) inside labVerify's own action; check does not run labVerify",
          lambda: se["exit"] == 0 and not se["labVerify_in_graph"],
          lambda: "exit %d, labVerify in :core:data:check graph: %s" % (se["exit"], se["labVerify_in_graph"]))
    check("S2", "one unrelated eager line (tasks.all { }) in the same project makes check run labVerify",
          lambda: sa["exit"] == 0 and sa["labVerify_in_graph"],
          lambda: "exit %d, labVerify in graph: %s, error: %s" % (
              sa["exit"], sa["labVerify_in_graph"], sa["what_went_wrong"][:120] or "-"))
    td, to = g("tapi-default"), g("tapi-omit")
    check("I1", "Tooling API GradleProject model (IDE sync) realizes every task of every project",
          lambda: td["realized"] >= 0.95 * td["registered"] and td["model_tasks_listed"] > 0,
          lambda: "registered %d, realized %d, tasks listed in the model %d, projects %d" % (
              td["registered"], td["realized"], td["model_tasks_listed"], td["model_projects"]))
    check("I2", "with -Dorg.gradle.internal.GradleProjectBuilderOptions=omit_all_tasks (Android Studio) it realizes none",
          lambda: to["by_phase"].get("tooling-model", 0) == 0 and to["model_tasks_listed"] == 0,
          lambda: "realized %d (phases %s), tasks listed %d" % (to["realized"], to["by_phase"], to["model_tasks_listed"]))

    # follow-ups (bead droidcon-led, 2026-11-05)
    ma = g("matching-all")
    check("E5", "tasks.matching { name == ... }.all { } (eager consumer) realizes (almost) every task: the docs' warning holds here",
          lambda: cfg(ma) >= 0.9 * ma["registered"],
          lambda: "configuration-phase realizations %d of %d registered; build exit %d" % (cfg(ma), ma["registered"], ma["exit"]))
    w = g("who-dryrun")

    def chains(prefix_re):
        import re as _re
        out = []
        for line in (w or {}).get("realized_by", []):
            path, _, frames = line.partition(" | ")
            if _re.fullmatch(prefix_re, path.strip().rsplit(":", 1)[-1]):
                out.append(frames)
        return out
    cl = chains("clean")
    check("R1", "Gradle core realizes clean in every project: LifecycleBasePlugin registers clean's targets with the build output cleanup registry, resolved when the task graph is finalized",
          lambda: len(cl) >= 30 and all("DefaultBuildOutputCleanupRegistry.resolveOutputs" in c for c in cl),
          lambda: "%d clean realizations, %d via DefaultBuildOutputCleanupRegistry.resolveOutputs" % (
              len(cl), sum("DefaultBuildOutputCleanupRegistry.resolveOutputs" in c for c in cl)))
    lint = chains(r"(generate\w*LintModel|lintAnalyze\w*|lintVitalAnalyze\w*|generate\w*LintVitalModel|write\w*LintModelMetadata|bundle\w*LocalLintAar|prepareLintJarForPublish)")
    check("R2", "the lint-related tasks realized but not scheduled are realized from AGP code (first non-Gradle frame is com.android.*)",
          lambda: len(lint) > 0 and sum(any(f.startswith("com.android.") for f in c.split(" < ")) for c in lint) >= 0.9 * len(lint),
          lambda: "%d lint-related realizations traced, %d with a com.android frame" % (
              len(lint), sum(any(f.startswith("com.android.") for f in c.split(" < ")) for c in lint)))
    ks = chains("kspKotlin|kspTestKotlin")
    check("R3", "(informational) who realizes :core:common:kspKotlin during configuration: a KSP or KGP frame is on the stack",
          lambda: len(ks) > 0 and any(("com.google.devtools.ksp" in c) or ("org.jetbrains.kotlin" in c) for c in ks),
          lambda: "%d traced; KSP frame: %s; KGP frame: %s" % (
              len(ks), any("com.google.devtools.ksp" in c for c in ks), any("org.jetbrains.kotlin" in c for c in ks)))
    at = g("all-stacktrace")
    check("D1", "(informational) tasks.all { } fails in Dependency Guard; the root cause is printed by details.py",
          lambda: at["exit"] != 0 and any("dropbox" in l.lower() or "dependency" in l.lower() for l in at["caused_by"] + [at["what_went_wrong"]]),
          lambda: (at["caused_by"][-1] if at["caused_by"] else at["what_went_wrong"])[:220].replace("\n", " "))

    # Cross-check with a measured macOS result: samples/nia-variants (nowinandroid 2982e63, Gradle 9.7.1, AGP 9.3.2,
    # Apple M1) counted tasks.names per project: 13135 in all projects (the root build and build-logic both print
    # ":"), 1126 in :app. Same commit and versions, so :app should match exactly; the total may differ by the
    # build-logic root and by tasks registered only with isolated projects off.
    exp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "samples", "nia-variants", "expected.json")
    if os.path.exists(exp_path) and not os.environ.get("LAB_APP"):
        with open(exp_path) as f:
            ex = json.load(f)
        check("X1", "registered tasks in :app equal the macOS count of the nia-variants lab",
              lambda: b["registered_by_project"][":app"] == ex["app_tasks_all"],
              lambda: ":app registered %d here, %d on macOS" % (b["registered_by_project"][":app"], ex["app_tasks_all"]))
        check("X2", "registered tasks in the whole build within 2% of the macOS count (informational)",
              lambda: abs(b["registered"] - ex["tasks_all"]) <= 0.02 * ex["tasks_all"],
              lambda: "%d here (main build), %d on macOS (all projects incl. build-logic root)" % (b["registered"], ex["tasks_all"]))

    tp = os.path.join(logs, "timing.json")
    timing_line = None
    if os.path.exists(tp):
        with open(tp) as f:
            tm = json.load(f)
        med = {k: statistics.median([x for x in v if x is not None]) for k, v in tm.items() if any(x is not None for x in v)}
        timing_line = "Configure build, median ms (CI x86 Linux runner, configuration cache cleared each run, n=%d): %s" % (
            max(len(v) for v in tm.values()), ", ".join("%s %d" % (k, v) for k, v in med.items()))

    if md:
        print("| ID | Hypothesis | Verdict | Measured |\n|---|---|---|---|")
        for r in rows:
            print("| %s | %s | %s | %s |" % tuple(x.replace("|", "/") for x in r))
        if timing_line:
            print("\n" + timing_line)
    else:
        for r in rows:
            print("%-3s %-8s %s\n      %s" % (r[0], r[2], r[1], r[3]))
        if timing_line:
            print(timing_line)


if __name__ == "__main__":
    main()
