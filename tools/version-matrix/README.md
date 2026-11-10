# vmatrix: version-matrix shadow-job harness

Runs one Gradle project against a matrix of Gradle, AGP, Kotlin (KGP) and KSP versions, one change per cell, and reports what broke and who owns it. Plan and rationale and results are in the author's research notes (not published). Modelled on Gradle's own smoke tests, plus the check those tests lack: proof that the requested version is the one that ran.

Status: written 2026-10-26. Unit and end-to-end tests pass against a fake `./gradlew`. It has not been run against a real Gradle build yet (see "Untested").

- Python 3.9+, standard library only, no pip. macOS and Linux (uses `./gradlew`, `ps`, process groups). Windows is not supported.
- Non-interactive. Progress goes to stderr. `--json` makes stdout one JSON document. Exit codes below.

## Quick start

```bash
cd tools/version-matrix
python3 vmatrix.py discover                       # latest stable / rc / beta / alpha / next per tool
python3 vmatrix.py plan --config matrix.example.json
python3 vmatrix.py run  --config matrix.example.json --dry-run     # prints edits and commands only
python3 vmatrix.py run  --config matrix.example.json --out out --gradle-user-home ~/.vmatrix-gradle
python3 vmatrix.py report --out out               # re-classify logs, rewrite report.json / report.md
python3 -m unittest discover tests                # from tools/version-matrix, or: discover tools/version-matrix/tests from the repo root
```

## Subcommands

| Command | Does | Writes |
|---|---|---|
| `discover [--tools gradle,agp,kotlin,ksp] [--channels ...] [--offline] [--refresh]` | Latest version per channel | discovery cache only |
| `plan --config F [--project P]` | Resolves `@channel` values, lists cells, planned edits, skips | nothing |
| `run --config F [--dry-run] [--out DIR]` | Runs cells one at a time, then collects, classifies and reports | `DIR/` (logs, `cell.json` per cell, `report.*`) |
| `report --out DIR` | Re-parses logs with current rules, rewrites reports | `DIR/report.*` |

Common flags: `--project`, `--cells a,b`, `--json`, `--offline`, `--refresh`, `--cache FILE`, `--java-home`, `--gradle-user-home`. `run` also: `--resume` (keep finished cells), `--keep-workdirs`, `--workspace`, `--mode auto|worktree|copy`, `--ref`, `--timeout SEC`, `--daemon-cleanup none|stop|stop+kill`, `--rules FILE`, `--fail-on never|invalid|any`.

**Per-cell `ref`.** A cell may set `"ref": "<commit, tag or branch>"` in the config. The harness then reads the pins (wrapper, version catalogs) and plans the edits from that commit, builds a worktree at it, and the version guard checks against that commit's pins. The working tree is not touched. A ref that does not resolve skips the cell with a reason. Without `ref` a cell uses `--ref` (default HEAD) as before. Each `cell.json` records `ref`, `commit` and `pins`.

Exit codes: `0` ok; `1` a cell FAILED, TIMEOUT or ERROR (`--fail-on any`, default); `2` usage, config or discovery error; `3` a cell is INVALID (always, unless `--fail-on never`). `--fail-on invalid` makes breakage of a next version a normal result and only a harness or guard problem red.

## How a cell runs

1. Workspace: `git worktree add --detach <out>/work/<cell> <ref>` (or a copy without `.git`, `build`, `.gradle` when the project is not a git repo). `local.properties` is copied in (`copy_files`). The user's tree is never edited; uncommitted changes are not in a worktree (a warning is recorded). Removed after the cell unless `--keep-workdirs`.
2. Edits: the cell's axes are written into `[versions]` of every `*.versions.toml` that has the key (so a separate `build-logic` catalog is covered; nowinandroid's build-logic reads `../gradle/libs.versions.toml`, so one file), and `distributionUrl` of `gradle/wrapper/gradle-wrapper.properties` (the checksum line is dropped). Catalogs declared inside `settings.gradle.kts` are not handled; set `catalog_files` / `catalog_keys` or extend `project.py`.
3. Flag cells: `flags` become `-Pkey=value` (for example `android.simulateAgpVersionBehavior=10.0.0`, `kotlin.experimental.tryNext=true`); `gradle_args` are appended (for example `--warning-mode=fail`; a cell option of the same name replaces the one in the common arguments).
4. Steps, each one `./gradlew` process with its own log and timeout (process group is killed on timeout): `--version`; the guard (`buildEnvironment :app:buildEnvironment`); then each entry of `tasks` (default `help`, then `:app:assembleDemoDebug`) with `--console=plain --warning-mode=all --stacktrace`. The first failing step stops the cell.
5. Cleanup: `./gradlew --stop` in the workspace, optionally `stop+kill` (kills daemon processes that appeared during the cell).

