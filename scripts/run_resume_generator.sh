#!/bin/sh

set -eu
umask 077

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(dirname -- "$script_dir")
log_dir="$project_root/logs"
log_file="$log_dir/resume-generator.log"
lock_dir="${TMPDIR:-/tmp}/job-agent-resume-generator.lock"
resume_limit="${JOB_AGENT_RESUME_GENERATION_BATCH_LIMIT:-1}"
resume_format="${JOB_AGENT_RESUME_GENERATION_BATCH_FORMAT:-docx}"

mkdir -p "$log_dir"
exec >>"$log_file" 2>&1

timestamp() {
    date -u '+%Y-%m-%dT%H:%M:%SZ'
}

case "$resume_limit" in
    ''|*[!0-9]*)
        printf '%s Invalid JOB_AGENT_RESUME_GENERATION_BATCH_LIMIT: %s\n' \
            "$(timestamp)" "$resume_limit"
        exit 2
        ;;
esac
if [ "$resume_limit" -le 0 ] || [ "$resume_limit" -gt 100 ]; then
    printf '%s JOB_AGENT_RESUME_GENERATION_BATCH_LIMIT must be between 1 and 100.\n' \
        "$(timestamp)"
    exit 2
fi
case "$resume_format" in
    html|docx|both) ;;
    *)
        printf '%s JOB_AGENT_RESUME_GENERATION_BATCH_FORMAT must be html, docx, or both.\n' \
            "$(timestamp)"
        exit 2
        ;;
esac

if ! mkdir "$lock_dir" 2>/dev/null; then
    running_pid=""
    if [ -r "$lock_dir/pid" ]; then
        running_pid=$(sed -n '1p' "$lock_dir/pid")
    fi

    if [ -n "$running_pid" ] && kill -0 "$running_pid" 2>/dev/null; then
        printf '%s Skipped resume generation because process %s is still running.\n' \
            "$(timestamp)" "$running_pid"
        exit 0
    fi

    rm -f "$lock_dir/pid"
    rmdir "$lock_dir" 2>/dev/null || true
    if ! mkdir "$lock_dir" 2>/dev/null; then
        printf '%s Skipped resume generation because the lock is unavailable.\n' \
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

printf '%s Starting queued document generation (limit=%s, format=%s).\n' \
    "$(timestamp)" "$resume_limit" "$resume_format"
cd "$project_root"

set +e
"$python_path" "$project_root/app.py" \
    --generate-matched-resumes \
    --resume-limit "$resume_limit" \
    --resume-format "$resume_format"
status=$?
set -e

printf '%s Document generation finished with status %s.\n' \
    "$(timestamp)" "$status"
exit "$status"
