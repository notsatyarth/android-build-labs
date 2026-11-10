Tier 2 flag probe results (labs/flag-builds, workflow `flag-builds`): nowinandroid built once per flag, each flag set alone
with `-P<flag>=<value>`. File name = AGP and Kotlin versions the cells ran with.

First run: nowinandroid 2982e63, AGP 9.3.2, Kotlin 2.3.0, Gradle 9.7.1, JDK 21, x86 Linux runner, `:app:assembleDemoDebug`
(CI run 42863141845; the aggregate step of that run failed, so the JSON was produced by running `aggregate.py` on the
run's per-flag artifacts; the workflow is fixed since).

Read the results with care:
- `pass` means the build succeeded with that value. It does not show the flag changed anything: some values equal the
  current default. The log mentions the flag only where the harness echoes the command line.
- Test values come from the flag name and stage (`value_basis` in probes/flags.json), not from a source that states them.
- `android.simulateAgpVersionBehavior` is experimental and undocumented.
- `fail` is "failed with this value", with the failing step and first error line.
