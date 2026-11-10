"""Flag availability probe (tier 1, no build): which known flags exist in which AGP or KGP version.

Reads the published plugin jar from Maven and looks for the flag name as a string in the class files.
Statuses per flag and version:
  declared       the name is in an options/properties class (AGP: com/android/build/gradle/options/*Option.class,
                 KGP: a class whose name contains "Propert")
  mentioned      the name is in some other class only (a message, a doc string, a reader); not proof it is an option
  absent         the name is in no class of that jar
  version_not_found / error:<reason>   the jar could not be fetched or read: not a statement about the flag
Derived from bytecode: internal, not public API. "absent" in a version only says the string is not in that jar.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
import zipfile

from . import result

HERE = os.path.dirname(os.path.abspath(__file__))
MAVEN = {
    "agp": "https://dl.google.com/android/maven2/com/android/tools/build/gradle/{v}/gradle-{v}.jar",
    "kgp": "https://repo.maven.apache.org/maven2/org/jetbrains/kotlin/kotlin-gradle-plugin/{v}/kotlin-gradle-plugin-{v}.jar",
}
DECLARING = {
    "agp": re.compile(r"^com/android/build/gradle/options/\w*Option\.class$"),
    "kgp": re.compile(r"Propert[^/]*\.class$"),
}


def load_flags(path=None):
    with open(path or os.path.join(HERE, "flags.json"), encoding="utf-8") as f:
        return json.load(f)["flags"]


def jar_url(tool, version):
    return MAVEN[tool].format(v=version)


def fetch_jar(tool, version, cache_dir, opener=urllib.request.urlopen):
    """Return the local jar path, downloading once. Raises FileNotFoundError for a version Maven does not have."""
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, "%s-%s.jar" % (tool, version))
    if os.path.isfile(path) and os.path.getsize(path) > 0:
        return path
    try:
        with opener(jar_url(tool, version), timeout=120) as r, open(path + ".part", "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise FileNotFoundError(version)
        raise
    os.replace(path + ".part", path)
    return path


def scan_jar(jar_path, tool, flag_names):
    """{flag: {"status": declared|mentioned|absent, "classes": [up to 3 class names]}}"""
    want = {f: f.encode("utf-8") for f in flag_names}
    found = {f: {"declared": [], "other": []} for f in flag_names}
    with zipfile.ZipFile(jar_path) as z:
        for name in z.namelist():
            if not name.endswith(".class"):
                continue
            data = z.read(name)
            kind = "declared" if DECLARING[tool].search(name) else "other"
            for f, b in want.items():
                if b in data:
                    found[f][kind].append(name)
    out = {}
    for f, hits in found.items():
        if hits["declared"]:
            out[f] = {"status": "declared", "classes": hits["declared"][:3]}
        elif hits["other"]:
            out[f] = {"status": "mentioned", "classes": hits["other"][:3]}
        else:
            out[f] = {"status": "absent", "classes": []}
    return out


def probe(tool, versions, cache_dir, flags=None, fetch=fetch_jar):
    """{version: {flag: {...}} or {"_error": reason}} for one tool."""
    names = [f["flag"] for f in (flags or load_flags()) if f["tool"] == tool]
    out = {}
    for v in versions:
        try:
            path = fetch(tool, v, cache_dir)
            out[v] = scan_jar(path, tool, names)
        except FileNotFoundError:
            out[v] = {"_error": "version_not_found"}
        except (OSError, zipfile.BadZipFile, urllib.error.URLError) as e:
            out[v] = {"_error": "error:%s" % e}
    return out


def summarize(per_version):
    """Result object for one tool: counts per version, inconclusive if any jar could not be read."""
    rows = {}
    bad = []
    for v, d in per_version.items():
        if "_error" in d:
            bad.append("%s: %s" % (v, d["_error"]))
            continue
        c = {"declared": 0, "mentioned": 0, "absent": 0}
        for r in d.values():
            c[r["status"]] += 1
        rows[v] = c
    if bad:
        return result("inconclusive", "; ".join(bad), counts=rows)
    return result("pass", None, counts=rows)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tool", required=True, choices=sorted(MAVEN))
    ap.add_argument("--versions", required=True, help="comma-separated plugin versions")
    ap.add_argument("--cache", required=True, help="directory for downloaded jars")
    ap.add_argument("--out", required=True, help="output JSON file")
    a = ap.parse_args(argv)
    versions = [v for v in a.versions.split(",") if v]
    data = probe(a.tool, versions, a.cache)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"tool": a.tool, "flags": [x for x in load_flags() if x["tool"] == a.tool],
                   "versions": data, "summary": summarize(data)}, f, indent=1)
    print("wrote %s (%d versions)" % (a.out, len(versions)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
