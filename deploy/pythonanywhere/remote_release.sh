#!/usr/bin/env bash
# Remote half of the paid PythonAnywhere EU deployment.
#
# This script is uploaded to an immutable, SHA-specific ops directory and is
# launched through the target environment's stopped always-on task. It never
# prints the private environment file or a database URL.

set -Eeuo pipefail

umask 077

MODE="${1:-}"
DEPLOY_ENVIRONMENT="${2:-}"
RELEASE_SHA="${3:-}"
ARCHIVE_SHA256="${4:-}"

HOME_DIRECTORY="/home/nepalkingz"

if [[ ! "${RELEASE_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
    echo "Release SHA must be 40 lowercase hexadecimal characters" >&2
    exit 2
fi
if [[ ! "${ARCHIVE_SHA256}" =~ ^[0-9a-f]{64}$ ]]; then
    echo "Archive SHA-256 must be 64 lowercase hexadecimal characters" >&2
    exit 2
fi

case "${DEPLOY_ENVIRONMENT}" in
    staging)
        ENV_FILE="${HOME_DIRECTORY}/.config/nepalkings/staging.env"
        VIRTUALENV="${HOME_DIRECTORY}/.virtualenvs/nepalkings-staging"
        WSGI_FILE="/var/www/nepalkingz_eu_pythonanywhere_com_wsgi.py"
        BACKUP_DIRECTORY="${HOME_DIRECTORY}/backups/postgres-staging"
        ;;
    production)
        ENV_FILE="${HOME_DIRECTORY}/.config/nepalkings/production.env"
        VIRTUALENV="${HOME_DIRECTORY}/.virtualenvs/nepalkings-production"
        WSGI_FILE="/var/www/api-nepalkingz_eu_pythonanywhere_com_wsgi.py"
        BACKUP_DIRECTORY="${HOME_DIRECTORY}/backups/postgres-production"
        ;;
    *)
        echo "Environment must be staging or production" >&2
        exit 2
        ;;
esac

RELEASE_DIRECTORY="${HOME_DIRECTORY}/releases/${RELEASE_SHA}"
ARCHIVE="${HOME_DIRECTORY}/uploads/nepalkings-server-${RELEASE_SHA}.tar.gz"
OPS_DIRECTORY="${HOME_DIRECTORY}/ops/${RELEASE_SHA}"
SCRIPTS_DIRECTORY="${OPS_DIRECTORY}/scripts"
LOG_FILE="${OPS_DIRECTORY}/${DEPLOY_ENVIRONMENT}-deploy.log"
READY_MARKER="${OPS_DIRECTORY}/${DEPLOY_ENVIRONMENT}-deploy.ready"
FAILED_MARKER="${OPS_DIRECTORY}/${DEPLOY_ENVIRONMENT}-deploy.failed"
FINALIZED_MARKER="${OPS_DIRECTORY}/production-finalize.ready"
FINALIZE_FAILED_MARKER="${OPS_DIRECTORY}/production-finalize.failed"
TEMP_RELEASE_DIRECTORY=""

mkdir -p "${OPS_DIRECTORY}"
chmod 700 "${OPS_DIRECTORY}"

if [[ "${MODE}" == "finalize-production" ]]; then
    if [[ "${DEPLOY_ENVIRONMENT}" != "production" ]]; then
        echo "finalize-production is production-only" >&2
        exit 2
    fi
    exec >>"${LOG_FILE}" 2>&1
    finalize_error() {
        local exit_code=$?
        local line_number=${1:-unknown}
        echo "PRODUCTION_FINALIZE_FAILED release=${RELEASE_SHA} line=${line_number} exit=${exit_code}"
        : >"${FINALIZE_FAILED_MARKER}"
        while true; do
            sleep 3600
        done
    }
    trap 'finalize_error ${LINENO}' ERR
    rm -f "${FINALIZED_MARKER}" "${FINALIZE_FAILED_MARKER}"
    test "$(grep -c '^RELEASE_SHA=' "${ENV_FILE}")" -eq 1
    grep -qx "RELEASE_SHA=${RELEASE_SHA}" "${ENV_FILE}"
    test "$(grep -c '^MAINTENANCE_MODE=' "${ENV_FILE}")" -eq 1
    sed -i -E 's/^MAINTENANCE_MODE=.*/MAINTENANCE_MODE=False/' "${ENV_FILE}"
    grep -qx 'MAINTENANCE_MODE=False' "${ENV_FILE}"
    : >"${FINALIZED_MARKER}"
    echo "PRODUCTION_FINALIZED release=${RELEASE_SHA} maintenance=False"
    while true; do
        sleep 3600
    done
