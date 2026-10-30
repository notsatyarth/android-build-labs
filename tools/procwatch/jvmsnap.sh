#!/bin/bash
# Print one line per Gradle/Kotlin JVM: label, pid, start time, RSS MB, kind, java binary.
# Usage: jvmsnap.sh LABEL
label="$1"
ps -eo pid=,ppid=,lstart=,rss=,command= | while read -r pid ppid d1 d2 d3 d4 d5 rss cmd; do
  case "$cmd" in
    *KotlinCompileDaemon*) kind=kotlin-daemon ;;
    *GradleDaemon*) kind=gradle-daemon ;;
    *GradleWorkerMain*) kind=gradle-worker ;;
    *GradleWrapperMain*) kind=gradle-client ;;
    *TapiClient*) kind=tapi-client ;;
    *) continue ;;
  esac
  javabin=$(echo "$cmd" | awk '{print $1}')
  case "$cmd" in *daemons-lab*) home=lab ;; *) home=other ;; esac
  echo "$label pid=$pid ppid=$ppid home=$home start=\"$d1 $d2 $d3 $d4 $d5\" rss_mb=$((rss/1024)) kind=$kind java=$javabin"
done
echo "$label jps: $(jps -l 2>/dev/null | grep -v Jps | awk '{print $1":"$2}' | tr '\n' ' ')"
