"""Gradle deprecation probe: read a Gradle console log written with --warning-mode=all (plus --stacktrace).

A deprecation record, as printed by Gradle 9.x:
    The Configuration.setVisible(boolean) method has been deprecated. This is scheduled to be removed in Gradle 11.
    Consult the upgrading guide for further information: <url>
    \tat org.gradle....            (stack frames; the first frame outside org.gradle / java / jdk / kotlin is the origin)
Format seen on Gradle 9.9.0-rc-1 (labs/version-matrix run on nowinandroid). It is console output, not a public API,
so surprises give "inconclusive" with a reason, never "pass".
The removal version ("Gradle 11") is what Gradle prints; this probe repeats it and adds nothing.
"""
import re

from . import result

_REC = re.compile(r"^(?P<msg>.*?(?:has been deprecated|is deprecated|are deprecated)\.)\s*"
                  r"This (?:is|will be) scheduled to be removed in Gradle (?P<ver>\d+(?:\.\d+)*)\.?\s*(?P<rest>.*)$")
_FRAME = re.compile(r"^\tat (?P<cls>[\w.$]+)\.(?P<method>[\w$<>]+)\((?P<src>[^)]*)\)")
_URL = re.compile(r"https?://\S+")
_SKIP = ("org.gradle.", "java.", "jdk.", "kotlin.", "groovy.", "org.codehaus.groovy.", "sun.")
_END = re.compile(r"^BUILD (SUCCESSFUL|FAILED)", re.M)
_SUMMARY = "Deprecated Gradle features were used in this build"
_WARNING_MODE = re.compile(r"--warning-mode[= ](\w+)")


def parse(log):
    if not log or not _END.search(log):
        return result("inconclusive", "no 'BUILD SUCCESSFUL' or 'BUILD FAILED' line: not a complete Gradle log")
    head = next((l for l in log.splitlines()[:3] if l.startswith("# cmd:")), "")
    m = _WARNING_MODE.search(head)
    if m and m.group(1) not in ("all", "fail"):
        return result("inconclusive", "run with --warning-mode=%s: details are not printed" % m.group(1))
    lines = log.splitlines()
    groups = {}
    for i, line in enumerate(lines):
        r = _REC.match(line.strip())
        if not r:
            continue
        url = _URL.search(r.group("rest"))
        origin = None
        for nxt in lines[i + 1:i + 80]:
            if not nxt.startswith("\t"):
                if nxt.strip():
                    break
                continue
            f = _FRAME.match(nxt)
            if f and not f.group("cls").startswith(_SKIP):
                origin = {"class": f.group("cls"), "at": f.group("src")}
                break
        key = (r.group("msg"), origin["class"] if origin else None)
        g = groups.setdefault(key, {"message": r.group("msg"), "removal": "Gradle " + r.group("ver"),
                                    "doc": url.group(0) if url else None, "origin": origin, "count": 0})
        g["count"] += 1
    recs = sorted(groups.values(), key=lambda g: -g["count"])
    total = sum(g["count"] for g in recs)
    if not recs and _SUMMARY in log:
        return result("inconclusive", "the log says deprecated features were used but prints no details", deprecations=[], total=0)
    if not recs:
        return result("pass", None, deprecations=[], total=0, distinct=0)
    return result("fail", "%d Gradle deprecation message(s), %d distinct" % (total, len(recs)),
                  deprecations=recs, total=total, distinct=len(recs))