fi

if [[ "${MODE}" != "deploy" ]]; then
    echo "Mode must be deploy or finalize-production" >&2
    exit 2
fi

exec 3>&1 4>&2
exec >"${LOG_FILE}" 2>&1

cleanup_temporary_release() {
    if [[ -n "${TEMP_RELEASE_DIRECTORY}" && -d "${TEMP_RELEASE_DIRECTORY}" ]]; then
        rm -rf -- "${TEMP_RELEASE_DIRECTORY}"
    fi
}

on_error() {
    local exit_code=$?
    local line_number=${1:-unknown}
    cleanup_temporary_release
    echo "DEPLOY_FAILED environment=${DEPLOY_ENVIRONMENT} release=${RELEASE_SHA} line=${line_number} exit=${exit_code}"
    : >"${FAILED_MARKER}"
    exec 1>&3 2>&4 3>&- 4>&-
    while true; do
        sleep 3600
    done
}

trap 'on_error ${LINENO}' ERR
trap cleanup_temporary_release EXIT

rm -f "${READY_MARKER}" "${FAILED_MARKER}"
echo "DEPLOY_BEGIN environment=${DEPLOY_ENVIRONMENT} release=${RELEASE_SHA}"

test -f "${ARCHIVE}"
test -f "${SCRIPTS_DIRECTORY}/create_postgres_backup.py"
test -f "${SCRIPTS_DIRECTORY}/verify_postgres_worker.py"
chmod 600 \
    "${SCRIPTS_DIRECTORY}/create_postgres_backup.py" \
    "${SCRIPTS_DIRECTORY}/verify_postgres_worker.py"
echo "${ARCHIVE_SHA256}  ${ARCHIVE}" | sha256sum --check --status
echo "ARTIFACT_VERIFIED sha256=${ARCHIVE_SHA256}"

test -f "${ENV_FILE}"
test -f "${WSGI_FILE}"
test "$(grep -c '^RELEASE_SHA=' "${ENV_FILE}")" -eq 1
if [[ "${DEPLOY_ENVIRONMENT}" == "production" ]]; then
    test "$(grep -c '^MAINTENANCE_MODE=' "${ENV_FILE}")" -eq 1
    sed -i -E 's/^MAINTENANCE_MODE=.*/MAINTENANCE_MODE=True/' "${ENV_FILE}"
    grep -qx 'MAINTENANCE_MODE=True' "${ENV_FILE}"
    echo "PRODUCTION_MAINTENANCE_ENABLED"
fi

BACKUP_TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIRECTORY}/${DEPLOY_ENVIRONMENT}-pre-${RELEASE_SHA:0:7}-${BACKUP_TIMESTAMP}.dump"
"${VIRTUALENV}/bin/python" \
    "${SCRIPTS_DIRECTORY}/create_postgres_backup.py" \
    --env-file "${ENV_FILE}" \
    --output "${BACKUP_FILE}"
echo "BACKUP_VERIFIED path=${BACKUP_FILE}"

if [[ -d "${RELEASE_DIRECTORY}" ]]; then
    test -f "${RELEASE_DIRECTORY}/.artifact-sha256"
    grep -qx "${ARCHIVE_SHA256}" "${RELEASE_DIRECTORY}/.artifact-sha256"
    echo "RELEASE_REUSED directory=${RELEASE_DIRECTORY}"
