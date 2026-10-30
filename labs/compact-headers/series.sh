#!/bin/bash
# Balanced ABBA order, 4 runs per arm. base = as shipped jvmargs, coh = plus -XX:+UseCompactObjectHeaders.
cd "$(dirname "$0")"
for spec in base:B1 coh:C1 coh:C2 base:B2 base:B3 coh:C3 coh:C4 base:B4; do
  arm=${spec%%:*}; label=${spec##*:}
  echo "$(date +%T) start $label ($arm)" >> raw/progress.txt
  ./run.sh "$label" "$arm"
  echo "$(date +%T) done $label $(tail -1 raw/$label.env)" >> raw/progress.txt
done
echo "$(date +%T) series finished" >> raw/progress.txt
