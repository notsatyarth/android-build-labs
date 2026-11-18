# probe3

What does one upgrade cost in build time and memory? Two pairs on nowinandroid, one CI runner type (ubuntu-24.04, x86 Linux).

| Pair | Old | New | Only difference |
|---|---|---|---|
| K | Kotlin 2.3.0 at nowinandroid `2982e63` (AGP 9.3.2, Gradle 9.7.1, KSP 2.3.4) | Kotlin 2.5.0-RC, same commit | the catalog's `kotlin` key (the Compose compiler plugin follows it); both sides carry the line-64 fix from `labs/kotlin-readiness/fix_line64.sh` |
| A | `ade8065442` (AGP 8.13.1) | `2c56ce13b` (AGP 9.0.0) | old-vs-new pair p2 |

- Time (pair K): `time_k.sh` runs gradle-profiler 0.26.0 with `labs/old-vs-new/scenarios.conf` (config, clean, nonabi;
  warm-ups as there, `iterations` input, default 10), old side then new side, through `labs/old-vs-new/run_commit.sh` and
  `agg.py`, so `agg.json` has the old-vs-new shape. Every scenario adds `-Dorg.gradle.isolated-projects=false` on both
  sides: `2982e63` enables Isolated Projects and Gradle refuses `--no-configuration-cache` with it ("Configuration Cache
  cannot be disabled when Isolated Projects is enabled."). Pair A time is not re-measured: `data/probe3/` holds the
  `agg.json` of old-vs-new run 44225818987 (p2, 10 iterations).
- Memory (both pairs): `mem.sh` primes both sides, then runs N clean builds per side
  (`:app:assembleDemoDebug --no-build-cache --rerun-tasks --no-configuration-cache`, plus the Isolated Projects switch
  for K), old and new interleaved, with `./gradlew --stop` and no Kotlin daemon before each build, under
  `tools/procwatch/procwatch.py --interval 0.5 --cpu --meta`. `memsum.py` turns the CSVs into `mem-<pair>.json`: peak RSS
  of the Gradle daemon, of each Kotlin daemon, of all Gradle workers summed, of AAPT2, peak total RSS and when, Kotlin
  daemon count, build wall time.
- `analyse.py`: old and new median, percent change of medians, a 95 % percentile bootstrap interval of that change
  (10,000 resamples, fixed seed), min and max; "measurable" when the interval excludes 0. Memory measures are also
  reported without build 1 (a fresh runner's first build can be a cold outlier).
- `compare.py`: both sides built, the resolved KGP is the requested one with AGP, KSP and Gradle equal, pair A CI time
  directions against the macOS medians of old-vs-new.
- Workflow: `probe3` (inputs `nia_ref`, `old_kotlin`, `new_kotlin`, `iterations`, `builds`, `java`).
