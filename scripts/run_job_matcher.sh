#!/bin/sh

set -eu
umask 077

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(dirname -- "$script_dir")
log_dir="$project_root/logs"
log_file="$log_dir/job-matcher.log"
lock_dir="${TMPDIR:-/tmp}/job-agent-job-matcher.lock"
match_limit="${JOB_AGENT_MATCHING_MAX_REQUESTS_PER_RUN:-15}"

mkdir -p "$log_dir"
exec >>"$log_file" 2>&1

timestamp() {
    date -u '+%Y-%m-%dT%H:%M:%SZ'
}

case "$match_limit" in
    ''|*[!0-9]*)
        printf '%s Invalid JOB_AGENT_MATCHING_MAX_REQUESTS_PER_RUN: %s\n' \
            "$(timestamp)" "$match_limit"
        exit 2
        ;;
esac
if [ "$match_limit" -le 0 ] || [ "$match_limit" -gt 15 ]; then
    printf '%s JOB_AGENT_MATCHING_MAX_REQUESTS_PER_RUN must be between 1 and 15.\n' \
        "$(timestamp)"
    exit 2
fi

if ! mkdir "$lock_dir" 2>/dev/null; then
    running_pid=""
    if [ -r "$lock_dir/pid" ]; then
        running_pid=$(sed -n '1p' "$lock_dir/pid")
    fi

    if [ -n "$running_pid" ] && kill -0 "$running_pid" 2>/dev/null; then
        printf '%s Skipped matching because process %s is still running.\n' \
            "$(timestamp)" "$running_pid"
        exit 0
    fi

    rm -f "$lock_dir/pid"
    rmdir "$lock_dir" 2>/dev/null || true
    if ! mkdir "$lock_dir" 2>/dev/null; then
        printf '%s Skipped matching because the matcher lock is unavailable.\n' \
            "$(timestamp)"
        exit 0
    fi
fi

printf '%s\n' "$$" >"$lock_dir/pid"
cleanup() {
    rm -f "$lock_dir/pid"
    rmdir "$lock_dir" 2>/dev/null || true
}
trap cleanup EXIT

python_path="$project_root/.venv/bin/python"
if [ ! -x "$python_path" ]; then
    printf '%s Project Python is unavailable at %s.\n' \
        "$(timestamp)" "$python_path"
    exit 1
fi

printf '%s Starting job matching with a maximum of %s Gemini requests.\n' \
    "$(timestamp)" "$match_limit"
cd "$project_root"

set +e
"$python_path" "$project_root/app.py" \
    --match-prospects \
    --match-limit "$match_limit"
status=$?
set -e

printf '%s Job matching finished with status %s.\n' \
    "$(timestamp)" "$status"
exit "$status"
