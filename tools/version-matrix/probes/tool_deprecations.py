"""AGP and Kotlin compiler deprecation probe: reads the task logs of a build, not Gradle's own deprecation records.

Two feature checks, each with its own state:
  agp_deprecations     console blocks "WARNING: ... is deprecated." printed by the Android Gradle plugin. The following
                       lines may say "It will be removed in version N of the Android Gradle plugin"; that sentence is
                       copied, never inferred.
  kotlin_deprecations  compiler warnings "w: <file>:<line>:<col> '<symbol>' is deprecated. ..." (or any "w:" line that
                       mentions "deprecat"). These are mostly deprecated library APIs that the project's own source
                       calls, so the place to fix is a source location, not a Gradle setting.
Console output is not a public API. A log without a "BUILD SUCCESSFUL" or "BUILD FAILED" line is inconclusive. A build
that never ran a Kotlin compile task gives kotlin "not_run", because no compiler warning could have been printed.
Same warning in several logs of one build (configuration output repeats) is counted once per log, at the highest count.
"""
import re

from . import result

_END = re.compile(r"^BUILD (SUCCESSFUL|FAILED)", re.M)
_AGP = re.compile(r"^WARNING: (?P<msg>.*(?:deprecat|will be removed).*)$", re.I)
_AGP_REMOVAL = re.compile(r"(?:It )?will be removed in version (?P<ver>[\d.]+) of the Android Gradle plugin", re.I)
_KW = re.compile(r"^w: (?:file://(?P<path>[^\s]+?):(?P<line>\d+):(?P<col>\d+) )?(?P<msg>.*)$")
_SYMBOL = re.compile(r"^(?P<sym>'[^']*'|\S.*?) is deprecated\b", re.I)
_KOTLIN_TASK = re.compile(r"^> Task \S*compile\S*Kotlin\S*", re.M)


def _agp(lines):
    out = {}
    for i, line in enumerate(lines):
        m = _AGP.match(line.strip())
        if not m:
            continue
        removal = None
        for nxt in lines[i + 1:i + 5]:
            r = _AGP_REMOVAL.search(nxt)
            if r:
                removal = "AGP " + r.group("ver")
                break
            if not nxt.strip() or nxt.startswith(("WARNING:", ">")):
                break
        g = out.setdefault(m.group("msg"), {"message": m.group("msg"), "removal": removal, "count": 0})
        g["count"] += 1
    return out


def _kotlin(lines):
    out = {}
    for line in lines:
        m = _KW.match(line)
        if not m or "deprecat" not in m.group("msg").lower():
            continue
        s = _SYMBOL.match(m.group("msg"))
        sym = (s.group("sym") if s else m.group("msg"))[:200]
        path = m.group("path")
        where = None
        if path:
            where = path.rsplit("/", 1)[-1] + ":" + m.group("line")
        key = (sym, where)
        g = out.setdefault(key, {"symbol": sym, "location": where, "message": m.group("msg")[:300], "count": 0})
        g["count"] += 1
    return out


def parse(logs):
    """logs: list of console log texts from one build. Returns {"agp_deprecations": result, "kotlin_deprecations": result}."""
    logs = [l for l in logs if l]
    if not logs or not any(_END.search(l) for l in logs):
        why = "no complete Gradle log (no 'BUILD SUCCESSFUL' or 'BUILD FAILED' line)"
        return {"agp_deprecations": result("inconclusive", why), "kotlin_deprecations": result("inconclusive", why)}
    agp, kt = {}, {}
    for l in logs:
        lines = l.splitlines()
        for k, g in _agp(lines).items():
            if k not in agp or g["count"] > agp[k]["count"]:
                agp[k] = g
        for k, g in _kotlin(lines).items():
            if k not in kt or g["count"] > kt[k]["count"]:
                kt[k] = g
    a = sorted(agp.values(), key=lambda g: -g["count"])
    k = sorted(kt.values(), key=lambda g: (-g["count"], g["location"] or ""))
    ra = (result("fail", "%d AGP deprecation warning(s)" % len(a), deprecations=a, total=sum(g["count"] for g in a), distinct=len(a))
          if a else result("pass", None, deprecations=[], total=0, distinct=0))
    if not any(_KOTLIN_TASK.search(l) for l in logs):
        rk = result("not_run", "no Kotlin compile task ran in these logs, so the compiler printed no warnings")
    elif k:
        rk = result("fail", "%d Kotlin deprecation warning(s)" % len(k), deprecations=k, total=sum(g["count"] for g in k), distinct=len(k))
    else:
        rk = result("pass", None, deprecations=[], total=0, distinct=0)
    return {"agp_deprecations": ra, "kotlin_deprecations": rk}
