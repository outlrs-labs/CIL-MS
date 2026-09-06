#!/usr/bin/env bash
set -euo pipefail

STACK_NAME="${1:-cil-platform}"
AWS_REGION="${2:-ap-south-1}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env.production"

for tool in aws python3 tar openssl; do
  command -v "$tool" >/dev/null || { echo "Missing required command: $tool" >&2; exit 1; }
done
test -f "$ENV_FILE" || { echo "Create .env.production from .env.production.example first." >&2; exit 1; }

origin_secret="$(awk -F= '$1 == "ORIGIN_VERIFY_HEADER" {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE")"
if [ "${#origin_secret}" -lt 32 ]; then
  origin_secret="$(openssl rand -hex 32)"
fi

aws cloudformation deploy \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME" \
  --template-file "$PROJECT_ROOT/deploy/cloudformation.yml" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides "OriginVerifyHeader=$origin_secret"

output() {
  aws cloudformation describe-stacks --region "$AWS_REGION" --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" --output text
}

instance_id="$(output ApplicationInstanceId)"
data_bucket="$(output DataBucketName)"
frontend_bucket="$(output FrontendBucketName)"
distribution_id="$(output DistributionId)"
distribution_domain="$(output DistributionDomain)"
environment_secret="$(output ProductionEnvironmentSecret)"
release_key="deploy/releases/$(date -u +%Y%m%dT%H%M%SZ)-${RANDOM}.tar.gz"
catalog_key="${release_key%.tar.gz}-catalog.sqlite3"

rendered_env="$(mktemp)"
release_archive="$(mktemp)"
catalog_snapshot=""
cleanup() { rm -f "$rendered_env" "$release_archive" ${catalog_snapshot:+"$catalog_snapshot"}; }
trap cleanup EXIT

python3 - "$ENV_FILE" "$rendered_env" "$distribution_domain" "$origin_secret" <<'PY'
from pathlib import Path
import sys

source, target, domain, origin = sys.argv[1:]
values = {"CORS_ORIGINS": f"https://{domain}", "ORIGIN_VERIFY_HEADER": origin}
lines = Path(source).read_text(encoding="utf-8").splitlines()
seen = set()
result = []
for line in lines:
    key = line.split("=", 1)[0] if "=" in line and not line.lstrip().startswith("#") else ""
    if key in values:
        result.append(f"{key}={values[key]}")
        seen.add(key)
    else:
        result.append(line)
for key, value in values.items():
    if key not in seen:
        result.append(f"{key}={value}")
Path(target).write_text("\n".join(result) + "\n", encoding="utf-8")
PY

for required in SUPABASE_URL SUPABASE_PUBLISHABLE_KEY SUPABASE_SECRET_KEY DF_BRIDGE_SECRET POSTGRES_PASSWORD; do
  value="$(awk -F= -v key="$required" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$rendered_env")"
  test -n "$value" || { echo "$required is missing from .env.production" >&2; exit 1; }
done

aws secretsmanager put-secret-value --region "$AWS_REGION" --secret-id "$environment_secret" \
  --secret-string "file://$rendered_env" >/dev/null

# Seed/update the durable object repository before the application starts.
# S3 versioning preserves replaced objects, while hidden workstation files stay local.
aws s3 sync --region "$AWS_REGION" "$PROJECT_ROOT/Data/cil/" "s3://${data_bucket}/cil/" \
  --no-follow-symlinks --exclude '.*' --exclude '*/.*' --only-show-errors

tar -C "$PROJECT_ROOT" -czf "$release_archive" \
  --exclude=.git --exclude=.env --exclude=.env.production --exclude=.venv \
  --exclude='*/node_modules' --exclude='*/dist' --exclude=Data --exclude='*/__pycache__' .
aws s3 cp --region "$AWS_REGION" "$release_archive" "s3://${frontend_bucket}/${release_key}" --only-show-errors
catalog_path="$PROJECT_ROOT/Data/.processing/catalog.sqlite3"
if [ -f "$catalog_path" ]; then
  catalog_snapshot="$(mktemp)"
  python3 - "$catalog_path" "$catalog_snapshot" <<'PY'
