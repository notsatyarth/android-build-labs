"""Parse Gradle console logs and the problems report into problem records.

A record: {kind, text, group, location, frames[], source, count}
kind: failure | deprecation | problem | warning | error
The problems-report parser is best-effort: the data embedded in problems-report.html is an internal,
undocumented format (Gradle says it can change in any release). Supported route is the Tooling API.
"""
import json
import re

_FRAME = re.compile(r"^\s+at\s+\S")
_LOC = re.compile(r"(?:Location|Where):?\s*(.+)$")


def parse_gradle_version(text):
    out = {}
    m = re.search(r"^Gradle\s+(\S+)\s*$", text, re.M)
    if m:
        out["gradle"] = m.group(1)
    m = re.search(r"^Kotlin:\s+(\S+)", text, re.M)
    if m:
        out["gradle_embedded_kotlin"] = m.group(1)
    m = re.search(r"^(?:Launcher )?JVM:\s+(.+)$", text, re.M)
    if m:
        out["jvm"] = m.group(1).strip()
    m = re.search(r"^OS:\s+(.+)$", text, re.M)
    if m:
        out["os"] = m.group(1).strip()
    return out


_DEP = re.compile(
    r"(?P<g>[A-Za-z0-9_.\-]+):(?P<n>[A-Za-z0-9_.\-]+)(?::(?P<v>[^\s:>]+))?(?:\s+->\s+(?P<r>[^\s]+))?")
_TREE = re.compile(r"^[\s|]*[+\\]---\s+(.*)$")


def parse_build_environment(text):
    """Return {'agp': set, 'kotlin': set, 'ksp': set} of resolved versions seen on buildscript classpaths."""
    seen = {"agp": set(), "kotlin": set(), "ksp": set()}
    for line in text.splitlines():
        t = _TREE.match(line)
        if not t:
            continue
        m = _DEP.match(t.group(1).strip())
        if not m:
            continue
        g, n = m.group("g"), m.group("n")
        v = m.group("r") or m.group("v")
        if not v:
            continue
        marker = n.endswith(".gradle.plugin") and g == n[: -len(".gradle.plugin")]
        if (g == "com.android.tools.build" and n == "gradle") or (marker and g.startswith("com.android.")):
            seen["agp"].add(v)
        elif (g == "org.jetbrains.kotlin" and n == "kotlin-gradle-plugin") or \
                (marker and g.startswith("org.jetbrains.kotlin.")):
            seen["kotlin"].add(v)
        elif (g == "com.google.devtools.ksp" and n == "symbol-processing-gradle-plugin") or \
                (marker and g == "com.google.devtools.ksp"):
            seen["ksp"].add(v)
    return seen


def _rec(kind, text, source="console", group=None, location=None, frames=None):
    return {"kind": kind, "text": text.strip(), "group": group, "location": location,
            "frames": frames or [], "source": source, "count": 1}


def rel_location(loc, root=None):
    """Strip file:// and the workspace root so locations (and signatures) are the same in every cell."""
    if not loc:
        return loc
    loc = re.sub(r"^file://", "", loc)
    if root:
        root = root.rstrip("/") + "/"
        loc = loc.replace(root, "", 1) if root in loc else loc
    return loc


def loc_key(loc):
    """(file, line) of 'a/b.kt:45:5' or 'a/b.kt line 45', else None."""
    m = re.match(r"^(.*?\.(?:kt|kts|java))(?::|\s+line\s+)(\d+)", loc or "")
    return (m.group(1), m.group(2)) if m else None


