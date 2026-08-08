#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(dirname -- "$script_dir")
crawler_schedule="${JOB_AGENT_CRAWLER_CRON_SCHEDULE:-*/5 * * * *}"
prospect_schedule="${JOB_AGENT_PROSPECT_SEARCH_CRON_SCHEDULE:-4 * * * *}"
matcher_schedule="${JOB_AGENT_MATCHER_CRON_SCHEDULE:-* * * * *}"
search_limit="${JOB_AGENT_GREENHOUSE_SEARCH_LIMIT:-100}"
board_limit="${JOB_AGENT_GREENHOUSE_BOARD_LIMIT:-25}"
match_limit="${JOB_AGENT_MATCHING_MAX_REQUESTS_PER_RUN:-15}"
begin_marker="# BEGIN job-agent managed cron jobs"
end_marker="# END job-agent managed cron jobs"
current_crontab=$(mktemp "${TMPDIR:-/tmp}/job-agent-crontab-current.XXXXXX")
next_crontab=$(mktemp "${TMPDIR:-/tmp}/job-agent-crontab-next.XXXXXX")

cleanup() {
    rm -f "$current_crontab" "$next_crontab"
}
trap cleanup EXIT

crontab -l >"$current_crontab" 2>/dev/null || :

awk \
    -v begin="$begin_marker" \
    -v end="$end_marker" \
    '
        $0 == begin { managed = 1; next }
        $0 == end { managed = 0; next }
        managed { next }
        index($0, "/scripts/run_greenhouse_crawler.sh") { next }
        index($0, "/scripts/run_greenhouse_prospect_search.sh") { next }
        index($0, "/scripts/run_job_matcher.sh") { next }
        { print }
    ' \
    "$current_crontab" >"$next_crontab"

{
    printf '%s\n' "$begin_marker"
    printf 'JOB_AGENT_GREENHOUSE_SEARCH_LIMIT=%s\n' "$search_limit"
    printf 'JOB_AGENT_GREENHOUSE_BOARD_LIMIT=%s\n' "$board_limit"
    printf 'JOB_AGENT_MATCHING_MAX_REQUESTS_PER_RUN=%s\n' "$match_limit"
    printf '%s %s/scripts/run_greenhouse_crawler.sh\n' \
        "$crawler_schedule" "$project_root"
    printf '%s %s/scripts/run_greenhouse_prospect_search.sh\n' \
        "$prospect_schedule" "$project_root"
    printf '%s %s/scripts/run_job_matcher.sh\n' \
        "$matcher_schedule" "$project_root"
    printf '%s\n' "$end_marker"
} >>"$next_crontab"

crontab "$next_crontab"
printf 'Installed job-agent cron jobs for %s.\n' "$project_root"
crontab -l
