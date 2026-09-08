#!/usr/bin/env bash
set -uo pipefail

repo=/home/ubuntu/afterbell
log="$repo/data/quality.log"
status_file="$repo/data/quality_status.json"
mkdir -p "$repo/data"
temporary="$(mktemp "$repo/data/.quality-status.XXXXXX")"
timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

status=Healthy
{
  echo "[$timestamp] AFTERBELL quality check"
  "$repo/.venv/bin/ruff" check "$repo/afterbell" "$repo/scripts"
  "$repo/.venv/bin/python" -m pytest "$repo/tests" --cov=afterbell --cov-report=term-missing -q
  "$repo/.venv/bin/python" -m pip check
  "$repo/.venv/bin/python" -c \
    "from importlib.metadata import requires; assert any('cryptography' in r for r in requires('afterbell'))"
} >"$log" 2>&1 || status=Failed

printf '{"status":"%s","ts":"%s","log":"data/quality.log"}\n' \
  "$status" "$timestamp" >"$temporary"
chmod 0644 "$temporary"
mv "$temporary" "$status_file"

if [ "$status" != Healthy ]; then
  tail -n 80 "$log" >&2
  exit 1
fi

tail -n 20 "$log"
