#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/infra/tool-versions.conf"

PROFILE="${1:-dev}"
if [[ -f "$PROFILE" ]]; then
  ENV_FILE="$PROFILE"
  PROFILE="custom"
else
  case "$PROFILE" in
    dev) ENV_FILE="$ROOT_DIR/infra/compose/dev/.env.example" ;;
    test) ENV_FILE="$ROOT_DIR/infra/compose/test/.env.example" ;;
    *) echo "stack-init: profile must be dev, test, or an env file path (got $PROFILE)" >&2; exit 2 ;;
  esac
fi
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

SETUP_PYTHON="${IBEX_SETUP_PYTHON:-python3}"

POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-ibex}"
POSTGRES_DB="${POSTGRES_DB:-ibex}"
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
CLICKHOUSE_HTTP_PORT="${CLICKHOUSE_HTTP_PORT:-8123}"
MINIO_API_PORT="${MINIO_API_PORT:-9100}"
S3_ACCESS_KEY="${S3_ACCESS_KEY:-minioadmin}"
S3_SECRET_KEY="${S3_SECRET_KEY:-minioadmin}"

failures=0
printf 'stack-init: profile=%s postgres=%s redis=%s clickhouse-http=%s minio=%s\n' \
  "$PROFILE" "$POSTGRES_PORT" "$REDIS_PORT" "$CLICKHOUSE_HTTP_PORT" "$MINIO_API_PORT"
probe() {
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then printf 'PASS  %-24s\n' "$name"
  else printf 'FAIL  %-24s\n' "$name"; failures=$((failures + 1)); fi
}

if command -v "${PG_ISREADY:-pg_isready}" >/dev/null 2>&1; then
  probe postgres "${PG_ISREADY:-pg_isready}" -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB"
else
  probe postgres-tcp bash -c "timeout 5 bash -c '</dev/tcp/$POSTGRES_HOST/$POSTGRES_PORT'"
  echo 'INFO  pg_isready/psql unavailable; PostgreSQL readiness used a TCP fallback.'
fi
probe redis bash -c "timeout 5 bash -c '</dev/tcp/$REDIS_HOST/$REDIS_PORT'"
probe clickhouse bash -c "curl -fsS http://127.0.0.1:${CLICKHOUSE_HTTP_PORT}/ping | grep -Fxq 'Ok.'"
probe minio curl -fsS "http://127.0.0.1:${MINIO_API_PORT}/minio/health/ready"

if command -v python3 >/dev/null 2>&1; then
  python3 - "$MINIO_API_PORT" "$S3_ACCESS_KEY" "$S3_SECRET_KEY" <<'PY'
import sys, urllib.request
port, access, secret = sys.argv[1:]
try:
    urllib.request.urlopen(f"http://127.0.0.1:{port}/minio/health/ready", timeout=5).read()
except Exception as exc:
    raise SystemExit(str(exc))
PY
fi

buckets="${S3_BUCKETS:-ibex-sessions ibex-exports}"
if command -v aws >/dev/null 2>&1; then
  for bucket in $buckets; do
    AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY" AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" \
      aws --endpoint-url "http://127.0.0.1:${MINIO_API_PORT}" s3 mb "s3://$bucket" >/dev/null 2>&1 || \
      AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY" AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" \
      aws --endpoint-url "http://127.0.0.1:${MINIO_API_PORT}" s3api head-bucket --bucket "$bucket" >/dev/null
    printf 'PASS  bucket %-18s\n' "$bucket"
  done
elif "$SETUP_PYTHON" -c 'import boto3' >/dev/null 2>&1 && "$SETUP_PYTHON" - "$MINIO_API_PORT" "$S3_ACCESS_KEY" "$S3_SECRET_KEY" "$buckets" <<'PY'
import sys
try:
    import boto3
except ImportError:
    raise SystemExit(1)
port, access, secret, bucket_list = sys.argv[1:]
s3 = boto3.client(
    "s3",
    endpoint_url=f"http://127.0.0.1:{port}",
    aws_access_key_id=access,
    aws_secret_access_key=secret,
    region_name="us-east-1",
)
for bucket in bucket_list.split():
    try:
        s3.create_bucket(Bucket=bucket)
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass
    print(f"PASS  bucket {bucket:<18}")
PY
then
  :
else
  echo 'FAIL  bucket initialization (install awscli or boto3)' >&2
  failures=$((failures + 1))
fi

if (( failures > 0 )); then
  echo "stack-init: $failures readiness probe(s) failed" >&2
  exit 1
fi
echo 'stack-init: all required readiness probes passed'
