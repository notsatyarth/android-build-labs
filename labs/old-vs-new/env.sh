HERE=$(cd "$(dirname "$0")" && pwd); : "${WORK:=$HOME/labs-work/nowinandroid}"
# Shared settings for the old-vs-new scripts. WORK holds the nowinandroid worktrees (wt-<commit>) and profiler-out/.
: "${ANDROID_HOME:=$HOME/Library/Android/sdk}"; export ANDROID_HOME
: "${JAVA_HOME:?set JAVA_HOME to a JDK 17 (original runs: Temurin 17.0.13)}"; export JAVA_HOME
export PATH=$JAVA_HOME/bin:$PATH
: "${WORK:=$HOME/labs-work/nowinandroid}"; export WORK
