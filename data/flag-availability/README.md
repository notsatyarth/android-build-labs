Flag availability per AGP and Kotlin plugin version (tier 1 flag probe, `tools/version-matrix/probes/flag_availability.py`).
Read from the published plugin jars on Google Maven and Maven Central: a flag is "declared" when its name is in the plugin's
options or properties classes, "mentioned" when it only appears elsewhere, "absent" when it is in no class.
Derived from bytecode (internal, not public API). "declared" says the name exists, not what its default is.
Regenerate: `python3 -m probes.flag_availability --tool agp --versions <versions.json> --cache <dir> --out agp.json` from tools/version-matrix.
