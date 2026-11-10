"""Project handling: read pins, apply one cell's versions to a throwaway workspace.

Never edits the user's tree: the workspace is a `git worktree` (detached, at --ref) or a copy.
Version overrides: [versions] entries of every *.versions.toml found (build-logic may carry its own),
and the Gradle wrapper distributionUrl. Catalogs declared inside settings.gradle(.kts) are not handled.
"""
import os
import re
import shutil
import subprocess

IGNORE_DIRS = {".git", ".gradle", "build", ".idea", ".kotlin", "node_modules", ".cxx"}
WRAPPER = os.path.join("gradle", "wrapper", "gradle-wrapper.properties")


class ProjectError(Exception):
    pass


# ---------- catalog ----------

_SECTION = re.compile(r"^\s*\[([^\]]+)\]\s*(#.*)?$")
_ENTRY = re.compile(r'^(\s*)([A-Za-z0-9_.\-]+)(\s*=\s*)"([^"]*)"(.*)$')


def find_catalogs(root, explicit=None):
    if explicit:
        return [p for p in explicit if os.path.isfile(os.path.join(root, p))]
    found = []
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in IGNORE_DIRS]
        for f in files:
            if f.endswith(".versions.toml"):
                found.append(os.path.relpath(os.path.join(d, f), root))
    return sorted(found)


def catalog_versions(text):
    out, section = {}, None
    for line in text.splitlines():
        m = _SECTION.match(line)
        if m:
            section = m.group(1).strip()
            continue
        if section == "versions":
            e = _ENTRY.match(line)
            if e:
                out[e.group(2)] = e.group(4)
    return out


def set_catalog_version(text, key, value):
    """Return (new_text, old_value) replacing key in [versions]; old_value None if key absent."""
    out, section, old = [], None, None
    for line in text.splitlines(keepends=True):
        m = _SECTION.match(line.rstrip("\n"))
        if m:
            section = m.group(1).strip()
        elif section == "versions":
            e = _ENTRY.match(line.rstrip("\n"))
            if e and e.group(2) == key and old is None:
                old = e.group(4)
                nl = "\n" if line.endswith("\n") else ""
                line = '%s%s%s"%s"%s%s' % (e.group(1), key, e.group(3), value, e.group(5), nl)
        out.append(line)
    return "".join(out), old


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def resolve_key(texts, candidates):
    """First candidate key present in any catalog text. Returns key or None."""
    for key in candidates:
        for t in texts:
            if key in catalog_versions(t):
                return key
    return None


# ---------- wrapper ----------

_DIST = re.compile(r"gradle-(.+?)-(bin|all)\.zip")


def read_wrapper(root):
    p = os.path.join(root, WRAPPER)
    if not os.path.isfile(p):
        return None
    for line in _read(p).splitlines():
        if line.startswith("distributionUrl="):
            m = _DIST.search(line)
            if m:
                return {"version": m.group(1), "type": m.group(2), "line": line}
    return None


def apply_wrapper(root, version, url=None):
    p = os.path.join(root, WRAPPER)
    cur = read_wrapper(root)
    if not cur:
        raise ProjectError("no readable distributionUrl in %s" % WRAPPER)
    new_url = url or "https://services.gradle.org/distributions/gradle-%s-%s.zip" % (version, cur["type"])
    new_line = "distributionUrl=" + new_url.replace(":", "\\:")
    lines = []
    for line in _read(p).splitlines(keepends=True):
        if line.startswith("distributionSha256Sum="):
            continue  # checksum belongs to the old distribution
        if line.startswith("distributionUrl="):
            line = new_line + ("\n" if line.endswith("\n") else "")
        lines.append(line)
    _write(p, "".join(lines))
    return cur["version"]


# ---------- pins and edits ----------

def read_pins(root, key_candidates, catalogs=None):
    """Current versions of the project: {'gradle':..,'agp':..,'kotlin':..,'ksp':..} (missing axes omitted)."""
    pins = {}
    w = read_wrapper(root)
    if w:
        pins["gradle"] = w["version"]
    cats = catalogs if catalogs is not None else find_catalogs(root)
    texts = [_read(os.path.join(root, c)) for c in cats]
    for axis, cands in key_candidates.items():
        for t in texts:
            vs = catalog_versions(t)
            hit = next((vs[k] for k in cands if k in vs), None)
            if hit:
                pins[axis] = hit
                break
    return pins


