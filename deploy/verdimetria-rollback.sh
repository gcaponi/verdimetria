#!/usr/bin/env bash
# Roll back Verdimetria to a previous commit (default: last release's parent).
# Usage: verdimetria-rollback.sh [sha]
set -euo pipefail

APP_DIR="${VERDIMETRIA_APP_DIR:-/opt/verdimetria}"
LOG="${VERDIMETRIA_RELEASE_LOG:-/var/log/verdimetria-releases.log}"

cd "$APP_DIR"
current="$(git rev-parse --short HEAD)"
if [[ -n "${1:-}" ]]; then
    target="$1"
else
    target="$(git rev-parse --short HEAD^)"
fi

git reset --hard "$target"
set -a
# shellcheck disable=SC1091
. /etc/verdimetria/app.env
. /etc/verdimetria/db.env
. /etc/verdimetria/smtp.env
. /etc/verdimetria/providers.env
. /etc/verdimetria/stripe.env
set +a
export DJANGO_SETTINGS_MODULE=backend.config.settings
.venv/bin/python manage.py check
systemctl restart verdimetria verdimetria-celery
sleep 2
systemctl is-active verdimetria verdimetria-celery nginx >/dev/null
curl -fsS -H "Host: api.verdimetria.cais.uno" http://127.0.0.1:8001/health/ >/dev/null
curl -fsS https://api.verdimetria.cais.uno/health/ >/dev/null

printf '%s rollback %s <- %s user=%s\n' \
    "$(date --iso-8601=seconds)" "$(git rev-parse --short HEAD)" "$current" \
    "${SUDO_USER:-${USER:-root}}" | tee -a "$LOG"
echo "rollback_ok=$(git rev-parse --short HEAD) from=$current"