def parse_console(text, root=None):
    """Return (records, meta). root: workspace path, stripped from file locations."""
    lines = text.splitlines()
    recs, meta = [], {"failed_tasks": [], "build": None, "configuration_cache": None, "exit": None}
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        s = ln.strip()
        if ln.startswith("# exit="):
            try:
                meta["exit"] = int(ln.split("=", 1)[1])
            except ValueError:
                pass
        elif ln.startswith("#"):
            pass
        elif ln.startswith("BUILD SUCCESSFUL"):
            meta["build"] = "SUCCESSFUL"
        elif ln.startswith("BUILD FAILED"):
            meta["build"] = "FAILED"
        elif re.match(r"^Configuration cache entry (stored|reused)", ln):
            meta["configuration_cache"] = re.match(r"^Configuration cache entry (\w+)", ln).group(1)
        elif ln.startswith("FAILURE: Build failed"):
            j = i + 1
            block = []
            while j < n and not lines[j].startswith("BUILD FAILED"):
                block.append(lines[j])
                j += 1
            where = wrong = None
            cur, buf = None, []
            for b in block + ["* END"]:
                if b.startswith("* "):
                    if cur == "where":
                        where = " ".join(x.strip() for x in buf if x.strip())
                    elif cur == "wrong":
                        wrong = "\n".join(x.rstrip() for x in buf).strip()
                    cur = "where" if b.startswith("* Where:") else ("wrong" if b.startswith("* What went wrong:") else None)
                    buf = []
                elif cur:
                    buf.append(b)
            frames = [b.strip() for b in block if _FRAME.match(b)]
            caused = [b.strip() for b in block if b.startswith("Caused by:")]
            r = _rec("failure", wrong or "Build failed (no 'What went wrong' block)", location=where,
                     frames=frames)
            if caused:
                r["text"] += "\n" + "\n".join(caused)
            recs.append(r)
            i = j - 1
        elif s.startswith("Problem found:"):
            j = i + 1
            body = []
            while j < n and lines[j][:1] in (" ", "\t") and lines[j].strip():
                body.append(lines[j].strip())
                j += 1
            header = s[len("Problem found:"):].strip()
            gm = re.search(r"\(in ([^)]+)\)", header) or re.search(r"\(id: ([^)]+)\)", header)
            loc = next((_LOC.search(b).group(1) for b in body if _LOC.search(b)), None)
            full = header + ("\n" + "\n".join(body) if body else "")
            kind = "deprecation" if "deprecat" in full.lower() else "problem"
            recs.append(_rec(kind, full, group=gm.group(1) if gm else None, location=loc))
            i = j - 1
        elif ln.startswith("WARNING:"):
            j = i + 1
            cont = []
            while j < n and lines[j].strip() and not lines[j].startswith(("WARNING:", ">", "Problem found")) \
                    and len(cont) < 4:
                cont.append(lines[j].strip())
                j += 1
            full = ln.strip() + ("\n" + "\n".join(cont) if cont else "")
            recs.append(_rec("deprecation" if "deprecat" in full.lower() else "warning", full))
            i = j - 1
        elif re.match(r"^[we]: ", ln):
            kind = "warning" if ln[0] == "w" else "error"
            m = re.match(r"^[we]: (?:file://)?(\S+?:\d+(?::\d+)?)?\s*(.*)$", ln)
            recs.append(_rec(kind, "Kotlin compiler %s: %s" % (kind, m.group(2) if m else ln[3:]),
                             location=rel_location(m.group(1) if m else None, root)))
        elif re.search(r"(has been deprecated|is deprecated|are deprecated)", ln) and \
                not ln.startswith(("Deprecated Gradle features", " ")):
            j = i + 1
            frames, extra = [], []
            while j < n and lines[j].strip() and len(frames) + len(extra) < 60:
                if _FRAME.match(lines[j]):
                    frames.append(lines[j].strip())
                elif re.match(r"^\s*(Consult|For more|See |This is scheduled|Use |Please)", lines[j]):
                    extra.append(lines[j].strip())
                else:
                    break
                j += 1
            recs.append(_rec("deprecation", ln.strip() + ("\n" + "\n".join(extra) if extra else ""), frames=frames))
            i = j - 1
        else:
            m = re.match(r"^> Task (\S+) FAILED", ln)
            if m:
                meta["failed_tasks"].append(m.group(1))
            m = re.search(r"(\d+) problems? (?:was|were) found (storing|reusing) the configuration cache", ln)
            if m:
                recs.append(_rec("warning", ln.strip()))
        i += 1
    return merge(recs), meta


def signature(rec):
    t = rec["text"].lower()
    t = re.sub(r"(/[\w.\-@+ ]+)+", "<path>", t)
    t = re.sub(r"\d+", "#", t)
    loc = rec.get("location") or ""
    # compiler diagnostics differ by file; do not merge the same text in different files
    where = "|" + loc if rec["kind"] in ("warning", "error") and loc_key(loc) else ""
    return "%s|%s%s" % (rec["kind"], " ".join(t.split())[:300], where)


def merge(recs):
    out, idx = [], {}
    for r in recs:
        k = signature(r)
        if k in idx:
            idx[k]["count"] += r.get("count", 1)
        else:
            idx[k] = r
            out.append(r)
    return out


# ---------- problems report (internal format, best effort) ----------

def _walk(o, found):
    if isinstance(o, dict):
        if ("problemId" in o or "definition" in o) and any(k in o for k in ("contextualLabel", "details", "label")):
            found.append(o)
        for v in o.values():
            _walk(v, found)
    elif isinstance(o, list):
        for v in o:
            _walk(v, found)


def _group_path(o):
    pid = o.get("problemId")
    if pid is None and isinstance(o.get("definition"), dict):
        pid = o["definition"].get("id") or o["definition"].get("problemId")
    names = []
    if isinstance(pid, list):
        for x in pid:
            names.append(x.get("displayName") or x.get("name") if isinstance(x, dict) else str(x))
    elif isinstance(pid, dict):
        names.append(pid.get("displayName") or pid.get("name") or "")
        g = pid.get("group")
        while isinstance(g, dict):
            names.insert(0, g.get("displayName") or g.get("name") or "")
            g = g.get("parent")
    elif isinstance(pid, str):
        names.append(pid)
    return " > ".join(x for x in names if x)


def parse_problems_report(html, root=None):
    """Return (records, note). Never raises on unknown formats; returns ([], note)."""
    dec = json.JSONDecoder()
    found = []
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", html, re.S | re.I):
        body = m.group(1)
        for sm in re.finditer(r"[{\[]", body):
            try:
                obj, _ = dec.raw_decode(body[sm.start():])
            except ValueError:
                continue
            before = len(found)
            _walk(obj, found)
            if len(found) > before:
                break
    if not found:
        return [], "no problem entries recognised in problems-report.html (internal format, may have changed)"
    recs = []
    for o in found:
        label = o.get("contextualLabel") or o.get("label") or ""
        det = o.get("details") or o.get("problemDetails") or ""
        sev = str(o.get("severity", "")).upper()
        loc = None
        locs = o.get("locations") or o.get("originLocations") or []
        if isinstance(locs, list) and locs and isinstance(locs[0], dict):
            l0 = locs[0]
            loc = rel_location(l0.get("path"), root) or l0.get("pluginId") or l0.get("taskPath")
            if loc and l0.get("line"):
                loc = "%s line %s" % (loc, l0["line"])
        group = _group_path(o)
        full = " ".join(x for x in (label, det) if x) or group
        kind = "deprecation" if "deprecat" in (group + full).lower() else (
            "error" if sev == "ERROR" else "problem")
        recs.append(_rec(kind, full, source="problems-report", group=group or None, location=loc))
    return merge(recs), "parsed %d entries from internal problems-report format (best effort)" % len(found)
