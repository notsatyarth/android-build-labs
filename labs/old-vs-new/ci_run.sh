#!/bin/bash
# CI driver for the old-versus-new lab: one pair of nowinandroid commits on one runner.
# Usage: ci_run.sh PAIR | --commits=PAIR (prints "OLD NEW")    PAIR = p1 (c5b604f72 -> 83d6dbb85), p2 (ade8065442 -> 2c56ce13b), p3 (7d45eae4f -> 94571e675)
# env: WORK (output root), JAVA_HOME (JDK 17), ITER (measured iterations, default 3), ROUNDS (1 = old,new; 2 adds new,old)
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
PAIR=${1#--commits=}
case "$PAIR" in p1) OLD=c5b604f72; NEW=83d6dbb85;; p2) OLD=ade8065442; NEW=2c56ce13b;; p3) OLD=7d45eae4f; NEW=94571e675;; *) echo "pair?"; exit 2;; esac
[ "${1#--commits=}" != "$1" ] && { echo "$OLD $NEW"; exit 0; }
: "${WORK:?}"; export WORK; mkdir -p "$WORK/profiler-out"
ITER=${ITER:-3}; ROUNDS=${ROUNDS:-1}
declare -A FULL=(
  [c5b604f72]=c5b604f72e096b355aae145dd96791972431eec6 [83d6dbb85]=83d6dbb856a27aae86baf93dfced70867e0485ee
  [7d45eae4f]=7d45eae4f8720a0c77f507712ba2437ff974b6ed [94571e675]=94571e67537552d9f345e02db6f56d7175b8cc2b
  [ade8065442]=ade8065442099e1f63f6c4c716bafc84b053ca09 [2c56ce13b]=2c56ce13bf13bdc33259efdc215166ec7f036225 )
# gradle-profiler release, pinned by SHA-256
GP_VER=0.26.0; GP_SHA=c573cdaffac8ecfa60cdd0624274511f46cbdde77fbba39ce35eae0fae7c9877
curl -sfL -o "$WORK/gp.zip" "https://github.com/gradle/gradle-profiler/releases/download/v$GP_VER/gradle-profiler-$GP_VER.zip"
echo "$GP_SHA  $WORK/gp.zip" | sha256sum -c - || exit 1
unzip -q -o "$WORK/gp.zip" -d "$WORK/gp"; export GRADLE_PROFILER=$WORK/gp/gradle-profiler-$GP_VER/bin/gradle-profiler
# iterations from ITER; warm-ups as in the original scenarios
sed "s/iterations = 5/iterations = $ITER/" "$HERE/scenarios.conf" > "$WORK/scenarios.ci.conf"; export SCENARIOS=$WORK/scenarios.ci.conf
for c in $OLD $NEW; do
  d=$WORK/wt-$c; rm -rf "$d"; git init -q "$d"
  git -C "$d" fetch -q --depth 1 https://github.com/android/nowinandroid "${FULL[$c]}" && git -C "$d" checkout -q FETCH_HEAD
  git -C "$d" config user.email ci@example.invalid; git -C "$d" config user.name ci
  echo "$c $(git -C "$d" rev-parse HEAD)"
done
# prime dependency caches for both commits (not measured)
for c in $OLD $NEW; do
  ( . "$HERE/env.sh"; cd "$WORK/wt-$c" && ./gradlew :app:assembleDemoDebug --no-build-cache --console=plain > "$WORK/profiler-out/prime-$c.log" 2>&1; echo "$c prime exit $?" >> "$WORK/profiler-out/prime-status.txt"; ./gradlew --stop >/dev/null 2>&1; pkill -f GradleDaemon; true )
done
bash "$HERE/run_commit.sh" $OLD 1; bash "$HERE/run_commit.sh" $NEW 1
if [ "$ROUNDS" -ge 2 ]; then bash "$HERE/run_commit.sh" $NEW 2; bash "$HERE/run_commit.sh" $OLD 2; fi
for c in $OLD $NEW; do bash "$HERE/rss_release.sh" $c; done
( cd "$WORK" && python3 -I "$HERE/agg.py" )
exit 0
