HERE=$(cd "$(dirname "$0")" && pwd); : "${WORK:=$HOME/labs-work/nowinandroid}"
S=$HERE
for c in c5b604f72 83d6dbb85 7d45eae4f 94571e675 ade8065442 2c56ce13b; do bash $S/rss_release.sh $c; done
echo ALLDONE2 >> $WORK/profiler-out/rss-status.txt
