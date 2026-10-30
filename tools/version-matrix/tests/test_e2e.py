"""End-to-end tests with a fake ./gradlew. No real Gradle build is started."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest

import helpers
import vmatrix
from vmlib import project


def cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = vmatrix.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class E2E(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.proj = helpers.make_project(os.path.join(self.tmp, "proj"))
        self.out = os.path.join(self.tmp, "out")
        self.cfgfile = os.path.join(self.tmp, "m.json")

    def write_cfg(self, cells, **extra):
        cfg = {"project": self.proj, "tasks": [["help"], ["assemble"]], "daemon_cleanup": "stop",
               "cells": cells}
        cfg.update(extra)
        helpers.wr(self.cfgfile, json.dumps(cfg))

    def run_json(self, *extra):
        code, out, err = cli("run", "--config", self.cfgfile, "--out", self.out, "--json", *extra)
        return code, json.loads(out), err

    def test_pass_and_guard_ok_and_project_untouched(self):
        before = helpers.rd(os.path.join(self.proj, "gradle", "libs.versions.toml"))
        self.write_cfg([{"name": "baseline"}, {"name": "agp-new", "axes": {"agp": "9.4.0", "gradle": "9.8.2"}}])
        code, rep, _ = self.run_json()
        self.assertEqual(code, 0)
        c = {x["name"]: x for x in rep["cells"]}
        self.assertEqual(c["agp-new"]["outcome"], "PASS")
        self.assertEqual(c["agp-new"]["guard"]["result"], "OK")
        self.assertEqual(c["agp-new"]["guard"]["actual"]["agp"], "9.4.0")
        self.assertEqual(c["agp-new"]["guard"]["actual"]["gradle"], "9.8.2")
        self.assertEqual(c["baseline"]["guard"]["actual"]["agp"], "9.3.2")
        # deprecation parsed from the fake build output, owner Gradle
        self.assertEqual(c["baseline"]["by_owner"], {"Gradle": {"deprecation": 1}})
        self.assertEqual(c["agp-new"]["new_vs_baseline"], [])
        # user's tree unchanged, workspaces cleaned, reports written
        self.assertEqual(helpers.rd(os.path.join(self.proj, "gradle", "libs.versions.toml")), before)
        self.assertFalse(os.path.exists(os.path.join(self.out, "work", "agp-new")))
        md = helpers.rd(os.path.join(self.out, "report.md"))
        self.assertIn("| agp-new |", md)
        self.assertIn("agp 9.4.0*", md)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "report.json")))
        self.assertTrue(os.path.isfile(os.path.join(self.out, "agp-new", "01-help.log")))

    def test_ignored_override_is_invalid(self):
        self.write_cfg([{"name": "baseline"}, {"name": "agp-new", "axes": {"agp": "9.4.0"}}])
        os.environ["FAKE_IGNORE_AGP"] = "1"
        self.addCleanup(os.environ.pop, "FAKE_IGNORE_AGP", None)
        code, rep, _ = self.run_json()
        c = {x["name"]: x for x in rep["cells"]}
        self.assertEqual(c["agp-new"]["outcome"], "INVALID")
        self.assertEqual(c["agp-new"]["guard"]["axes"]["agp"]["status"], "MISMATCH")
        self.assertEqual([s["role"] for s in c["agp-new"]["steps"]], ["version", "guard"])  # tasks not run
        self.assertEqual(c["baseline"]["outcome"], "PASS")
        self.assertEqual(code, 3)
        self.assertEqual(cli("report", "--out", self.out, "--fail-on", "never")[0], 0)
        self.assertEqual(cli("report", "--out", self.out, "--fail-on", "invalid")[0], 3)

    def test_failure_classified_and_exit_code(self):
        self.write_cfg([{"name": "baseline"}, {"name": "bad", "axes": {"kotlin": "2.5.0-Beta2"},
                                               "tasks": [["FAILTASK"]]}])
        code, rep, _ = self.run_json()
        bad = rep["cells"][1]
        self.assertEqual(bad["outcome"], "FAIL")
        self.assertEqual(bad["failed_step"], "01-FAILTASK")
        self.assertEqual(bad["first_error"]["owner"], "Gradle")
        self.assertEqual(code, 1)
        self.assertEqual(cli("report", "--out", self.out, "--fail-on", "invalid")[0], 0)

    def test_timeout(self):
        self.write_cfg([{"name": "slow", "tasks": [["SLEEP"]], "timeout_sec": 1}])
        code, rep, _ = self.run_json()
        self.assertEqual(rep["cells"][0]["outcome"], "TIMEOUT")
        self.assertEqual(code, 1)

    def test_skip_identical_and_unknown_axis_and_flags_cell(self):
        self.write_cfg([{"name": "same", "axes": {"agp": "9.3.2"}},
                        {"name": "flag", "flags": {"android.simulateAgpVersionBehavior": "10.0.0"}}])
        code, rep, _ = self.run_json()
        c = {x["name"]: x for x in rep["cells"]}
        self.assertEqual(c["same"]["outcome"], "SKIPPED")
        self.assertEqual(c["flag"]["outcome"], "PASS")
        cmds = [" ".join(s["cmd"]) for s in c["flag"]["steps"]]
        self.assertTrue(all("-Pandroid.simulateAgpVersionBehavior=10.0.0" in x for x in cmds[1:]))
        self.write_cfg([{"name": "x", "axes": {"nope": "1"}}])
        self.assertEqual(cli("plan", "--config", self.cfgfile)[0], 2)

    def test_dry_run_writes_nothing(self):
        self.write_cfg([{"name": "baseline"}, {"name": "g", "axes": {"gradle": "9.8.2"}}])
        code, out, _ = cli("run", "--dry-run", "--config", self.cfgfile, "--out", self.out, "--json")
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertTrue(d["dry_run"])
        cmds = d["commands"][1]["steps"]
        self.assertEqual(cmds[0]["cmd"], ["./gradlew", "--version"])
        self.assertEqual(d["commands"][1]["edits"][0]["new"], "9.8.2")
        self.assertFalse(os.path.exists(self.out))

    def test_plan_errors(self):
        self.write_cfg([{"name": "a"}], project=os.path.join(self.tmp, "missing"))
        code, _, err = cli("plan", "--config", self.cfgfile)
        self.assertEqual(code, 2)
        self.assertIn("not a directory", err)

    def test_offline_channel_without_cache(self):
        self.write_cfg([{"name": "n", "axes": {"agp": "@next"}}])
        code, _, err = cli("plan", "--config", self.cfgfile, "--offline", "--cache",
                           os.path.join(self.tmp, "none.json"))
        self.assertEqual(code, 2)
        self.assertIn("offline", err)

    def test_channel_resolution_from_cache(self):
        cache = os.path.join(self.tmp, "c.json")
        helpers.wr(cache, json.dumps({"agp": {"fetched_at": "t", "fetched_epoch": 1, "entries": [
            {"version": "9.3.2", "channel": "stable"}, {"version": "9.5.0-rc01", "channel": "rc"}]}}))
        self.write_cfg([{"name": "n", "axes": {"agp": "@rc"}}, {"name": "b", "axes": {"agp": "@beta"}}])
        code, out, _ = cli("plan", "--config", self.cfgfile, "--offline", "--cache", cache, "--json")
        plan = json.loads(out)
        self.assertEqual(plan["cells"][0]["axes"], {"agp": "9.5.0-rc01"})
        self.assertIn("beta", plan["cells"][1]["skip"])


@unittest.skipUnless(shutil.which("git"), "git not available")
class WorktreeMode(unittest.TestCase):
    def test_worktree_cell_leaves_repo_clean(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        proj = helpers.make_project(os.path.join(tmp, "repo"), git=True)
        helpers.wr(os.path.join(proj, "local.properties"), "sdk.dir=/sdk\n")  # untracked; must be copied
        helpers.wr(os.path.join(proj, ".gitignore"), "local.properties\n")
        helpers.wr(os.path.join(tmp, "m.json"), json.dumps({
            "project": proj, "mode": "worktree", "tasks": [["help"]],
            "cells": [{"name": "k", "axes": {"kotlin": "2.5.0-Beta2"}}]}))
        out = os.path.join(tmp, "out")
        status = lambda: subprocess.run(["git", "status", "--porcelain"], cwd=proj, stdout=subprocess.PIPE,  # noqa: E731
                                        universal_newlines=True).stdout
        st_before = status()
        code, o, _ = cli("run", "--config", os.path.join(tmp, "m.json"), "--out", out, "--json",
                         "--keep-workdirs")
        rep = json.loads(o)
        self.assertEqual(rep["cells"][0]["outcome"], "PASS")
        ws = rep["cells"][0]["workspace"]
        self.assertTrue(os.path.isfile(os.path.join(ws, "local.properties")))
        self.assertIn("2.5.0-Beta2", helpers.rd(os.path.join(ws, "gradle", "libs.versions.toml")))
        self.assertNotIn("2.5.0-Beta2", helpers.rd(os.path.join(proj, "gradle", "libs.versions.toml")))
        project.remove_workspace(proj, ws, "worktree")
        wl = subprocess.run(["git", "worktree", "list"], cwd=proj, stdout=subprocess.PIPE,
                            universal_newlines=True).stdout.strip().splitlines()
        self.assertEqual(len(wl), 1)
        self.assertEqual(status(), st_before)
        self.assertTrue(any("uncommitted" in w for w in rep["cells"][0]["warnings"]))


if __name__ == "__main__":
    unittest.main()
