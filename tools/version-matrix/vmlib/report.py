"""Collect and classify per-cell logs, then render report.json and report.md."""
import os

from . import __version__, classify, collect, util
from probes import cell as cell_probes

KIND_ORDER = {"failure": 0, "error": 1, "deprecation": 2, "problem": 3, "warning": 4}
OWNERS_ORDER = ["Gradle", "AGP", "KGP/Kotlin", "KSP", "Other plugin", "Project", "Unknown"]


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def analyze_cell(res, ruleset):
    """Add problems, by_owner, first_error, notes to a raw cell result (re-parsed from its logs)."""
    notes, recs, metas = [], [], []
    d = res.get("dir") or ""
    # workspace is recorded by the runner; older cell.json files: <out>/work/<cell> is the default
    root = res.get("workspace") or (os.path.join(os.path.dirname(d), "work", os.path.basename(d)) if d else None)
    merged = {}
    for s in res.get("steps", []):
        if s["role"] == "version":
            continue
        rs, meta = collect.parse_console(_read(s["log"]), root)
        metas.append(dict(meta, step=s["name"]))
        for r in rs:
            k = collect.signature(r)
            if k in merged:
                merged[k]["count"] = max(merged[k]["count"], r["count"])
            else:
                merged[k] = r
                recs.append(r)
    pr = os.path.join(res.get("dir", ""), "problems-report.html")
    if os.path.isfile(pr):
        try:
            prs, note = collect.parse_problems_report(_read(pr), root)
        except Exception as e:  # best-effort parser on an internal format: a surprise must not stop the report
            prs, note = [], "could not parse problems-report.html (%s: %s)" % (type(e).__name__, e)
        notes.append("problems-report.html: " + note)
        seen_at = {collect.loc_key(r.get("location")) for r in recs if collect.loc_key(r.get("location"))}
        for r in prs:
            k = collect.signature(r)
            # the same compiler diagnostic is already in the console log
            if collect.loc_key(r.get("location")) in seen_at:
                continue
            if k not in merged:
                merged[k] = r
                recs.append(r)
    classify.classify_all(recs, ruleset)
    for r in recs:
        r["frames"] = r["frames"][:8]
        r["signature"] = collect.signature(r)
    recs.sort(key=lambda r: (KIND_ORDER.get(r["kind"], 9), -r["count"]))
    by_owner = {}
    for r in recs:
        d = by_owner.setdefault(r["owner"], {})
        d[r["kind"]] = d.get(r["kind"], 0) + 1
    res["problems"] = recs
    res["by_owner"] = by_owner
    res["first_error"] = next((r for r in recs if r["kind"] == "failure"), None)
    res["configuration_cache"] = next((m["configuration_cache"] for m in reversed(metas) if m["configuration_cache"]), None)
    res["analysis_notes"] = notes
    res["probes"] = cell_probes.run(res)
    return res


def build_report(cells, project_info, ruleset, meta=None):
    for c in cells:
        analyze_cell(c, ruleset)
    base = next((c for c in cells if c.get("baseline")), None)
    base_sigs = {p["signature"] for p in base["problems"]} if base else set()
    for c in cells:
        if base and c is not base:
            c["new_vs_baseline"] = [p["signature"] for p in c["problems"] if p["signature"] not in base_sigs
                                    and p["kind"] in ("failure", "error", "deprecation", "problem")]
            c["new_by_owner"] = {}
            for p in c["problems"]:
                if p["signature"] in c["new_vs_baseline"]:
                    c["new_by_owner"][p["owner"]] = c["new_by_owner"].get(p["owner"], 0) + 1
    counts = {}
    for c in cells:
        counts[c["outcome"]] = counts.get(c["outcome"], 0) + 1
    return {"schema": "vmatrix-report/1", "tool_version": __version__, "generated": util.now_iso(),
            "project": project_info, "meta": meta or {}, "summary": counts, "cells": cells,
            "notes": ["problems-report.html is parsed best-effort from an internal, undocumented format."]}


def _vers(c):
    parts = []
    for a in ("gradle", "agp", "kotlin", "ksp"):
        if a in c["requested"]:
            parts.append("%s %s%s" % (a, c["requested"][a], "*" if a in c["axes"] else ""))
    fl = ["%s=%s" % kv for kv in sorted(c["flags"].items())] + c.get("gradle_args", [])
    if fl:
        parts.append("flags: " + " ".join(fl))
    return "<br>".join(parts)