Concurrent builds: `--stop` stops every daemon of that Gradle version in the same `GRADLE_USER_HOME`, and `stop+kill` kills any new daemon process. If other Gradle builds run on the machine, set `--gradle-user-home` (isolated daemons and caches, slower first run) or `--daemon-cleanup none`.

## Version guard

After `--version` and `buildEnvironment` the harness compares what ran with what was requested, for every axis in the cell (the project's current pins plus the cell's change):

- Gradle: `Gradle x.y.z` from `--version`.
- AGP: `com.android.tools.build:gradle` and `com.android.*` plugin markers in `buildEnvironment`.
- KGP: `kotlin-gradle-plugin` and `org.jetbrains.kotlin.*` markers. KSP: `symbol-processing-gradle-plugin` and its marker. "A -> B" takes B (resolved).

Result per axis: `OK`, `MISMATCH` (different, or more than one version seen) or `UNVERIFIED` (not seen). Any non-OK result with a successful guard step makes the cell `INVALID`, and its tasks are not run. If the guard step itself fails (for example the version does not resolve) the cell is `FAIL` with `guard: UNVERIFIED`. The guard runs before the tasks (same configuration, saves hours on a bad cell). Limit: it checks the classpath of the projects named in `guard_tasks`, not every project.

## Discovery

| Tool | Source | Channels |
|---|---|---|
| AGP | Google Maven `com/android/tools/build/gradle/maven-metadata.xml` | stable, rc, beta, alpha, dev |
| KGP | Maven Central `kotlin-gradle-plugin` metadata | stable, rc, beta, alpha, milestone, dev |
| KSP | Maven Central `symbol-processing-gradle-plugin` metadata | stable (and pre-releases if published) |
| Gradle | `services.gradle.org/versions/all` | stable, rc, milestone, nightly, release-nightly |

In a config, `"agp": "@rc"` means "highest rc newer than the latest stable"; `@next` is the highest rc, beta, alpha or milestone newer than stable; `@latest` the highest non-dev; `@stable`; `@nightly` (Gradle; uses the snapshot download URL). A channel with no candidate makes the cell `SKIPPED` with a reason. A cell identical to the current pins is also skipped. The cache lives in `~/.cache/vmatrix/discover.json` (override `--cache` or `$VMATRIX_CACHE`), is reused for 24 h, and is the fallback when the network fails; `--offline` never uses the network and errors if there is no cache. KSP versions are not paired with a Kotlin version automatically: if a Kotlin cell needs a different KSP, add `"ksp": "..."` to the cell.

## Collector and classifier

Per cell the logs of all steps are parsed into records `{kind, text, group, location, frames, count, source}`, deduplicated:

- `failure`: the "What went wrong" block of `FAILURE: Build failed`, with location and stack frames.
- `deprecation`: Gradle deprecation lines plus their `at ...` trace (`--stacktrace` / `-Dorg.gradle.deprecation.trace=true`), AGP `WARNING: ... deprecated` blocks, "Problem found:" blocks that mention deprecation.
- `problem`: other "Problem found:" blocks (Problems API console rendering, with group from `(in A > B)` or `(id: ...)`).
- `warning` / `error`: Kotlin `w:` / `e:` lines, other AGP `WARNING:` blocks, configuration cache problem summaries.
- `build/reports/problems/problems-report.html` (copied into the cell directory) is parsed best effort: JSON blobs in `<script>` tags are walked for entries with `problemId` or `definition` plus a label. This is Gradle's internal, undocumented format (it changed in 9.9 and may change in patch releases); a format change yields zero entries and a note, never a crash. The supported way to read problems is the Tooling API (see `Talk/Part 4 Research/Part 4 Seam 4 Problems API.md`); a Tooling API runner is not part of this harness.

Owner rules are data: `vmlib/owners.rules.json` (override with `--rules`). Ordered, first match wins, each rule is a regex on `text`, `location`, `frames`, `group` or `any`. Owners: Gradle, AGP, KGP/Kotlin, KSP, Other plugin, Project, Unknown. Order matters and is the design: explicit tool names in the message first (`com.android.`, `org.jetbrains.kotlin`, `com.google.devtools.ksp`, `android.*` options); compiler diagnostics located in project sources are Project; then stack frames by package (a Gradle deprecation raised from `com.android.` frames is blamed on AGP, one raised only from `org.gradle.` frames stays Gradle); then generic Gradle text; then project files. Every classified record carries its `rule` id, so a wrong owner is debuggable and the classification is a heuristic, not a fact. Reclassify after editing rules with `vmatrix.py report --out DIR`.

