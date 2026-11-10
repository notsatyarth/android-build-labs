# Dashboard

Static page. Reads `data.js`, which bundles the frozen JSON under `data/`. No network needed.

- Rebuild the data: `python3 docs/dashboard/build_data.py`
- Open locally: `python3 -m http.server -d docs/dashboard 8765`, then http://localhost:8765/ (or open `index.html` directly).
- Publish: GitHub Pages, source branch `main`, folder `/docs`. That is a repository setting and is not turned on by any script here.

Charts: build duration and outcome, configuration cache problems, Gradle deprecations (per commit, with the tool versions each commit pins), flag availability per AGP and Kotlin version, flag build results, and the KT-90672 fixture.
