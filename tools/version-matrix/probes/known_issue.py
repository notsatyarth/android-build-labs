"""Known-issue probe: does a published repro still fail the way the issue says, on a given tool version?

Reads the console log of the repro command. States:
  fail          the build failed and the log contains the issue's signature: the issue reproduces on this version
  pass          the build succeeded: the issue does not reproduce on this version
  inconclusive  no complete Gradle log, or the build failed with a different error (not evidence about the issue)
"pass" says the repro did not fail here; it does not prove the issue is fixed in that version.
"""
import json
import os
import re
import sys

from . import result

HERE = os.path.dirname(os.path.abspath(__file__))
_END = re.compile(r"^BUILD (SUCCESSFUL|FAILED)", re.M)


def load_issue(issue_id, path=None):
    with open(path or os.path.join(HERE, "known_issues.json"), encoding="utf-8") as f:
        for i in json.load(f)["issues"]:
            if i["id"] == issue_id:
                return i
    raise KeyError(issue_id)


def parse(log, issue):
    m = _END.search(log or "")
    if not m:
        return result("inconclusive", "no 'BUILD SUCCESSFUL' or 'BUILD FAILED' line: not a complete Gradle log")
    if m.group(1) == "SUCCESSFUL":
        return result("pass", None, issue=issue["id"], reproduces=False)
    if re.search(issue["signature"], log):
        return result("fail", "reproduces %s" % issue["id"], issue=issue["id"], reproduces=True)
    first = next((l.strip() for l in log.splitlines() if l.strip() and "What went wrong" in l), None)
    after = None
    lines = log.splitlines()
    for i, l in enumerate(lines):
        if "What went wrong" in l and i + 1 < len(lines):
            after = lines[i + 1].strip()[:200]
            break
    return result("inconclusive", "failed with a different error than %s: %s" % (issue["id"], after or first or "unknown"),
                  issue=issue["id"], reproduces=False)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    issue = load_issue(a.issue)
    with open(a.log, encoding="utf-8", errors="replace") as f:
        r = parse(f.read(), issue)
    r["version"] = a.version
    r["expected"] = issue.get("expected", {}).get(a.version)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(r, f, indent=1)
    print("%s %s: %s %s" % (a.issue, a.version, r["state"], r["reason"] or ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