else
    mkdir -p "${HOME_DIRECTORY}/releases"
    TEMP_RELEASE_DIRECTORY="$(mktemp -d "${HOME_DIRECTORY}/releases/.${RELEASE_SHA}.XXXXXX")"
    tar -xzf "${ARCHIVE}" -C "${TEMP_RELEASE_DIRECTORY}"
    test -f "${TEMP_RELEASE_DIRECTORY}/server/manage.py"
    test -f "${TEMP_RELEASE_DIRECTORY}/server/requirements.txt"
    printf '%s\n' "${ARCHIVE_SHA256}" >"${TEMP_RELEASE_DIRECTORY}/.artifact-sha256"
    mv "${TEMP_RELEASE_DIRECTORY}" "${RELEASE_DIRECTORY}"
    TEMP_RELEASE_DIRECTORY=""
    echo "RELEASE_CREATED directory=${RELEASE_DIRECTORY}"
fi

"${VIRTUALENV}/bin/python" -m compileall -q "${RELEASE_DIRECTORY}/server"
"${VIRTUALENV}/bin/pip" install --disable-pip-version-check \
    -r "${RELEASE_DIRECTORY}/server/requirements.txt"
"${VIRTUALENV}/bin/pip" check
echo "DEPENDENCIES_VERIFIED environment=${DEPLOY_ENVIRONMENT}"

sed -i -E "s/^RELEASE_SHA=.*/RELEASE_SHA=${RELEASE_SHA}/" "${ENV_FILE}"
grep -qx "RELEASE_SHA=${RELEASE_SHA}" "${ENV_FILE}"
NEPAL_KINGS_ENV_FILE="${ENV_FILE}" \
    "${VIRTUALENV}/bin/python" \
    "${RELEASE_DIRECTORY}/server/manage.py" prepare-database
echo "DATABASE_PREPARED environment=${DEPLOY_ENVIRONMENT}"

test "$(grep -Eo '[0-9a-f]{40}' "${WSGI_FILE}" | wc -l)" -eq 1
sed -i -E "s/[0-9a-f]{40}/${RELEASE_SHA}/" "${WSGI_FILE}"
grep -Fq "${RELEASE_SHA}" "${WSGI_FILE}"
echo "WSGI_UPDATED path=${WSGI_FILE}"

(
    WORKER_VERIFIED=False
    for _attempt in $(seq 1 30); do
        if "${VIRTUALENV}/bin/python" \
            "${SCRIPTS_DIRECTORY}/verify_postgres_worker.py" \
            --env-file "${ENV_FILE}" \
            --environment "${DEPLOY_ENVIRONMENT}"; then
            WORKER_VERIFIED=True
            break
        fi
        sleep 2
    done
    if [[ "${WORKER_VERIFIED}" == "True" ]]; then
        echo "WORKER_VERIFIED environment=${DEPLOY_ENVIRONMENT}"
        : >"${READY_MARKER}"
        echo "DEPLOY_READY environment=${DEPLOY_ENVIRONMENT} release=${RELEASE_SHA}"
    else
        echo "WORKER_VERIFICATION_FAILED environment=${DEPLOY_ENVIRONMENT}"
        : >"${FAILED_MARKER}"
    fi
) >>"${LOG_FILE}" 2>&1 &

echo "WORKER_STARTING environment=${DEPLOY_ENVIRONMENT}"
trap - ERR EXIT
exec 1>&3 2>&4 3>&- 4>&-
exec env \
    NEPAL_KINGS_ENV_FILE="${ENV_FILE}" \
    AI_ENABLED=True \
    AI_JOBS_ENABLED=True \
    "${VIRTUALENV}/bin/python" \
    "${RELEASE_DIRECTORY}/server/manage.py" run-worker
