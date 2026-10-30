"""Small shared helpers: version ordering, JSON io, time."""
import json
import os
import re
import tempfile
import time

_PRE_RANK = (
    ("rc", 4),
    ("beta", 3),
    ("alpha", 2),
    ("milestone", 1),
)


def version_key(v):
    """Sortable key. stable > rc > beta > alpha > milestone > dev/other for the same numeric core."""
    m = re.match(r"^(\d+(?:\.\d+)*)(?:[-.+]?(.*))?$", v.strip())
    if not m:
        return ((0, 0, 0, 0), -1, (), v)
    main = [int(x) for x in m.group(1).split(".")]
    main = tuple((main + [0, 0, 0, 0])[: max(4, len(main))])
    pre = (m.group(2) or "").strip()
    if not pre:
        return (main, 5, (), "")
    low = pre.lower()
    rank = 0
    for name, r in _PRE_RANK:
        if name in low:
            rank = r
            break
    nums = tuple(int(x) for x in re.findall(r"\d+", pre))
    return (main, rank, nums, pre)


def channel_of(v):
    """Generic channel from a version string: stable, rc, beta, alpha, milestone, dev, other."""
    if "-" not in v and not re.search(r"[A-Za-z]", v):
        return "stable"
    low = v.lower()
    if "rc" in re.split(r"[-.\d]+", low) or re.search(r"-rc\d*", low):
        return "rc"
    if "beta" in low:
        return "beta"
    if "alpha" in low:
        return "alpha"
    if "milestone" in low or re.search(r"-m\d+$", low):
        return "milestone"
    if "dev" in low or "snapshot" in low or re.search(r"\d{8,}", low) or "titan" in low:
        return "dev"
    return "other"


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=False)
        f.write("\n")
    os.replace(tmp, path)


def slug(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_") or "x"
