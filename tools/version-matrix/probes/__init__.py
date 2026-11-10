"""Feature probes. Each probe is a module with parse(...) plus a JSON config next to it.

Result states for every probe: pass, fail, inconclusive (with a reason), not_applicable.
A report that cannot be read is inconclusive, never pass and never zero problems.
"""
STATES = ("pass", "fail", "inconclusive", "not_applicable")


def result(state, reason=None, **fields):
    assert state in STATES, state
    out = {"state": state, "reason": reason}
    out.update(fields)
    return out
