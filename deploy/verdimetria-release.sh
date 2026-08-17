#!/usr/bin/env bash
# Release Verdimetria from the git checkout on pcc.
# Usage: verdimetria-release.sh [--no-backup]
set -euo pipefail

APP_DIR="${VERDIMETRIA_APP_DIR:-/opt/verdimetria}"
LOG="${VERDIMETRIA_RELEASE_LOG:-/var/log/verdimetria-releases.log}"
BACKUP_DIR="${VERDIMETRIA_BACKUP_DIR:-/var/backups/verdimetria}"
SKIP_BACKUP=0
[[ "${1:-}" == "--no-backup" ]] && SKIP_BACKUP=1

cd "$APP_DIR"
prev="$(git rev-parse --short HEAD)"
tracked="$(git status --porcelain --untracked-files=no)"
if [[ -n "$tracked" ]]; then
    echo "tracked_worktree=dirty" >&2
    echo "$tracked" >&2
    exit 1
fi

mkdir -p "$(dirname "$LOG")" "$BACKUP_DIR"
git fetch origin main
git pull --ff-only origin main
after="$(git rev-parse --short HEAD)"

set -a
# shellcheck disable=SC1091
. /etc/verdimetria/app.env
. /etc/verdimetria/db.env
. /etc/verdimetria/smtp.env
. /etc/verdimetria/providers.env
. /etc/verdimetria/stripe.env
set +a
export DJANGO_SETTINGS_MODULE=backend.config.settings

if [[ "$SKIP_BACKUP" -eq 0 ]]; then
    stamp="$(date +%Y%m%d-%H%M%S)"
    dump="$BACKUP_DIR/verdimetria-pre-${after}-${stamp}.dump"
    PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
        -h "${POSTGRES_HOST:-127.0.0.1}" \
        -p "${POSTGRES_PORT:-5432}" \
        -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" \
        -Fc -f "$dump"
    echo "backup=$dump"
fi

.venv/bin/python manage.py check
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput
systemctl restart verdimetria verdimetria-celery
sleep 2
systemctl is-active verdimetria verdimetria-celery nginx >/dev/null

curl -fsS -H "Host: api.verdimetria.cais.uno" http://127.0.0.1:8001/health/ >/dev/null
curl -fsS -H "Host: api.verdimetria.cais.uno" http://127.0.0.1:8001/ready/ >/dev/null
curl -fsS https://api.verdimetria.cais.uno/health/ >/dev/null
curl -fsS https://api.verdimetria.cais.uno/ready/ >/dev/null

printf '%s release %s <- %s user=%s\n' \
    "$(date --iso-8601=seconds)" "$after" "$prev" "${SUDO_USER:-${USER:-root}}" \
    | tee -a "$LOG"
echo "release_ok=$after prev=$prev"
