#!/usr/bin/env python3
"""Convert the module build scripts of a nowinandroid checkout from Kotlin DSL to Groovy DSL.
Usage: convert.py NIA_DIR [--include-build-logic]
Mechanical rewrites cover the scripts that only use plugins{}, android{}, dependencies{} and simple blocks;
scripts that use Kotlin-only syntax (lambdas, val, constructors) come from overrides/<dir>/build.gradle.
build-logic is left alone unless --include-build-logic is given (then only its two scripts are converted).
Every converted .gradle.kts is deleted so exactly one variant of each script exists."""
import re, sys, pathlib
nia = pathlib.Path(sys.argv[1]).resolve()
here = pathlib.Path(__file__).resolve().parent
with_bl = "--include-build-logic" in sys.argv
RULES = [
    (r"isIncludeAndroidResources", "includeAndroidResources"),
    (r"missingDimensionStrategy\(FlavorDimension\.contentType\.name, NiaFlavor\.demo\.name\)", "missingDimensionStrategy(FlavorDimension.contentType.name(), NiaFlavor.demo.name())"),
    (r"isMinifyEnabled", "minifyEnabled"),
    (r'signingConfigs\.named\("debug"\)\.get\(\)', "signingConfigs.debug"),
    (r"\.map\(String::toBooleanStrict\)", ".map { Boolean.parseBoolean(it) }"),
    (r'excludes\.add\("([^"]*)"\)', r'excludes.add("\1")'),
]
count = 0
for kts in sorted(nia.rglob("*.gradle.kts")):
    rel = kts.relative_to(nia)
    if rel.parts[0] == "build-logic" and not with_bl:
        continue
    ov = here / "overrides" / rel.parent / "build.gradle"
    out = kts.with_name(kts.name[:-4])
    if kts.name == "build.gradle.kts" and ov.exists():
        out.write_text(ov.read_text())
    else:
        s = kts.read_text()
        for a, b in RULES:
            s = re.sub(a, b, s)
        s = s.replace("`java-library`", "id 'java-library'")
        if kts.name == "settings.gradle.kts" and rel.parent == pathlib.Path("."):
            s = re.sub(r"check\(JavaVersion.*\Z", """if (!JavaVersion.current().isCompatibleWith(JavaVersion.VERSION_17)) {
    throw new GradleException("Now in Android requires JDK 17+ but it is currently using JDK ${JavaVersion.current()}.")
}
""", s, flags=re.S)
        out.write_text(s)
    kts.unlink()
    count += 1
print(f"converted {count} scripts")
