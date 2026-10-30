#!/bin/bash
# Shallow-clone android/nowinandroid at one commit. Usage: clone_nia.sh DIR [SHA]
set -eu
DIR=$1; SHA=${2:-2982e63cb691ad49cd009aab43dc206fee6699c2}
git init -q "$DIR"
git -C "$DIR" fetch -q --depth 1 https://github.com/android/nowinandroid "$SHA"
git -C "$DIR" checkout -q FETCH_HEAD
echo "nowinandroid $(git -C "$DIR" rev-parse HEAD)"
