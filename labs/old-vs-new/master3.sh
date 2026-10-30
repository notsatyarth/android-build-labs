HERE=$(cd "$(dirname "$0")" && pwd); : "${WORK:=$HOME/labs-work/nowinandroid}"
S=$HERE
bash $S/run_commit.sh ade8065442 1; bash $S/run_commit.sh 2c56ce13b 1
bash $S/run_commit.sh 2c56ce13b 2; bash $S/run_commit.sh ade8065442 2
for c in ade8065442 2c56ce13b; do bash $S/rss_release.sh $c; done
echo ALLDONE3 >> $WORK/profiler-out/run-status.txt
