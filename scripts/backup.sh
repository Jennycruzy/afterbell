#!/usr/bin/env bash
# Copy AFTERBELL's irreplaceable recorder data to a second location.
#
# The destination is intentionally supplied outside the repository. `copy`
# never deletes remote files, and the OAuth pending file is excluded because
# it contains a live PKCE verifier. Configure /etc/afterbell/backup.env with:
#   AFTERBELL_BACKUP_REMOTE=remote-name:afterbell
set -euo pipefail

ROOT=/home/ubuntu/afterbell
DATA="$ROOT/data"
LOG="$DATA/backup.log"
ENV_FILE="${AFTERBELL_BACKUP_ENV:-/etc/afterbell/backup.env}"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { printf '%s %s\n' "$(ts)" "$*" >> "$LOG"; }

if [ -r "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  . "$ENV_FILE"
fi

remote="${AFTERBELL_BACKUP_REMOTE:-}"
if [ -z "$remote" ]; then
  log "BACKUP GAP: AFTERBELL_BACKUP_REMOTE is not configured in $ENV_FILE"
  exit 2
fi
if ! command -v rclone >/dev/null 2>&1; then
  log "BACKUP GAP: rclone is not installed"
  exit 2
fi

log "copying recorder data to configured backup destination"
rclone copy "$DATA" "$remote" \
  --exclude '.oauth_pending.json' \
  --exclude '*.tmp' \
  --create-empty-src-dirs \
  --checkers 4 --transfers 2 --log-level NOTICE >> "$LOG" 2>&1

tmp="$DATA/.backup_status.tmp"
printf '%s\n' "{\"ts\":\"$(ts)\",\"status\":\"OK\"}" > "$tmp"
mv -f "$tmp" "$DATA/backup_status.json"
log "backup completed"
