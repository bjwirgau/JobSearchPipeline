#!/bin/sh

set -eu

commit_sha="${1:-}"
project_root="/opt/job-agent"
deploy_lock="/tmp/job-agent-deploy.lock"
crawler_lock="/tmp/job-agent-greenhouse-crawler.lock"
prospect_search_lock="/tmp/job-agent-greenhouse-prospect-search.lock"
job_matcher_lock="/tmp/job-agent-job-matcher.lock"
resume_generator_lock="/tmp/job-agent-resume-generator.lock"
crawler_lock_acquired=0
prospect_search_lock_acquired=0
job_matcher_lock_acquired=0
resume_generator_lock_acquired=0

if [ "${#commit_sha}" -ne 40 ]; then
    echo "A 40-character Git commit SHA is required."
    exit 2
fi

case "$commit_sha" in
    *[!0-9a-f]*)
        echo "The commit SHA contains invalid characters."
        exit 2
        ;;
esac

if ! mkdir "$deploy_lock" 2>/dev/null; then
    echo "Another deployment is already running."
    exit 1
fi

cleanup() {
    if [ "$resume_generator_lock_acquired" -eq 1 ]; then
        rm -f "$resume_generator_lock/pid"
        rmdir "$resume_generator_lock" 2>/dev/null || true
    fi
    if [ "$job_matcher_lock_acquired" -eq 1 ]; then
        rm -f "$job_matcher_lock/pid"
        rmdir "$job_matcher_lock" 2>/dev/null || true
    fi
    if [ "$prospect_search_lock_acquired" -eq 1 ]; then
        rm -f "$prospect_search_lock/pid"
        rmdir "$prospect_search_lock" 2>/dev/null || true
    fi
    if [ "$crawler_lock_acquired" -eq 1 ]; then
        rm -f "$crawler_lock/pid"
        rmdir "$crawler_lock" 2>/dev/null || true
    fi
    rmdir "$deploy_lock" 2>/dev/null || true
}
trap cleanup EXIT

# Wait up to ten minutes for an active crawler to finish.
attempt=0
while ! mkdir "$crawler_lock" 2>/dev/null; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 120 ]; then
        echo "Timed out waiting for the crawler."
        exit 1
    fi
    sleep 5
done

crawler_lock_acquired=1
printf '%s\n' "$$" >"$crawler_lock/pid"

# Also prevent a scheduled prospect search from using files during checkout.
attempt=0
while ! mkdir "$prospect_search_lock" 2>/dev/null; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 120 ]; then
        echo "Timed out waiting for the Greenhouse prospect search."
        exit 1
    fi
    sleep 5
done

prospect_search_lock_acquired=1
printf '%s\n' "$$" >"$prospect_search_lock/pid"

# Prevent the minute-based matcher from importing files during checkout.
attempt=0
while ! mkdir "$job_matcher_lock" 2>/dev/null; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 120 ]; then
        echo "Timed out waiting for the job matcher."
        exit 1
    fi
    sleep 5
done

job_matcher_lock_acquired=1
printf '%s\n' "$$" >"$job_matcher_lock/pid"

# Prevent the resume generator from importing files during checkout.
attempt=0
while ! mkdir "$resume_generator_lock" 2>/dev/null; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 120 ]; then
        echo "Timed out waiting for the resume generator."
        exit 1
    fi
    sleep 5
done

resume_generator_lock_acquired=1
printf '%s\n' "$$" >"$resume_generator_lock/pid"

cd "$project_root"

git fetch --prune origin main
git cat-file -e "${commit_sha}^{commit}"
git merge-base --is-ancestor "$commit_sha" origin/main
git checkout --detach "$commit_sha"

.venv/bin/python -m pip install -e '.[search]'

docker compose up --detach --wait mysql

# Initializes or migrates the database and verifies configuration.
.venv/bin/python app.py

echo "Successfully deployed $commit_sha"