import sqlite3, sys
source = sqlite3.connect(sys.argv[1])
target = sqlite3.connect(sys.argv[2])
source.backup(target)
target.close(); source.close()
PY
  aws s3 cp --region "$AWS_REGION" "$catalog_snapshot" "s3://${frontend_bucket}/${catalog_key}" --only-show-errors
  rm -f "$catalog_snapshot"
fi

echo "Waiting for the EC2 Systems Manager agent..."
for _ in $(seq 1 60); do
  if aws ssm describe-instance-information --region "$AWS_REGION" \
    --filters "Key=InstanceIds,Values=$instance_id" \
    --query 'InstanceInformationList[0].PingStatus' --output text 2>/dev/null | grep -q Online; then
    break
  fi
  sleep 10
done

commands=$(python3 - "$frontend_bucket" "$release_key" "$catalog_key" "$environment_secret" "$AWS_REGION" "$distribution_id" <<'PY'
import json, sys
bucket, key, catalog_key, secret, region, distribution = sys.argv[1:]
commands = [
    "set -eux",
    "mkdir -p /opt/cil-platform",
    f"aws s3 cp s3://{bucket}/{key} /tmp/cil-release.tar.gz --region {region}",
    "find /opt/cil-platform -mindepth 1 -maxdepth 1 -exec rm -rf {} +",
    "tar -xzf /tmp/cil-release.tar.gz -C /opt/cil-platform",
    f"aws secretsmanager get-secret-value --secret-id {secret} --region {region} --query SecretString --output text > /opt/cil-platform/.env.production",
    "chmod 600 /opt/cil-platform/.env.production",
    "cd /opt/cil-platform && docker compose --env-file .env.production -f docker-compose.production.yml up -d --build --remove-orphans",
    f"if aws s3 cp s3://{bucket}/{catalog_key} /tmp/cil-catalog.sqlite3 --region {region} --only-show-errors; then cd /opt/cil-platform && docker compose --env-file .env.production -f docker-compose.production.yml run --rm -v /tmp/cil-catalog.sqlite3:/migration/catalog.sqlite3:ro api python scripts/migrate_sqlite_to_postgres.py /migration/catalog.sqlite3; fi",
    "rm -rf /tmp/cil-frontend && mkdir -p /tmp/cil-frontend",
    "cd /opt/cil-platform && docker build --target frontend-export --output type=local,dest=/tmp/cil-frontend .",
    f"aws s3 sync /tmp/cil-frontend/ s3://{bucket}/ --delete --exclude 'deploy/*' --region {region}",
    f"aws cloudfront create-invalidation --distribution-id {distribution} --paths '/*' >/dev/null",
    "docker image prune -f",
]
print(json.dumps(commands))
PY
)

command_id=$(aws ssm send-command --region "$AWS_REGION" --instance-ids "$instance_id" \
  --document-name AWS-RunShellScript --timeout-seconds 3600 \
  --parameters "commands=$commands" --query 'Command.CommandId' --output text)

status=Pending
for _ in $(seq 1 240); do
  status=$(aws ssm get-command-invocation --region "$AWS_REGION" --command-id "$command_id" --instance-id "$instance_id" --query Status --output text 2>/dev/null || echo Pending)
  case "$status" in Success|Failed|Cancelled|TimedOut) break ;; esac
  sleep 15
done
if [ "$status" != Success ]; then
  aws ssm get-command-invocation --region "$AWS_REGION" --command-id "$command_id" --instance-id "$instance_id" \
    --query '{Status:Status,Output:StandardOutputContent,Error:StandardErrorContent}' --output json
  exit 1
fi

rm -f "$release_archive"
aws s3 rm --region "$AWS_REGION" "s3://${frontend_bucket}/${release_key}" --only-show-errors
aws s3 rm --region "$AWS_REGION" "s3://${frontend_bucket}/${catalog_key}" --only-show-errors 2>/dev/null || true
echo "Deployment complete: https://${distribution_domain}"
echo "Data root: s3://${data_bucket}/cil/"
