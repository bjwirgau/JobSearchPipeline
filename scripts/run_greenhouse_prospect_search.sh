#!/bin/sh

set -eu
umask 077

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(dirname -- "$script_dir")
log_dir="$project_root/logs"
log_file="$log_dir/greenhouse-prospect-search.log"
lock_dir="${TMPDIR:-/tmp}/job-agent-greenhouse-prospect-search.lock"
search_limit="${JOB_AGENT_GREENHOUSE_SEARCH_LIMIT:-100}"
board_limit="${JOB_AGENT_GREENHOUSE_BOARD_LIMIT:-25}"

mkdir -p "$log_dir"
exec >>"$log_file" 2>&1

timestamp() {
    date -u '+%Y-%m-%dT%H:%M:%SZ'
}

case "$search_limit" in
    ''|*[!0-9]*)
        printf '%s Invalid JOB_AGENT_GREENHOUSE_SEARCH_LIMIT: %s\n' \
            "$(timestamp)" "$search_limit"
        exit 2
        ;;
esac
if [ "$search_limit" -le 0 ]; then
    printf '%s JOB_AGENT_GREENHOUSE_SEARCH_LIMIT must be greater than zero.\n' \
        "$(timestamp)"
    exit 2
fi
case "$board_limit" in
    ''|*[!0-9]*)
        printf '%s Invalid JOB_AGENT_GREENHOUSE_BOARD_LIMIT: %s\n' \
            "$(timestamp)" "$board_limit"
        exit 2
        ;;
esac
if [ "$board_limit" -le 0 ] || [ "$board_limit" -gt 1000 ]; then
    printf '%s JOB_AGENT_GREENHOUSE_BOARD_LIMIT must be between 1 and 1000.\n' \
        "$(timestamp)"
    exit 2
fi

if ! mkdir "$lock_dir" 2>/dev/null; then
    running_pid=""
    if [ -r "$lock_dir/pid" ]; then
        running_pid=$(sed -n '1p' "$lock_dir/pid")
    fi

    if [ -n "$running_pid" ] && kill -0 "$running_pid" 2>/dev/null; then
        printf '%s Skipped search because process %s is still running.\n' \
            "$(timestamp)" "$running_pid"
        exit 0
    fi

    rm -f "$lock_dir/pid"
    rmdir "$lock_dir" 2>/dev/null || true
    if ! mkdir "$lock_dir" 2>/dev/null; then
        printf '%s Skipped search because the search lock is unavailable.\n' \
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

printf '%s Starting Greenhouse prospect search with result limit %s and board limit %s.\n' \
    "$(timestamp)" "$search_limit" "$board_limit"
cd "$project_root"

set +e
"$python_path" "$project_root/app.py" \
    --search \
    --source greenhouse \
    --greenhouse-board-limit "$board_limit" \
    --limit "$search_limit"
status=$?
set -e

printf '%s Greenhouse prospect search finished with status %s.\n' \
    "$(timestamp)" "$status"
exit "$status"
