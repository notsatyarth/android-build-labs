HERE=$(cd "$(dirname "$0")" && pwd); : "${WORK:=$HOME/labs-work/nowinandroid}"
# usage: rss_release.sh COMMIT
. $HERE/env.sh
C=$1
P=$WORK
cd $P/wt-$C
./gradlew --stop >/dev/null 2>&1; pkill -f KotlinCompileDaemon; sleep 3
# warm daemon then a measured clean build under procwatch
./gradlew help --no-configuration-cache -q >/dev/null 2>&1
python3 -I $(dirname "$0")/../../tools/procwatch/procwatch.py $P/profiler-out/rss-$C.csv --interval 2 -- ./gradlew :app:assembleDemoDebug --no-build-cache --rerun-tasks --no-configuration-cache --console=plain > $P/profiler-out/rss-$C.log 2>&1
echo "$C rss exit $?" >> $P/profiler-out/rss-status.txt
./gradlew --stop >/dev/null 2>&1; pkill -f KotlinCompileDaemon; sleep 3
( time ./gradlew :app:assembleDemoRelease --no-build-cache --no-configuration-cache --console=plain ) > $P/profiler-out/release-$C.log 2>&1
echo "$C release exit $?" >> $P/profiler-out/rss-status.txt
./gradlew --stop >/dev/null 2>&1; pkill -f GradleDaemon; pkill -f KotlinCompileDaemon; true
