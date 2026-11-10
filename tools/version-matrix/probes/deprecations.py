"""Gradle deprecation probe: read a Gradle console log written with --warning-mode=all (plus --stacktrace).

A deprecation record, as printed by Gradle 9.x:
    The Configuration.setVisible(boolean) method has been deprecated. This is scheduled to be removed in Gradle 11.
    Consult the upgrading guide for further information: <url>
    \tat org.gradle....            (stack frames; the first frame outside org.gradle / java / jdk / kotlin is the origin)
Format seen on Gradle 9.9.0-rc-1 (labs/version-matrix run on nowinandroid). It is console output, not a public API,
so surprises give "inconclusive" with a reason, never "pass".
Two wordings are read: "This is scheduled to be removed in Gradle N" and "This will fail with an error in Gradle N".
The version and wording are what Gradle prints; this probe repeats them and adds nothing. A line that mentions the
upgrading guide and "deprecat" but matches neither wording makes the result inconclusive, so a new wording cannot
produce a false zero.
"""
import re

from . import result

_REC = re.compile(r"^(?P<msg>.*?(?:has been deprecated|have been deprecated|is deprecated|are deprecated)\.)\s*"
                  r"This (?P<what>is scheduled to be removed|will be removed|will fail with an error|will be an error|will become an error)"
                  r" in Gradle (?P<ver>\d+(?:\.\d+)*)\.?\s*(?P<rest>.*)$")
_UPGRADE = re.compile(r"Consult the upgrading guide")
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
    unrecognised = 0
    for i, line in enumerate(lines):
        r = _REC.match(line.strip())
        if not r:
            if _UPGRADE.search(line) and "deprecat" in line.lower():
                unrecognised += 1   # looks like a Gradle deprecation but the wording is new to this parser
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
        g = groups.setdefault(key, {"message": r.group("msg"), "removal": "Gradle " + r.group("ver"), "stated": r.group("what"),
                                    "doc": url.group(0) if url else None, "origin": origin, "count": 0})
        g["count"] += 1
    recs = sorted(groups.values(), key=lambda g: -g["count"])
    total = sum(g["count"] for g in recs)
    if unrecognised:
        return result("inconclusive", "%d line(s) look like Gradle deprecations but were not recognised (new wording?); "
                      "%d recognised" % (unrecognised, total), deprecations=recs, total=total, distinct=len(recs),
                      unrecognised=unrecognised)
    if not recs and _SUMMARY in log:
        return result("inconclusive", "the log says deprecated features were used but prints no details", deprecations=[], total=0)
    if not recs:
        return result("pass", None, deprecations=[], total=0, distinct=0)
    return result("fail", "%d Gradle deprecation message(s), %d distinct" % (total, len(recs)),
                  deprecations=recs, total=total, distinct=len(recs))
