"""Assign an owner to each problem record using vmlib/owners.rules.json (or --rules FILE)."""
import json
import os
import re

DEFAULT_RULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "owners.rules.json")


def load_rules(path=None):
    with open(path or DEFAULT_RULES, "r", encoding="utf-8") as f:
        data = json.load(f)
    rules = []
    for r in data["rules"]:
        fl = re.I if "i" in r.get("flags", "") else 0
        rules.append(dict(r, _re=re.compile(r["regex"], fl | re.M),
                          _loc=re.compile(r["also_location"]) if r.get("also_location") else None))
    return {"default_owner": data.get("default_owner", "Unknown"), "rules": rules}


def _field(rec, name):
    if name == "text":
        return rec.get("text") or ""
    if name == "location":
        return rec.get("location") or ""
    if name == "frames":
        return "\n".join(rec.get("frames") or [])
    if name == "group":
        return rec.get("group") or ""
    return "\n".join([rec.get("text") or "", rec.get("location") or "", rec.get("group") or "",
                      "\n".join(rec.get("frames") or [])])


def classify(rec, ruleset):
    """Return (owner, rule_id). Informational kinds are still classified."""
    for r in ruleset["rules"]:
        if r["_re"].search(_field(rec, r["field"])):
            if r["_loc"] and not r["_loc"].search(rec.get("location") or ""):
                continue
            return r["owner"], r["id"]
    return ruleset["default_owner"], "default"


def classify_all(recs, ruleset):
    for r in recs:
        r["owner"], r["rule"] = classify(r, ruleset)
    return recs
