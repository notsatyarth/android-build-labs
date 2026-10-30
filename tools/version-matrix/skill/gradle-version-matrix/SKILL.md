---
name: gradle-version-matrix
description: Tests whether an Android/Gradle project builds with the next Gradle, AGP, Kotlin (KGP) or KSP version, or with next-version flags (AGP 10 simulation, kotlin.experimental.tryNext, Gradle feature previews, --warning-mode=fail), one change per cell, using the vmatrix.py harness. Reports failures by owner (Gradle, AGP, KGP, KSP, plugin, project). Use for "try the next AGP/Kotlin/Gradle", "will AGP 10 break us", "turn on next-version flags", or "which tool broke the build". Never edits the user's working tree.
compatibility: Needs Python 3.9+, a Gradle project with ./gradlew, git, JDK(s) installed. Runs real Gradle builds (slow, network).
---

# gradle-version-matrix

Drives `vmatrix.py` (standard library only). Set `VM=tools/version-matrix/vmatrix.py` relative to the repo root, or the path in `$VMATRIX_HOME`. Run it from the harness repo, pass the Android project with `--project` or `"project"` in the config. Full reference: `tools/version-matrix/README.md`.

## Safety rules (always)

1. Never edit the user's project tree. The harness runs each cell in a `git worktree` or a copy under `--out`. If a cell fails, propose a fix as a diff or text; apply it only in a scratch copy, and only if the user asks.
2. Never `git push`, never commit to the user's branches, never publish build scans (no `--scan`, no `-Dscan`), never upload logs.
3. Before any real `run` (starts Gradle, can take an hour per cell): show the plan and the dry run, state how many cells and the timeout, and ask. `discover`, `plan`, `run --dry-run`, `report` are safe without asking.
4. One Gradle build at a time. Warn if other Gradle builds run; suggest `--gradle-user-home ~/.vmatrix-gradle`.
5. Never state a version, date or content for Gradle 10, AGP 10 or Kotlin 2.5 that the tool output or a source does not show. There is no "KGP 10". Say "simulation of AGP 10 behaviour", not "AGP 10".
6. Uncommitted changes are not in a worktree. Tell the user, or ask them to commit.

## Flow A: try the next AGP / Kotlin / Gradle

1. `python3 $VM discover --json` and show latest stable/rc/beta/alpha/next per tool. Network failure: retry with `--offline` and say the data is cached.
2. Write `matrix.json` (example: `example-matrix.json` in this folder): `{"name":"baseline"}` first, then one cell per tool with exactly one axis changed: `{"name":"agp-next","axes":{"agp":"@next"}}`, same for `gradle`, `kotlin`, `ksp`. Do not combine axes unless the user asks (then name the cell `agp+kotlin` and say the result cannot be attributed to one tool). Use exact versions if the user names one.
3. `python3 $VM plan --config matrix.json --json`: check resolved versions and skips (a missing channel or an unchanged pin is SKIPPED, not a failure).
4. `python3 $VM run --config matrix.json --dry-run --json`: show edits and commands.
5. Ask. Then run one cell at a time: `python3 $VM run --config matrix.json --cells baseline --out out --json`, read it, then each next cell with `--resume`. Baseline first: if it fails, stop; nothing else is interpretable.
6. Read `out/report.json` (schema `vmatrix-report/1`). In this order:
   - Any cell with `outcome` INVALID or a `guard` axis not OK: the requested version did not run. Report it as a harness or resolution problem and give no result for that cell.
   - `outcome` FAIL / TIMEOUT / ERROR: read `first_error`, then `new_by_owner` (problems new versus baseline), then the log path in `steps` for evidence.
   - PASS: still list `new_by_owner` deprecations; new warnings are the upgrade work.
7. Summarise as a table: cell, requested vs actual (guard), outcome, new problems by owner, first error (quote it). Owner is a heuristic: each problem has a `rule`; say so and check the stack frames before blaming a tool.
8. For each failure propose the minimal fix (a catalog edit, a removed property, a plugin bump) or the owner tracker to file: AGP -> Google Issue Tracker (needs a browser; give the title and repro, do not claim it exists), Gradle -> github.com/gradle/gradle issues, Kotlin/KGP/KSP -> youtrack.jetbrains.com (KT) or github.com/google/ksp, third-party plugin -> its repo. Search for an existing issue first (`gh search issues`, YouTrack API); never file one yourself without being asked.

## Flow B: turn on next-version flags

Flag cells change no versions; they run the current versions with `-P` properties or Gradle args:

| Cell | Setting | Notes |
|---|---|---|
| `flag-simulate-agp10` | `"flags":{"android.simulateAgpVersionBehavior":"10.0.0"}` and `"java_home":"<JDK 21>"` | Needs JDK 21 or AGP stops first with "requires Java 21". Experimental. Find JDK 21 with `/usr/libexec/java_home -v 21` (macOS) and tell the user which path you use. |
| `flag-kotlin-tryNext` | `"flags":{"kotlin.experimental.tryNext":"true"}` | Compiles with the next language version; read the build-end "compiled with Kotlin x.y" summary. |
| `flag-warning-fail` | `"gradle_args":["--warning-mode=fail"]` | Any Gradle deprecation fails the build; useful as a gate, noisy as a first look (use `all`). |
| Gradle feature preview | not a cell | Previews are enabled in `settings.gradle(.kts)` with `enableFeaturePreview(...)`; the harness does not edit settings. Use a scratch copy with that line added, or ask the user to add it on a branch. |

## Flow C: reading false alarms (example: useAndroidX)

On nowinandroid with AGP 9.3.2 and the simulation on JDK 21, the build fails at `android.useAndroidX=true` ("removed in version 10.0"), and after deleting that line fails again because AGP's AndroidX check wants it set. The simulation contradicts itself, so the failure says nothing about real AGP 10 (observed in the next-version switches lab, 2026-10-26; cause not established). Rules drawn from this:
- A flag-cell failure is a statement about the flag, not about the next version, until a second source (release notes, tracker, a real pre-release cell) agrees.
- If fixing the first error produces an opposite error, report the loop, not "X will break".
- Say what is known (exact message, which property) and what is not (cause).

## Output to the user

Short summary first (what ran, what did not, what is invalid), table, then proposed fixes and trackers, then what was not run. Include the `--out` path so they can open `report.md`. Do not report timings from INVALID cells.
