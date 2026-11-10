"""Configuration cache probe: read build/reports/configuration-cache/<h>/<h>/configuration-cache-report.html.

The report embeds its data as JSON between '// begin-report-data' and '// end-report-data' (format seen on
Gradle 9.7.1 in nowinandroid CI output; labs/capture-samples; Gradle 8.11.1 has the same layout without
uniqueProblemCount and overflownProblemCount). The format is not a public API, so every
structural surprise gives "inconclusive" with the reason, never "pass".
"""
import json

from . import result

BEGIN, END = "// begin-report-data", "// end-report-data"
REQUIRED = ("totalProblemCount", "cacheAction", "diagnostics")   # uniqueProblemCount is absent on Gradle 8.11.1


def load_data(html):
    a, b = html.find(BEGIN), html.find(END)
    if a < 0 or b < 0 or b < a:
        raise ValueError("report data markers not found")
    blob = html[a + len(BEGIN):b].strip().rstrip(" )\n;")
    data = json.loads(blob)
    if not isinstance(data, dict):
        raise ValueError("report data is not an object")
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise ValueError("report data lacks " + ", ".join(missing))
    return data


def _text(parts):
    """Join a list of {text|name|internalText: ...} fragments into one string."""
    out = []
    for x in parts or []:
        if isinstance(x, dict):
            out.append(x.get("text") or x.get("name") or "")
    return "".join(out).strip()


def _trace(trace):
    """Who the problem is attached to: the first trace entry, as 'kind: identifier'."""
    if not trace or not isinstance(trace, list) or not isinstance(trace[0], dict):
        return None, None
    t = trace[0]
    ident = t.get("path") or t.get("type") or t.get("location") or t.get("name")
    return t.get("kind"), ident


def problems(data):
    """One entry per diagnostic that carries a problem. Fields are best effort; absent ones are None."""
    out = []
    for x in data.get("diagnostics", []):
        if not isinstance(x, dict) or not x.get("problem"):
            continue
        kind, ident = _trace(x.get("trace"))
        err = x.get("error") or {}
        out.append({"message": _text(x["problem"]), "origin_kind": kind, "origin": ident,
                    "location": _text(err.get("summary")) or None, "doc": x.get("documentationLink")})
    return out


def parse(html):
    try:
        d = load_data(html)
    except (ValueError, TypeError) as e:
        return result("inconclusive", "cannot read configuration cache report: %s" % e)
    total, unique = d["totalProblemCount"], d.get("uniqueProblemCount")
    if not isinstance(total, int) or not (unique is None or isinstance(unique, int)):
        return result("inconclusive", "problem counts are not numbers")
    base = {"total_problems": total, "unique_problems": unique, "cache_action": d["cacheAction"],
            "requested_tasks": d.get("requestedTasks")}
    if total == 0:
        return result("pass", None, problems=[], **base)
    found = problems(d)
    if not found:
        # the report says there are problems but we cannot see any: format change, do not guess
        return result("inconclusive", "report counts %d problem(s) but none could be read" % total, **base)
    return result("fail", "%d configuration cache problem(s)" % total, problems=found, **base)
