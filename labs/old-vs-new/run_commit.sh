HERE=$(cd "$(dirname "$0")" && pwd); : "${WORK:=$HOME/labs-work/nowinandroid}"
# usage: run_commit.sh COMMIT ROUND
. $HERE/env.sh
C=$1; R=$2
GP=${GRADLE_PROFILER:?set GRADLE_PROFILER to the gradle-profiler binary (built from source in the original runs)}
cd $WORK/wt-$C
./gradlew --stop >/dev/null 2>&1
OUT=$WORK/profiler-out/$C-r$R
$GP --benchmark --measure-config-time --gradle-user-home ~/.gradle --project-dir . --output-dir $OUT --scenario-file $HERE/scenarios.conf config clean nonabi > $OUT.log 2>&1
echo "$C r$R exit $?" >> $WORK/profiler-out/run-status.txt
git checkout -q -- . ; git status --short | head
./gradlew --stop >/dev/null 2>&1
pkill -f GradleDaemon; pkill -f KotlinCompileDaemon; true
