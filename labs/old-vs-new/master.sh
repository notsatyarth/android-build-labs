HERE=$(cd "$(dirname "$0")" && pwd); : "${WORK:=$HOME/labs-work/nowinandroid}"
S=$HERE
bash $S/run_commit.sh c5b604f72 1; bash $S/run_commit.sh 83d6dbb85 1
bash $S/run_commit.sh 7d45eae4f 1; bash $S/run_commit.sh 94571e675 1
bash $S/run_commit.sh 83d6dbb85 2; bash $S/run_commit.sh c5b604f72 2
bash $S/run_commit.sh 94571e675 2; bash $S/run_commit.sh 7d45eae4f 2
echo ALLDONE >> $WORK/profiler-out/run-status.txt
