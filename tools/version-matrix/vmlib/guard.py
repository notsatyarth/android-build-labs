"""Version guard: did the versions we asked for actually run?

Lesson from Gradle's smoke tests: a version parameter that is silently ignored makes a cell meaningless.
"""
from . import collect


def check(requested, gradle_version_text, build_env_text):
    """requested: {'gradle','agp','kotlin','ksp'} (only axes to verify).

    Returns {'result': OK|MISMATCH|UNVERIFIED, 'axes': {axis: {requested, actual, status}}, 'actual': {...}}.
    """
    gv = collect.parse_gradle_version(gradle_version_text or "")
    env = collect.parse_build_environment(build_env_text or "")
    axes, actual = {}, {}
    for axis, req in requested.items():
        if axis == "gradle":
            act = [gv["gradle"]] if gv.get("gradle") else []
        else:
            act = sorted(env.get(axis, ()))
        actual[axis] = act[0] if len(act) == 1 else (act or None)
        if not act:
            status = "UNVERIFIED"
        elif act == [req]:
            status = "OK"
        else:
            status = "MISMATCH"
        axes[axis] = {"requested": req, "actual": actual[axis], "status": status}
    sts = {a["status"] for a in axes.values()}
    result = "MISMATCH" if "MISMATCH" in sts else ("UNVERIFIED" if "UNVERIFIED" in sts else "OK")
    return {"result": result, "axes": axes, "actual": actual,
            "gradle_info": gv}
