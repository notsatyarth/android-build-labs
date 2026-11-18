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

## Results: run 44264907185 (attempt 2; mem-K from attempt 1)

Data in `data/probe3/run44264907185/` (`probe3.json` has every value). ubuntu-24.04 image 20261111, 4 vCPU, about 15.5 GiB,
Temurin 17.0.21; each job on its own runner (time-K: AMD EPYC 7763; mem-K: AMD EPYC 9V74; mem-A: Intel Xeon 6975P-C), so
compare within a pair only. Attempt 1 of time-K and mem-A failed in the unmeasured prime build on plugin resolution
(`com.android.lint:9.3.2` not found; `kotlin-stdlib-2.2.20.pom` could not be fetched from plugins.gradle.org); rerun once.
Resolved, pair K: Gradle 9.7.1, AGP 9.3.2, KSP 2.3.4 on both sides; KGP and Compose compiler plugin 2.3.0 vs 2.5.0-RC.

Measurable (95 % interval of the percent change of medians excludes 0):
- Pair K time: none of the three scenarios (clean -8.58 % [-18.6, 27.6], config +1.15 % [-13.2, 16.4], nonabi +3.85 % [-10.3, 18.5]).
- Pair K memory: peak total RSS -12.0 % [-20.4, -1.59] (8740 to 7700 MB; without build 1: -7.80 % [-19.3, -0.487]);
  second Kotlin daemon -25.1 % [-43.1, -0.221] with all builds, not measurable without build 1 (-21.8 % [-39.2, 0.871]).
- Pair A time (old-vs-new run 44225818987): config -28.2 %, nonabi -25.1 % measurable; clean +1.40 % [-16.2, 30.0] not.
- Pair A memory: nothing measurable.
- Two Kotlin daemons in every build of both pairs. No Gradle worker process was seen in any build.
- The gradle-profiler clean iterations still drift downwards on both sides (k230 61.6 s to 38.6 s, k250rc 70.2 s to
  38.6 s over the 10 measured iterations), so one warm-up is not enough for a steady state on these runners.
