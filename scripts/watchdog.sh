#!/usr/bin/env bash
# Recorder watchdog. The highest-cost failure in this project is the recorder
# dying quietly at 03:00 while nobody is watching: the off-hours order books it
# collects cannot be back-filled afterwards.
#
# Runs from cron every 5 minutes. Restarts a stale recorder and appends to a
# log that is checked each morning.
set -uo pipefail

HB=/home/ubuntu/afterbell/data/heartbeat
LOG=/home/ubuntu/afterbell/data/watchdog.log
MAX_AGE=300            # heartbeat older than 5 minutes is stale
DISK_PCT_ALERT=80
HEALTH=/home/ubuntu/afterbell/scripts/healthcheck.sh

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
issues=0

if [ ! -f "$HB" ]; then
  echo "$(ts) MISSING heartbeat; restarting recorder" >> "$LOG"
  systemctl restart afterbell-recorder
  issues=1
else
  age=$(( $(date +%s) - $(stat -c %Y "$HB") ))
  if [ "$age" -gt "$MAX_AGE" ]; then
    echo "$(ts) STALE heartbeat (${age}s); restarting recorder" >> "$LOG"
    systemctl restart afterbell-recorder
    issues=1
  fi
fi

for unit in afterbell-recorder afterbell-dashboard afterbell-guard afterbell-mcp; do
  if ! systemctl is-active --quiet "$unit"; then
    echo "$(ts) $unit not active; restarting" >> "$LOG"
    systemctl restart "$unit"
    issues=1
  fi
done

# Operator freeze transitions. The freeze itself is enforced in the guard and
# receipted in the ledger; this reports the edge, so engaging or releasing it
# from an SSH session is visible without reading the ledger.
FREEZE=$(sed -n 's/^ *kill_file: *//p' /home/ubuntu/afterbell/config/policy.yaml | head -1)
SEEN=/home/ubuntu/afterbell/data/.freeze_seen
now=absent
[ -n "$FREEZE" ] && [ -e "$FREEZE" ] && now=present
was=$(cat "$SEEN" 2>/dev/null || echo absent)
if [ "$now" != "$was" ]; then
  echo "$now" > "$SEEN"
  if [ "$now" = present ]; then
    echo "$(ts) FREEZE ENGAGED: $FREEZE present; all authorizations refused" >> "$LOG"
    "$HEALTH" fail "AFTERBELL operator freeze ENGAGED; every authorization is refused"
  else
    echo "$(ts) FREEZE RELEASED: $FREEZE removed" >> "$LOG"
    "$HEALTH" ok "AFTERBELL operator freeze RELEASED"
  fi
fi

pct=$(df --output=pcent /home/ubuntu | tail -1 | tr -dc '0-9')
if [ "${pct:-0}" -ge "$DISK_PCT_ALERT" ]; then
  echo "$(ts) DISK at ${pct}%" >> "$LOG"
  issues=1
fi

if [ "$issues" -eq 0 ]; then
  "$HEALTH" ok "afterbell watchdog healthy; disk=${pct}%"
else
  "$HEALTH" fail "afterbell watchdog detected a service, heartbeat, or disk issue; disk=${pct}%"
fi
