#!/bin/bash
# Append the runner's hardware and toolchain to the job summary (and print it).
# Usage: runner_info.sh  (writes to $GITHUB_STEP_SUMMARY when set)
{
  echo "### Runner"
  echo
  echo "| item | value |"
  echo "|---|---|"
  echo "| image | ${ImageOS:-?} ${ImageVersion:-?} |"
  echo "| arch | $(uname -m) |"
  echo "| nproc | $(nproc 2>/dev/null || sysctl -n hw.ncpu) |"
  echo "| MemTotal | $(awk '/MemTotal/{printf "%.1f GiB", $2/1048576}' /proc/meminfo 2>/dev/null) |"
  echo "| SwapTotal | $(awk '/SwapTotal/{printf "%.1f GiB", $2/1048576}' /proc/meminfo 2>/dev/null) |"
  echo "| CPU | $(awk -F': ' '/model name/{print $2; exit}' /proc/cpuinfo 2>/dev/null) |"
  echo "| java | $(java -version 2>&1 | head -1) |"
  echo "| ANDROID_HOME build-tools | $(ls "${ANDROID_HOME:-/nonexistent}/build-tools" 2>/dev/null | tr '\n' ' ') |"
  echo "| ANDROID_HOME platforms | $(ls "${ANDROID_HOME:-/nonexistent}/platforms" 2>/dev/null | tr '\n' ' ') |"
  echo
} | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
