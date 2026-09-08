#!/usr/bin/env bash
# Copy AFTERBELL recorder data to a second location and verify stable data.
#
# The destination is supplied outside the repository. Files modified inside
# the minimum-age window are skipped, stable data is checked against the
# remote, and old local raw archives are removed only after an exact check.
# The OAuth pending file is excluded because it contains a live PKCE verifier.
# Configure /etc/afterbell/backup.env with AFTERBELL_BACKUP_REMOTE and keep the
# rclone config in a directory writable by the service user.
set -euo pipefail

ROOT=/home/ubuntu/afterbell
DATA="$ROOT/data"
LOG="$DATA/backup.log"
ENV_FILE=/etc/afterbell/backup.env
configured_env="${AFTERBELL_BACKUP_ENV:-}"
if [ -n "$configured_env" ]; then
  ENV_FILE="$configured_env"
fi

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { printf '%s %s\n' "$(ts)" "$*" >> "$LOG"; }

if [ -r "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  . "$ENV_FILE"
fi

remote="${AFTERBELL_BACKUP_REMOTE:-}"
min_age="${AFTERBELL_BACKUP_MIN_AGE:-2m}"
retention_days="${AFTERBELL_BACKUP_RETENTION_DAYS:-14}"

write_status() {
  local status="$1"
  local covered_through="$2"
  local tmp="$DATA/.backup_status.$$.tmp"
  printf '{"covered_through":"%s","retention_days":"%s","status":"%s","ts":"%s"}\n' \
    "$covered_through" "$retention_days" "$status" "$(ts)" > "$tmp"
  mv -f -- "$tmp" "$DATA/backup_status.json"
}

fail() {
  local message="$1"
  local code=1
  if [ "$#" -ge 2 ]; then
    code="$2"
  fi
  log "BACKUP GAP: $message"
  write_status "FAILED" ""
  exit "$code"
}

if [ -z "$remote" ]; then
  fail "AFTERBELL_BACKUP_REMOTE is not configured in $ENV_FILE" 2
fi
if ! command -v rclone >/dev/null 2>&1; then
  fail "rclone is not installed" 2
fi
case "$retention_days" in
  ''|*[!0-9]*) fail "AFTERBELL_BACKUP_RETENTION_DAYS must be a positive integer" 2 ;;
esac
if [ "$retention_days" -lt 1 ]; then
  fail "AFTERBELL_BACKUP_RETENTION_DAYS must be at least 1" 2
fi

# rclone writes refreshed OAuth tokens beside its config. Fail visibly when a
# configured path points into a directory the service user cannot write.
rclone_config="${RCLONE_CONFIG:-}"
home_dir="${HOME:-}"
[ -n "$home_dir" ] || home_dir=/home/ubuntu
if [ -z "$rclone_config" ]; then
  rclone_config="$home_dir/.config/rclone/rclone.conf"
fi
rclone_dir=$(dirname -- "$rclone_config")
if [ ! -d "$rclone_dir" ] || [ ! -w "$rclone_dir" ]; then
  fail "rclone config directory is not writable: $rclone_dir" 2
fi
if [ ! -f "$rclone_config" ] || [ ! -r "$rclone_config" ]; then
  fail "rclone config is missing or unreadable: $rclone_config" 2
fi

log "copying recorder data to configured backup destination"
if ! rclone --config "$rclone_config" copy "$DATA" "$remote" \
  --exclude '.oauth_pending.json' \
  --exclude '*.tmp' \
  --exclude 'backup.log' \
  --exclude 'backup_status.json' \
  --min-age "$min_age" \
  --create-empty-src-dirs \
  --checkers 4 --transfers 2 --log-level NOTICE >> "$LOG" 2>&1; then
  fail "rclone copy failed" 1
fi

# The active UTC day's raw archive is excluded from verification. This makes
# OK mean every stable archive is present remotely, not merely that rclone
# exited zero after observing a hot file.
today=$(date -u +%F)
if ! rclone --config "$rclone_config" check "$DATA" "$remote" \
  --exclude '.oauth_pending.json' \
  --exclude '*.tmp' \
  --exclude 'backup.log' \
  --exclude 'backup_status.json' \
  --exclude "raw/$today/**" \
  --min-age "$min_age" \
  --one-way --checkers 4 --log-level NOTICE >> "$LOG" 2>&1; then
  fail "stable-data verification failed" 1
fi

# Only prune a closed raw-day directory after checking that exact directory
# against the remote. The current archive is never a retention candidate.
cutoff=$(date -u -d "$retention_days days ago" +%F)
for day_dir in "$DATA/raw"/*; do
  [ -d "$day_dir" ] || continue
  day=$(basename -- "$day_dir")
  [[ "$day" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || continue
  [ "$day" != "$today" ] || continue
  if [[ "$day" < "$cutoff" ]]; then
    if rclone --config "$rclone_config" check "$day_dir" "$remote/raw/$day" \
      --one-way --checkers 4 --log-level NOTICE >> "$LOG" 2>&1; then
      rm -rf -- "$day_dir"
      log "retention removed verified raw archive $day"
    else
      fail "retention verification failed for raw archive $day" 1
    fi
  fi
done

write_status "OK" "$(date -u -d '1 day ago' +%F)"
log "backup completed; stable data verified"
