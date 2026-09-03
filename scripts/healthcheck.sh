#!/usr/bin/env bash
# Healthchecks.io-compatible notification helper.
#
# A URL is supplied only in /etc/afterbell/monitor.env. Without one, the
# missing alert destination is recorded locally instead of being presented as
# a healthy external monitor.
set -euo pipefail

ROOT=/home/ubuntu/afterbell
LOG="$ROOT/data/watchdog.log"
state="${1:-ok}"
message="${2:-afterbell watchdog}"
url="${AFTERBELL_HEALTHCHECKS_URL:-}"
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

if [ -z "$url" ]; then
  printf '%s ALERT GAP: external healthcheck URL is not configured; state=%s\n' \
    "$(ts)" "$state" >> "$LOG"
  exit 0
fi

endpoint="$url"
if [ "$state" = "fail" ]; then
  endpoint="${url%/}/fail"
fi
curl --fail --silent --show-error --max-time 10 \
  --data-binary "$message" "$endpoint" >/dev/null