## Report

`report.json` (schema `vmatrix-report/1`): `project`, `summary` (outcome counts), `cells[]` with `requested`, `axes` (what changed), `flags`, `guard` (per axis requested / actual / status), `outcome` (`PASS`, `FAIL`, `TIMEOUT`, `INVALID`, `ERROR`, `SKIPPED`), `failed_step`, `steps[]` (cmd, exit, duration, log path), `problems[]` (with `owner`, `rule`, `signature`), `by_owner`, `first_error`, `configuration_cache`, `new_vs_baseline`, `new_by_owner`, `duration_s`. `report.md`: table (cell, requested, actual and guard, outcome, problems by owner, top problems, duration; `*` marks the changed version) plus a section per cell. New versus baseline compares problem signatures (digits and paths normalised) with the cell flagged `baseline` (or the cell with no change).

## Config (`matrix.example.json`)

Keys: `project`, `mode`, `ref`, `workspace`, `tasks` (list of arg lists or strings), `gradle_args`, `guard_tasks`, `timeout_sec`, `catalog_keys` (axis to candidate catalog keys; default `androidGradlePlugin`/`agp`, `kotlin`, `ksp`), `catalog_files`, `copy_files`, `java_home`, `gradle_user_home`, `daemon_cleanup`, `problems_report`, `cells`. A cell: `name`, `axes` (`gradle`, `agp`, `kotlin`, `ksp`), `flags`, `gradle_args`, `tasks`, `java_home` (per-cell JDK; `~` expanded; also sets `PATH`), `env`, `timeout_sec`, `baseline`. Without `--config` the built-in matrix is baseline plus `@next` for Gradle, AGP and Kotlin. Project path precedence: `--project`, config, `$VMATRIX_PROJECT`.

## Calling it from an agent (Copilot, Claude, other harness)

All calls are non-interactive and exit with a code; parse stdout when `--json` is set.

```bash
python3 tools/version-matrix/vmatrix.py discover --json                       # what is out there
python3 tools/version-matrix/vmatrix.py plan --config matrix.json --json      # cells, skips, planned edits
python3 tools/version-matrix/vmatrix.py run  --config matrix.json --dry-run --json   # commands, safe
python3 tools/version-matrix/vmatrix.py run  --config matrix.json --out out --fail-on invalid --json > report.json
python3 tools/version-matrix/vmatrix.py report --out out --json               # after editing owners.rules.json
```

Suggested agent loop (for the skill in skill/): `discover` then `plan --json`; show the plan to the human; `run --dry-run`; real `run` only with the human's go-ahead (it starts Gradle builds and can take hours); read `report.json`: first check every cell's `guard.result` and `outcome == INVALID`, then `first_error` and `new_by_owner` for cells that FAIL; open the `log` paths in `steps` for evidence. Never report a number from an INVALID cell. Long runs: use `--resume --out DIR` to continue; each cell is written when it finishes. Exit 0/1/3 distinguish clean, broken, invalid; 2 is a config error to fix, not a finding.

## CI examples (documentation only, not installed or run)

`ci/github-actions.example.yml` (matrix of cells as parallel jobs, nightly schedule, step summary from `report.md`, artifacts) and `ci/gitlab-ci.example.yml`. Locally the same command runs all cells sequentially.

## Files

`vmatrix.py` CLI; `vmlib/` modules (`config`, `discover`, `project`, `runner`, `guard`, `collect`, `classify`, `report`, `util`) and `owners.rules.json`; `tests/` (unittest; fixtures marked SYNTHETIC; the e2e tests use a fake `gradlew` shell script and never start Gradle).

## Untested and known limits

- Never run against real Gradle, AGP alpha, Kotlin Beta or the Gradle nightly: the guard regexes match the documented shape of `--version` and `buildEnvironment` output, not a captured real output of this project. First run should be one baseline cell, then inspect the `guard` block in `cell.json`.
- Real console shapes for deprecations traces, Kotlin compiler problems and AGP problems are parsed from the next-version switches lab logs (not published) and Gradle documentation; the fixtures are synthetic.
- Problems report format is a guess at an internal format (see above).
- Gradle nightly download URL and checksum handling follow `versions/all`; not exercised.
- Timing is wall time per step only. No process tree or RSS sampling (use `procwatch.py` separately). No incremental-compile, lint or configuration-cache-reuse steps from the plan; add them as extra `tasks` entries.
- Pairs that cannot build (AGP needs a newer Gradle, JDK too old) show up as FAIL with a classified first error; that is a result, not a harness fault. Set `java_home` per cell when a pair needs another JDK.
