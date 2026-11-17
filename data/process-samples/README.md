# Frozen process samples

`release-run2.csv`: build 2 of 3 from GitHub Actions run 43173666753 (workflow `process-samples`, ubuntu-24.04, 4 vCPU), a clean nowinandroid build at commit 2982e63cb691ad49cd009aab43dc206fee6699c2 with tasks `:app:assembleDemoRelease :app:lintDemoRelease :app:testDemoDebugUnitTest`, sampled every 0.5 s by `tools/procwatch` with `--cpu --client`.

Columns: `elapsed_s, pid, ppid, kind, rss_mb, xmx, gc, cpu_s` (cpu_s = cumulative CPU seconds of the process; rss_mb = physical memory, not heap). Build 1 of that run is the cold outlier and is not kept. R8 and lint run inside the Gradle daemon and do not appear as separate processes.

`assemble-release-run2.csv`: build 2 of 3 from GitHub Actions run 44008662129 (workflow `process-samples`, ubuntu-24.04, 4 vCPU), a clean nowinandroid build at commit 2982e63cb691ad49cd009aab43dc206fee6699c2 with the task `:app:assembleRelease` (1,739 tasks, BUILD SUCCESSFUL in 5m 34s), sampled every 0.5 s by `tools/procwatch` with `--cpu --client`. Same columns as above. Peak summed RSS 10.1 GB (builds 1 to 3: 10.2, 10.1, 9.8 GB). No test worker: the task runs no tests.
