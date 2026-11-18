# readiness-probe1

Does nowinandroid build on the next versions today, and if not, which tasks break? A baseline build and six builds that
each change one tool, all on the same nowinandroid commit, the same runner image, JDK 21, the same task command and
`--continue`, with no build cache:

| Build | Mode | Change |
|---|---|---|
| `baseline` | baseline | none: the commit's pins (AGP 9.3.2, Kotlin 2.3.0, Gradle 9.7.1 at 2982e63) |
| `1a-agp` | real | newest AGP in Google Maven metadata (alpha included) and the matching `androidTools` (AGP + 23.0.0, as nowinandroid's catalog asks). If AGP refuses the Gradle version ("Minimum supported Gradle version is X"), Gradle is raised to X and the build runs again; `build.json` records the raise, so this build is then not isolated to AGP |
| `1a-kotlin` | real | newest `kotlin-gradle-plugin` in Maven Central metadata (any channel) |
| `1a-gradle` | real | the newer of the Gradle nightly and release-nightly (services.gradle.org) |
| `1b-agp` | switch | `-Pandroid.simulateAgpVersionBehavior=10.0.0` |
| `1b-kotlin` | switch | `-Pkotlin.experimental.tryNext=true` |
| `1b-gradle` | switch | `--warning-mode=fail` and `enableFeaturePreview("NO_IMPLICIT_LOOKUP_IN_PARENT_PROJECTS")` appended to `settings.gradle.kts` (the preview the `next-version-switches` lab used) |

The switches are not AGP 10, Kotlin 2.5 or Gradle 10: they turn on announced behaviour in today's versions.

## Files

- `probe_config.json`: shared by every build: the task command (`:app:assembleDemoDebug testDemoDebugUnitTest
  -Proborazzi.test.verify=false`, demo variant like nowinandroid's own CI), common arguments, the build list, and the
  known baseline failures. `:feature:foryou:impl:compileProdDebugUnitTestKotlin` (unresolved import, prod variant) is
  listed there as a known baseline failure: it is not excluded with `-x`; the command does not request it, and if it
  ever fails it is not counted as new.
- `resolve.py NIA OUT.json`: resolves the versions at run time and records them with their sources.
- `probe.init.gradle`: works with the configuration cache and Isolated Projects (nowinandroid enables both, with
  configuration cache problems set to fail). A shared build service registered with
  `BuildEventsListenerRegistry.onTaskCompletion` writes one JSON line per finished task (success, up-to-date,
  from-cache, no-source, skipped, failed); `taskGraph.whenReady` writes the planned task list. A planned task with no
  event is `not-run` (an upstream task failed). No planned list after a failed build = configuration failed. It also
  logs `LAB-PROBE` markers: Gradle, JVM, warning mode, active feature previews (internal `FeatureFlags` service, best
  effort), AGP and KGP on the root project's classpath (present even when a subproject fails to configure), AGP in
  `:app`, KGP in `:app` and `:core:model`, and the Kotlin language version of every configured Kotlin compile task.
- `run_build.py BUILD --nia DIR --resolved resolved.json --out DIR`: edits the clone, runs `./gradlew --version`, stops
  the daemon (AGP prints some warnings once per daemon), runs the build, writes `build.json`: expected and proven
  versions, per-task outcomes, counts (failed, not-run, passed over the root build's task graph; included builds
  counted apart), first error lines of each failed task (Gradle's failure chain plus the first `e:` lines under the
  task's project directory), the first "What went wrong" blocks, and harness faults.
- `compare.py PARTS --run-id ID --csv OUT.csv --json OUT.json`: diffs each build with the baseline per task (new
  failures only, known baseline failures subtracted), prints Markdown, writes one CSV line per build.

## Harness fault rules

A build is a harness fault, never a pass, when: the init-script marker is missing; Gradle (`--version` and in-build),
the JVM (21) or AGP/KGP on the root classpath differ from what the build asked for; `:app` configured but logged no
AGP marker; or the switch has no proof: `1b-agp` needs AGP's experimental-option warning or a "removed in version
10.0" message, `1b-kotlin` needs every logged compile task at language version current + 1, `1b-gradle` needs warning
mode `Fail` and the feature preview active. A missing `build.json` (job crashed) is reported as a harness fault.

## Data

The `compare` job appends its CSV lines to `data/readiness-probe1/runs.csv` on the `probe-data` branch (artifacts
expire; the branch keeps the series). Columns: date, run_id, nia_commit, build, mode, tool, gradle, agp, kotlin, jvm,
gradle_raised_from, build_exit, configuration_failed, failed, not_run, passed, planned, new_failures_vs_baseline,
known_baseline_failures_seen, harness_fault, baseline_usable. Artifacts (logs, `build.json`, events) are kept 90 days.

Run: workflow `readiness-probe1` (`workflow_dispatch`, and weekly on Monday). One run at a time (concurrency group).
Numbers and outcomes are from x86 Linux runners; do not compare them with laptop numbers.

Local smoke test (macOS or Linux, JDK 21 in `JAVA_HOME`, Android SDK): `run_build.py` takes `--tasks "..."` to replace
the task command for a quick check; CI never uses it.
