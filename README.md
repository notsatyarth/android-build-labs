# android-build-labs

Small, reproducible experiments on how the Android Gradle Plugin (AGP), the Kotlin Gradle Plugin (KGP), KSP and Gradle interact: daemons, memory, classloaders, variants and version upgrades. They are the evidence behind the talk "Android builds to the future!" (Droidcon Bengaluru, 20 November 2026).

Every lab runs on a laptop (macOS or Linux) and most also run as a manually triggered GitHub Actions workflow, so anyone can re-run them and read the raw logs.

Results from GitHub-hosted runners are x86 Linux numbers. Do not compare their timings or memory with laptop numbers. Compare outcomes (generated or not, cache reused or not, how many daemons), and compare numbers only within one machine.

## Layout

| Path | Question it answers | Runs in CI |
|---|---|---|
| `samples/ksp-root-classpath/` | Does KSP still run when AGP, or only AGP's API jar, is on a parent classloader (root `buildscript`, `buildSrc`)? | yes: `ksp-root-classpath` |
| `samples/missing-dimension/` | What `missingDimensionStrategy` and `matchingFallbacks` actually pick when a library has a flavor the app lacks | yes: `missing-dimension` (`checkpoints.py` replays checkpoints 1 to 5) |
| `samples/kmp-single-variant/` | The KMP Android library plugin has one variant: what happens to build types and flavors | yes: `kmp-single-variant` (`checkpoints.py` replays c1 to c3c) |
| `samples/nia-variants/` | How many variants and tasks nowinandroid configures, and what `beforeVariants` filtering saves (init script) | yes: `nia-variants` (`run.sh`, `compare.py`) |
| `labs/compact-headers/` | Does `-XX:+UseCompactObjectHeaders` (JDK 25, JEP 519) reduce Gradle and Kotlin daemon memory? | yes: `compact-headers` (ABBA series, `compare.py`) |
| `labs/daemons-ide-cli/` | Do an IDE-style build (Tooling API) and a CLI build share a daemon and a configuration cache entry? What happens to the Kotlin daemon under `--no-daemon`, and with two worktrees building at once? | planned |
| `labs/old-vs-new/` | Old versus new nowinandroid commits with gradle-profiler: configuration and build time, daemon memory | no (needs gradle-profiler built from source) |
| `tools/version-matrix/` | Run one project against a matrix of Gradle, AGP, Kotlin and KSP versions and report what broke and who owns it | example workflows in `ci/` |
| `tools/procwatch/` | Sample every JVM of a build (RSS, `-Xmx`, GC, plus macOS footprint or Linux RSS+swap) into a CSV | used by the labs |
| `tools/time-share/` | Attribute build time to Gradle, AGP, Kotlin and KSP from a build operation trace | no |

`MANIFEST.tsv` lists where each file came from in the author's original lab setup.

## Running locally

Each lab's script header lists what it needs. In general: a JDK in `JAVA_HOME` (17 unless stated), `ANDROID_HOME` pointing at an Android SDK, Python 3 (standard library only), and for the nowinandroid labs a checkout of [android/nowinandroid](https://github.com/android/nowinandroid) at the commit named in the script (default path `$HOME/nowinandroid`, override with `NIA` or `LAB`).

```bash
# Example: one KSP cell
cd samples/ksp-root-classpath
./run.sh demo 8.10.1 2.2.0 2.2.0-2.0.2 8.14.3 C   # layout C: buildSrc implementation(gradle-api)
```

## Running in GitHub Actions

Workflows are `workflow_dispatch` only (Actions tab, "Run workflow"). Each uploads its logs as artifacts and writes a summary table. No workflow publishes a build scan or needs a secret.

## Rules for these labs

- Change one thing per run, and record versions, JDK and machine with every result.
- A result that does not reproduce is a result. Report it.
- No build scans, no credentials, no private code.

## License

Apache License 2.0, see `LICENSE`. nowinandroid is not vendored; it is cloned at run time under its own Apache 2.0 license.
