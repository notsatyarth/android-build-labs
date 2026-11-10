History of nowinandroid (10 commits, evenly spaced over the 281 commits since 2025-01-01, oldest to newest) built with the
tool versions each commit pins. One row per commit: date, subject, Gradle/AGP/Kotlin/KSP pins, build outcome, duration,
version-guard result, configuration cache probe, Gradle deprecation probe (with the deprecation messages and origins).

Source: CI run 42876138951 (workflow `history-series`, x86 Linux runner, JDK 21, one cold run per commit, `help` then
`:app:assembleDemoDebug`). The probe results were recomputed from that run's saved logs and reports by
`labs/history-series/aggregate_history.py` after the deprecation parser was fixed (it first missed the wording
"This will fail with an error in Gradle 10", which made 3 commits look clean).

Read with care:
- Durations are single cold runs; they include dependency downloads. Not a build-time comparison across commits.
- A build outcome of FAIL (commit 3bc6ed6d: `:build-logic:convention:compileKotlin`, AGP 9.0.0-alpha14) is a result for that commit
  on this runner; the deprecation probe is inconclusive there because the log has no deprecation section from a finished build.
- `pass` for deprecations means no recognised Gradle deprecation message in the `help` log, with `--warning-mode=all`;
  it does not cover AGP's or Kotlin's own deprecation warnings.
- Evenly spaced commits are a sample, not the whole history.
