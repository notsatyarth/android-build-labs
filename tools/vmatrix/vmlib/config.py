"""Matrix config: load, merge defaults, resolve channels into concrete cells."""
import json
import os
import shlex

from . import project, util

AXES = ("gradle", "agp", "kotlin", "ksp")

DEFAULTS = {
    "project": None,
    "mode": "auto",                 # auto | worktree | copy
    "ref": "HEAD",                  # git ref used for worktree mode
    "workspace": None,              # default: <out>/work
    "tasks": [["help"], [":app:assembleDemoDebug"]],
    "gradle_args": ["--console=plain", "--warning-mode=all", "--stacktrace"],
    "guard_tasks": ["buildEnvironment", ":app:buildEnvironment"],
    "timeout_sec": 3600,
    "catalog_keys": {"agp": ["androidGradlePlugin", "agp"], "kotlin": ["kotlin"], "ksp": ["ksp"]},
    "catalog_files": None,          # default: every *.versions.toml found in the project
    "copy_files": ["local.properties"],
    "java_home": None,
    "gradle_user_home": None,       # set for isolation from other builds on the machine
    "daemon_cleanup": "stop",       # none | stop | stop+kill
    "problems_report": "build/reports/problems/problems-report.html",
    "cells": [
        {"name": "baseline"},
        {"name": "gradle-next", "axes": {"gradle": "@next"}},
        {"name": "agp-next", "axes": {"agp": "@next"}},
        {"name": "kotlin-next", "axes": {"kotlin": "@next"}},
    ],
}


class ConfigError(Exception):
    pass


def _norm_tasks(tasks):
    out = []
    for t in tasks:
        out.append(shlex.split(t) if isinstance(t, str) else list(t))
    return out


def load(path=None, overrides=None):
    cfg = json.loads(json.dumps(DEFAULTS))
    if path:
        try:
            with open(path, "r", encoding="utf-8") as f:
                user = json.load(f)
        except (OSError, ValueError) as e:
            raise ConfigError("cannot read config %s: %s" % (path, e))
        base = os.path.dirname(os.path.abspath(path))
        for k, v in user.items():
            if not k.startswith("_"):
                cfg[k] = v
        if cfg.get("project") and not os.path.isabs(os.path.expanduser(cfg["project"])):
            cfg["project"] = os.path.normpath(os.path.join(base, cfg["project"]))
    for k, v in (overrides or {}).items():
        if v is not None:
            cfg[k] = v
    if not cfg.get("project"):
        cfg["project"] = os.environ.get("VMATRIX_PROJECT")
    if not cfg.get("project"):
        raise ConfigError("no project: pass --project, set 'project' in the config, or set VMATRIX_PROJECT")
    cfg["project"] = os.path.abspath(os.path.expanduser(cfg["project"]))
    if not os.path.isdir(cfg["project"]):
        raise ConfigError("project path is not a directory: %s" % cfg["project"])
    if not os.path.isfile(os.path.join(cfg["project"], "gradlew")):
        raise ConfigError("no ./gradlew in %s" % cfg["project"])
    cfg["tasks"] = _norm_tasks(cfg["tasks"])
    cfg["guard_tasks"] = shlex.split(cfg["guard_tasks"]) if isinstance(cfg["guard_tasks"], str) else cfg["guard_tasks"]
    if cfg["daemon_cleanup"] not in ("none", "stop", "stop+kill"):
        raise ConfigError("daemon_cleanup must be none, stop or stop+kill")
    names = [c.get("name") for c in cfg["cells"]]
    if len(set(names)) != len(names) or not all(names):
        raise ConfigError("cell names must be present and unique: %s" % names)
    return cfg


def resolve(cfg, discovery=None):
    """Return the plan: {'pins', 'catalogs', 'cells': [...]} with channels resolved.

    Each cell: name, axes (changes only), requested (all axes to verify), flags, gradle_args, tasks, java_home,
    gradle_url, edits (planned), skip (reason or None), baseline (bool).
    """
    root = cfg["project"]
    catalogs = project.find_catalogs(root, cfg.get("catalog_files"))
    pins = project.read_pins(root, cfg["catalog_keys"], catalogs)
    cells = []
    for c in cfg["cells"]:
        axes_in = dict(c.get("axes") or {})
        for a in axes_in:
            if a not in AXES:
                raise ConfigError("cell %s: unknown axis %r (known: %s)" % (c["name"], a, ", ".join(AXES)))
        axes, skip, gradle_url, notes = {}, None, None, []
        for a, v in axes_in.items():
            if isinstance(v, str) and v.startswith("@"):
                if discovery is None:
                    skip = skip or "channel %s needs discovery" % v
                    continue
                ent = discovery.pick(a, v[1:])
                if not ent:
                    skip = skip or "no %s version in channel %s newer than stable" % (a, v[1:])
                    continue
                v = ent["version"]
                if a == "gradle" and ent.get("url") and ent["channel"] in ("nightly", "release-nightly", "dev"):
                    gradle_url = ent["url"]
                notes.append("%s %s -> %s" % (a, axes_in[a], v))
            axes[a] = v
        if not skip and axes and all(pins.get(a) == v for a, v in axes.items()) and not c.get("flags") \
                and not c.get("gradle_args"):
            skip = "identical to the project's current pins (same as baseline)"
        requested = dict(pins)
        requested.update(axes)
        for a in list(requested):
            if a not in pins and a not in axes:
                requested.pop(a)
        cell = {
            "name": c["name"],
            "axes": axes,
            "requested": requested,
            "flags": dict(c.get("flags") or {}),
            "gradle_args": list(c.get("gradle_args") or []),
            "tasks": _norm_tasks(c["tasks"]) if c.get("tasks") else cfg["tasks"],
            "java_home": c.get("java_home") or cfg.get("java_home"),
            "env": dict(c.get("env") or {}),
            "timeout_sec": c.get("timeout_sec") or cfg["timeout_sec"],
            "gradle_url": gradle_url,
            "channel_notes": notes,
            "skip": skip,
            "baseline": bool(c.get("baseline")) or (not axes_in and not c.get("flags") and not c.get("gradle_args")),
        }
        if not skip:
            try:
                cell["edits"] = project.plan_edits(root, axes, cfg["catalog_keys"], catalogs, gradle_url)
            except project.ProjectError as e:
                cell["skip"] = "cannot apply: %s" % e
                cell["edits"] = []
        else:
            cell["edits"] = []
        cells.append(cell)
    return {"project": project.project_info(root), "pins": pins, "catalogs": catalogs, "cells": cells}
