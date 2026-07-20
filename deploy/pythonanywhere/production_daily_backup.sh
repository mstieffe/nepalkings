#!/usr/bin/env bash
# PythonAnywhere scheduled task 22971. The deployed copy is:
# /home/nepalkingz/ops/production_daily_backup.sh
set -euo pipefail

umask 077

backup_dir="/home/nepalkingz/backups/postgres-production"
timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
output="${backup_dir}/production-daily-${timestamp}.dump"

mkdir -p "${backup_dir}"
/home/nepalkingz/.virtualenvs/nepalkings-production/bin/python \
  /home/nepalkingz/ops/70e9259200f08e309fdad60b2a7a1aff48d30254/scripts/create_postgres_backup.py \
  --env-file /home/nepalkingz/.config/nepalkings/production.env \
  --output "${output}"

# Retain two weeks of provider-side daily dumps. Pre-deployment and manually
# named recovery archives are deliberately outside this deletion pattern.
find "${backup_dir}" \
  -maxdepth 1 \
  -type f \
  -name 'production-daily-*.dump' \
  -mtime +13 \
  -delete
