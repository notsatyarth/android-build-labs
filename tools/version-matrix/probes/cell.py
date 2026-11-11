"""Run every probe that reads a finished cell's files; used by the harness report step.

Inputs are the cell directory contents the runner leaves behind: configuration-cache-report.html (copied from the
workspace after the tasks ran) and the step logs. Missing input is "inconclusive" with a reason, never "pass".
The Gradle deprecation probe reads the first task step's log (configuration-time deprecations show up there)."""
import os

from . import configuration_cache, deprecations, result, tool_deprecations


def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def run(res):
    d = res.get("dir") or ""
    out = {}
    task_steps = [s for s in res.get("steps", []) if s.get("role") == "task"]
    p = os.path.join(d, "configuration-cache-report.html")
    if os.path.isfile(p):
        out["configuration_cache"] = configuration_cache.parse(_read(p))
        cc = out["configuration_cache"]
        if cc["state"] == "pass" and not task_steps:
            # The only report is from a guard step (for example buildEnvironment). Zero problems there says nothing
            # about the project's tasks, which never ran. A fail is kept: problems that were found are real.
            out["configuration_cache"] = dict(cc, state="inconclusive",
                                              reason="the build stopped before the project's tasks ran; the report only covers the guard step")
    else:
        out["configuration_cache"] = result("inconclusive", "no configuration cache report was collected for this cell")
    log = task_steps[0].get("log") if task_steps else None
    if log and os.path.isfile(log):
        out["deprecations"] = deprecations.parse(_read(log))
    else:
        out["deprecations"] = result("inconclusive", "no task log for this cell (the build did not reach the tasks)")
    logs = []
    for st in task_steps:
        if st.get("log") and os.path.isfile(st["log"]):
            logs.append(_read(st["log"]))
    out.update(tool_deprecations.parse(logs))
    return out
