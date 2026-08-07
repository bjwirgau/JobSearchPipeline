#!/usr/bin/env bash

set -Eeuo pipefail

usage() {
    cat <<'EOF'
Copy the MySQL database from an SSM-managed EC2 instance into local Docker MySQL.

Usage:
  scripts/copy_aws_database.sh \
    --instance-id INSTANCE_ID \
    [--region AWS_REGION] \
    [--profile AWS_PROFILE] \
    [--remote-database DATABASE] \
    [--remote-user USER] \
    [--remote-port PORT] \
    [--local-forward-port PORT] \
    --replace-local-database

The remote MySQL password is read from JOB_AGENT_AWS_MYSQL_PASSWORD. When that
variable is unset, the command prompts for it without echoing the value.

This command replaces the local database. Before importing, it writes a local
backup under data/database_backups/.
EOF
}

fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 2
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

valid_port() {
    [[ "$1" =~ ^[0-9]+$ ]] && ((10#$1 >= 1 && 10#$1 <= 65535))
}

port_is_open() {
    (exec 3<>"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1
}

quote_mysql_option() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '"%s"' "$value"
}

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
instance_id=""
aws_region="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
aws_profile="${AWS_PROFILE:-}"
remote_database="${JOB_AGENT_AWS_MYSQL_DATABASE:-job_agent}"
remote_user="${JOB_AGENT_AWS_MYSQL_USER:-job_agent}"
remote_port="${JOB_AGENT_AWS_MYSQL_PORT:-3306}"
local_forward_port="13306"
replace_local_database=0

while (($#)); do
    case "$1" in
        --instance-id)
            (($# >= 2)) || fail "--instance-id requires a value"
            instance_id="$2"
            shift 2
            ;;
        --region)
            (($# >= 2)) || fail "--region requires a value"
            aws_region="$2"
            shift 2
            ;;
        --profile)
            (($# >= 2)) || fail "--profile requires a value"
            aws_profile="$2"
            shift 2
            ;;
        --remote-database)
            (($# >= 2)) || fail "--remote-database requires a value"
            remote_database="$2"
            shift 2
            ;;
        --remote-user)
            (($# >= 2)) || fail "--remote-user requires a value"
            remote_user="$2"
            shift 2
            ;;
        --remote-port)
            (($# >= 2)) || fail "--remote-port requires a value"
            remote_port="$2"
            shift 2
            ;;
        --local-forward-port)
            (($# >= 2)) || fail "--local-forward-port requires a value"
            local_forward_port="$2"
            shift 2
            ;;
        --replace-local-database)
            replace_local_database=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "unknown argument: $1"
            ;;
    esac
done

[[ -n "$instance_id" ]] || fail "--instance-id is required"
[[ "$instance_id" =~ ^i-[[:alnum:]]+$ ]] || fail "invalid EC2 instance ID"
[[ -n "$aws_region" ]] || fail "--region is required"
[[ -n "$remote_database" ]] || fail "remote database must not be empty"
[[ -n "$remote_user" ]] || fail "remote user must not be empty"
valid_port "$remote_port" || fail "--remote-port must be between 1 and 65535"
valid_port "$local_forward_port" || fail \
    "--local-forward-port must be between 1 and 65535"
((replace_local_database == 1)) || fail \
    "refusing to replace local data without --replace-local-database"

require_command aws
require_command docker
require_command mysqldump
docker compose version >/dev/null 2>&1 || fail "Docker Compose is unavailable"

cd "$project_root"
docker compose -f docker-compose.yml up --detach --wait mysql

local_database=$(
    docker compose -f docker-compose.yml exec -T mysql \
        sh -c 'printf "%s" "$MYSQL_DATABASE"'
)
[[ -n "$local_database" ]] || fail "local MySQL database name is unavailable"
[[ "$remote_database" == "$local_database" ]] || fail \
    "remote database '$remote_database' must match local database '$local_database'"

backup_dir="$project_root/data/database_backups"
backup_timestamp=$(date -u '+%Y%m%dT%H%M%SZ')
backup_path="$backup_dir/local-before-aws-copy-$backup_timestamp.sql"
mkdir -p "$backup_dir"

printf 'Backing up local database %s to %s\n' "$local_database" "$backup_path"
docker compose -f docker-compose.yml exec -T mysql sh -c '
    exec mysqldump \
        --user=root \
        --password="$MYSQL_ROOT_PASSWORD" \
        --single-transaction \
        --quick \
        --no-tablespaces \
        --add-drop-database \
        --databases "$MYSQL_DATABASE"
' >"$backup_path"
[[ -s "$backup_path" ]] || fail "local database backup is empty"

remote_password="${JOB_AGENT_AWS_MYSQL_PASSWORD:-}"
if [[ -z "$remote_password" ]]; then
    [[ -t 0 ]] || fail \
        "JOB_AGENT_AWS_MYSQL_PASSWORD must be set when no terminal is available"
    read -r -s -p "Remote MySQL password for $remote_user: " remote_password
    printf '\n'
fi
[[ -n "$remote_password" ]] || fail "remote MySQL password must not be empty"
[[ "$remote_password" != *$'\n'* ]] || fail "remote MySQL password contains a newline"

remote_options=$(mktemp "${TMPDIR:-/tmp}/job-agent-remote-mysql.XXXXXX")
session_log=$(mktemp "${TMPDIR:-/tmp}/job-agent-ssm-session.XXXXXX")
tunnel_pid=""

cleanup() {
    if [[ -n "$tunnel_pid" ]] && kill -0 "$tunnel_pid" 2>/dev/null; then
        kill "$tunnel_pid" 2>/dev/null || true
        wait "$tunnel_pid" 2>/dev/null || true
    fi
    rm -f "$remote_options" "$session_log"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

chmod 600 "$remote_options"
{
    printf '[client]\n'
    printf 'user=%s\n' "$(quote_mysql_option "$remote_user")"
    printf 'password=%s\n' "$(quote_mysql_option "$remote_password")"
    printf 'host=127.0.0.1\n'
    printf 'port=%s\n' "$local_forward_port"
    printf 'protocol=tcp\n'
} >"$remote_options"
unset remote_password

port_is_open "$local_forward_port" && fail \
    "local forwarding port $local_forward_port is already in use"

session_parameters=$(printf \
    '{"portNumber":["%s"],"localPortNumber":["%s"]}' \
    "$remote_port" \
    "$local_forward_port")
aws_session=(
    aws ssm start-session
    --target "$instance_id"
    --document-name AWS-StartPortForwardingSession
    --parameters "$session_parameters"
    --region "$aws_region"
)
if [[ -n "$aws_profile" ]]; then
    aws_session+=(--profile "$aws_profile")
fi

printf 'Opening SSM tunnel to %s:%s through %s\n' \
    "$instance_id" "$remote_port" "$aws_region"
"${aws_session[@]}" >"$session_log" 2>&1 &
tunnel_pid=$!

tunnel_ready=0
for _attempt in {1..30}; do
    if port_is_open "$local_forward_port"; then
        tunnel_ready=1
        break
    fi
    if ! kill -0 "$tunnel_pid" 2>/dev/null; then
        printf 'SSM tunnel exited before becoming ready:\n' >&2
        sed -n '1,120p' "$session_log" >&2
        exit 1
    fi
    sleep 1
done
if ((tunnel_ready == 0)); then
    printf 'SSM tunnel did not become ready within 30 seconds:\n' >&2
    sed -n '1,120p' "$session_log" >&2
    exit 1
fi

printf 'Replacing local database %s from the AWS instance\n' "$local_database"
if ! mysqldump \
    --defaults-extra-file="$remote_options" \
    --single-transaction \
    --quick \
    --skip-lock-tables \
    --no-tablespaces \
    --add-drop-database \
    --databases "$remote_database" |
    docker compose -f docker-compose.yml exec -T mysql sh -c '
        exec mysql --user=root --password="$MYSQL_ROOT_PASSWORD"
    '
then
    printf 'Database copy failed. The pre-copy backup is available at %s\n' \
        "$backup_path" >&2
    exit 1
fi

printf 'Database copy completed successfully.\n'
printf 'Pre-copy local backup: %s\n' "$backup_path"
