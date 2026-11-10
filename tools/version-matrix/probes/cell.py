"""Run every probe that reads a finished cell's files; used by the harness report step.

Inputs are the cell directory contents the runner leaves behind: configuration-cache-report.html (copied from the
workspace after the tasks ran) and the step logs. Missing input is "inconclusive" with a reason, never "pass".
The Gradle deprecation probe reads the first task step's log (configuration-time deprecations show up there)."""
import os

from . import configuration_cache, deprecations, result


def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def run(res):
    d = res.get("dir") or ""
    out = {}
    p = os.path.join(d, "configuration-cache-report.html")
    if os.path.isfile(p):
        out["configuration_cache"] = configuration_cache.parse(_read(p))
    else:
        out["configuration_cache"] = result("inconclusive", "no configuration cache report was collected for this cell")
    task_steps = [s for s in res.get("steps", []) if s.get("role") == "task"]
    log = task_steps[0].get("log") if task_steps else None
    if log and os.path.isfile(log):
        out["deprecations"] = deprecations.parse(_read(log))
    else:
        out["deprecations"] = result("inconclusive", "no task log for this cell (the build did not reach the tasks)")
    return out