def plan_edits(root, axes, key_candidates, catalogs, gradle_url=None):
    """Describe edits without writing. axes: {'agp':'9.4.0', 'gradle': '9.8.2'}. Raises ProjectError if impossible."""
    edits = []
    for axis, value in axes.items():
        if axis == "gradle":
            w = read_wrapper(root)
            if not w:
                raise ProjectError("cannot set gradle: no wrapper properties")
            edits.append({"file": WRAPPER, "axis": "gradle", "key": "distributionUrl",
                          "old": w["version"], "new": value, "url": gradle_url})
            continue
        cands = key_candidates.get(axis)
        if not cands:
            raise ProjectError("no catalog key configured for axis %r" % axis)
        hit = False
        for c in catalogs:
            vs = catalog_versions(_read(os.path.join(root, c)))
            for k in cands:
                if k in vs:
                    edits.append({"file": c, "axis": axis, "key": k, "old": vs[k], "new": value})
                    hit = True
                    break
        if not hit:
            raise ProjectError("axis %r: none of the keys %s found in [versions] of %s"
                               % (axis, cands, ", ".join(catalogs) or "(no catalogs)"))
    return edits


def apply_edits(ws, edits):
    for e in edits:
        if e["axis"] == "gradle":
            apply_wrapper(ws, e["new"], e.get("url"))
        else:
            p = os.path.join(ws, e["file"])
            new, old = set_catalog_version(_read(p), e["key"], e["new"])
            if old is None:
                raise ProjectError("key %s vanished from %s" % (e["key"], e["file"]))
            _write(p, new)


# ---------- per-cell ref ----------

def rev_parse(root, ref):
    """Full commit sha of ref, or raise ProjectError."""
    return _git(["rev-parse", "--verify", ref + "^{commit}"], root).stdout.strip()


def ref_view(root, ref, dest):
    """Write the files the harness reads for pins and edits (catalogs, wrapper properties) as they are at ref.

    Returns the commit sha. Lets a cell name an old commit without checking it out: pins and planned edits
    come from that commit, not from the working tree."""
    sha = rev_parse(root, ref)
    names = _git(["ls-tree", "-r", "--name-only", sha], root).stdout.splitlines()
    for n in names:
        if n.endswith(".versions.toml") or n == WRAPPER.replace(os.sep, "/"):
            blob = _git(["show", "%s:%s" % (sha, n)], root).stdout
            path = os.path.join(dest, n)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            _write(path, blob)
    return sha


# ---------- workspace ----------

def _git(args, cwd, check=True):
    r = subprocess.run(["git"] + args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True)
    if check and r.returncode != 0:
        raise ProjectError("git %s failed: %s" % (" ".join(args), r.stderr.strip()))
    return r


def is_git_repo(root):
    return os.path.exists(os.path.join(root, ".git"))


def project_info(root):
    info = {"path": root, "git": None, "dirty": None}
    if is_git_repo(root):
        r = _git(["rev-parse", "HEAD"], root, check=False)
        info["git"] = r.stdout.strip() or None
        s = _git(["status", "--porcelain"], root, check=False)
        info["dirty"] = bool(s.stdout.strip())
    return info


def prepare_workspace(root, dest, mode="auto", ref="HEAD", copy_files=()):
    """Create dest. Returns {'mode':..., 'warnings':[...]}."""
    if os.path.exists(dest):
        raise ProjectError("workspace already exists: %s" % dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    warnings = []
    if mode == "auto":
        mode = "worktree" if is_git_repo(root) else "copy"
    if mode == "worktree":
        _git(["worktree", "add", "--detach", dest, ref], root)
        if _git(["status", "--porcelain"], root, check=False).stdout.strip():
            warnings.append("project has uncommitted changes; the worktree is built from %s without them" % ref)
        for f in copy_files:
            src = os.path.join(root, f)
            if os.path.exists(src):
                os.makedirs(os.path.dirname(os.path.join(dest, f)) or dest, exist_ok=True)
                shutil.copy2(src, os.path.join(dest, f))
    elif mode == "copy":
        shutil.copytree(root, dest, symlinks=True,
                        ignore=shutil.ignore_patterns(*sorted(IGNORE_DIRS)))
    else:
        raise ProjectError("unknown workspace mode %r" % mode)
    return {"mode": mode, "warnings": warnings}


def remove_workspace(root, dest, mode):
    if mode == "worktree":
        _git(["worktree", "remove", "--force", dest], root, check=False)
        _git(["worktree", "prune"], root, check=False)
    if os.path.exists(dest):
        shutil.rmtree(dest, ignore_errors=True)
