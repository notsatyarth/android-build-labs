HERE=$(cd "$(dirname "$0")" && pwd); : "${WORK:=$HOME/labs-work/nowinandroid}"
. $HERE/env.sh
for c in 83d6dbb85 7d45eae4f 94571e675 ade8065442 2c56ce13b; do
  cd $WORK/wt-$c
  ./gradlew :app:assembleDemoDebug --no-build-cache --console=plain > ../profiler-out/prime-$c.log 2>&1
  echo "$c exit $?" >> ../profiler-out/prime-status.txt
  ./gradlew --stop >/dev/null 2>&1
done
