#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(dirname -- "$script_dir")
log_dir="$project_root/logs"
log_file="$log_dir/greenhouse-crawler.log"
lock_dir="${TMPDIR:-/tmp}/job-agent-greenhouse-crawler.lock"
crawl_limit="${JOB_AGENT_COMPANY_CRAWLER_LIMIT:-100}"

mkdir -p "$log_dir"
exec >>"$log_file" 2>&1

timestamp() {
    date -u '+%Y-%m-%dT%H:%M:%SZ'
}

if ! mkdir "$lock_dir" 2>/dev/null; then
    running_pid=""
    if [ -r "$lock_dir/pid" ]; then
        running_pid=$(sed -n '1p' "$lock_dir/pid")
    fi

    if [ -n "$running_pid" ] && kill -0 "$running_pid" 2>/dev/null; then
        printf '%s Skipped crawl because process %s is still running.\n' \
            "$(timestamp)" "$running_pid"
        exit 0
    fi

    rm -f "$lock_dir/pid"
    rmdir "$lock_dir" 2>/dev/null || true
    if ! mkdir "$lock_dir" 2>/dev/null; then
        printf '%s Skipped crawl because the crawler lock is unavailable.\n' \
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

printf '%s Starting Greenhouse company crawl with limit %s.\n' \
    "$(timestamp)" "$crawl_limit"
cd "$project_root"

set +e
"$project_root/.venv/bin/python" "$project_root/app.py" \
    --crawl-greenhouse-companies \
    --crawl-limit "$crawl_limit"
status=$?
set -e

printf '%s Greenhouse company crawl finished with status %s.\n' \
    "$(timestamp)" "$status"
exit "$status"