def _actual(c):
    g = c.get("guard")
    if not g:
        return "-"
    out = []
    for a, d in g["axes"].items():
        act = d["actual"]
        out.append("%s %s" % (a, ",".join(act) if isinstance(act, list) else (act or "?")))
    return "<br>".join(out)


def _esc(s):
    return s.replace("|", "\\|").replace("\n", " ")


def _top(c, n=3):
    out = []
    for p in c["problems"]:
        if p["kind"] == "warning":
            continue
        first = p["text"].split("\n")[0][:90]
        out.append("[%s] %s%s" % (p["owner"], first, " (x%d)" % p["count"] if p["count"] > 1 else ""))
        if len(out) == n:
            break
    return "<br>".join(_esc(x) for x in out) or "-"


def _owners(c):
    parts = []
    for o in OWNERS_ORDER + sorted(set(c["by_owner"]) - set(OWNERS_ORDER)):
        d = c["by_owner"].get(o)
        if d:
            parts.append("%s %d" % (o, sum(d.values())))
    return ", ".join(parts) or "-"


def render_md(rep):
    pi = rep["project"]
    L = ["# Version matrix report", "",
         "Generated %s by vmatrix %s. Project `%s`%s." % (
             rep["generated"], rep["tool_version"], pi.get("path"),
             " at `%s`" % pi["git"][:10] if pi.get("git") else ""),
         "", "Outcomes: " + ", ".join("%s %d" % kv for kv in sorted(rep["summary"].items())), "",
         "`*` marks the version changed in that cell. INVALID means the versions that ran differ from the ones "
         "requested (or could not be verified); its results are not evidence about the requested versions.", "",
         "| Cell | Requested | Actual (guard) | Outcome | Problems by owner | Top problems | Duration |",
         "|---|---|---|---|---|---|---|"]
    for c in rep["cells"]:
        g = c.get("guard")
        L.append("| %s | %s | %s %s | %s | %s | %s | %s |" % (
            c["name"], _esc(_vers(c)), _actual(c),
            "(%s)" % g["result"] if g else "", c["outcome"], _owners(c), _top(c),
            "%ds" % c["duration_s"] if c.get("duration_s") is not None else "-"))
    for c in rep["cells"]:
        L += ["", "## %s" % c["name"], "", "- Outcome: %s%s" % (
            c["outcome"], " (failed step `%s`)" % c["failed_step"] if c.get("failed_step") else "")]
        if c.get("error"):
            L.append("- Harness error: %s" % c["error"])
        if c.get("guard"):
            for a, d in c["guard"]["axes"].items():
                L.append("- Guard %s: requested %s, actual %s, %s" % (a, d["requested"], d["actual"], d["status"]))
        for w in c.get("warnings", []):
            L.append("- Warning: " + w)
        fe = c.get("first_error")
        if fe:
            L.append("- First error [%s, rule %s]: %s" % (fe["owner"], fe["rule"], fe["text"].split("\n")[0][:200]))
        if c.get("new_by_owner"):
            L.append("- New versus baseline, by owner: " + ", ".join("%s %d" % kv for kv in sorted(c["new_by_owner"].items())))
        if c.get("configuration_cache"):
            L.append("- Configuration cache: entry %s" % c["configuration_cache"])
        L.append("- Steps: " + "; ".join("%s exit %s %ss" % (s["name"], s["exit_code"], s["duration_s"]) for s in c["steps"]))
        shown = [p for p in c["problems"] if p["kind"] != "warning"][:15]
        if shown:
            L += ["", "| Kind | Owner | Count | Problem |", "|---|---|---|---|"]
            for p in shown:
                L.append("| %s | %s | %d | %s |" % (p["kind"], p["owner"], p["count"], _esc(p["text"].split("\n")[0][:140])))
    L += ["", "Notes: " + " ".join(rep["notes"]), ""]
    return "\n".join(L)


def write_reports(rep, out_dir):
    util.write_json(os.path.join(out_dir, "report.json"), rep)
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(render_md(rep))


def exit_code(rep, fail_on="any"):
    s = rep["summary"]
    if fail_on == "never":
        return 0
    if s.get("INVALID"):
        return 3
    if fail_on == "any" and any(s.get(k) for k in ("FAIL", "TIMEOUT", "ERROR")):
        return 1
    return 0
