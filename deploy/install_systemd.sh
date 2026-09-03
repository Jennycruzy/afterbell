#!/usr/bin/env bash
set -euo pipefail

repo=/home/ubuntu/afterbell
sudo install -m 0644 "$repo"/deploy/systemd/afterbell-recorder.service /etc/systemd/system/
sudo install -m 0644 "$repo"/deploy/systemd/afterbell-dashboard.service /etc/systemd/system/
sudo install -m 0644 "$repo"/deploy/systemd/afterbell-guard.service /etc/systemd/system/
sudo install -m 0644 "$repo"/deploy/systemd/afterbell-backup.service /etc/systemd/system/
sudo install -m 0644 "$repo"/deploy/systemd/afterbell-backup.timer /etc/systemd/system/
sudo install -m 0644 "$repo"/deploy/systemd/afterbell-watchdog.service /etc/systemd/system/
sudo install -m 0644 "$repo"/deploy/systemd/afterbell-watchdog.timer /etc/systemd/system/
sudo install -d -m 0755 /usr/local/libexec
sudo install -m 0755 "$repo"/scripts/backup.sh /usr/local/libexec/afterbell-backup.sh
sudo install -m 0755 "$repo"/scripts/healthcheck.sh /usr/local/libexec/afterbell-healthcheck.sh
sudo install -m 0755 "$repo"/scripts/watchdog.sh /usr/local/libexec/afterbell-watchdog.sh
sudo sed -i \
  -e 's#ExecStart=/home/ubuntu/afterbell/scripts/backup.sh#ExecStart=/usr/local/libexec/afterbell-backup.sh#' \
  -e 's#ExecStart=/home/ubuntu/afterbell/scripts/watchdog.sh#ExecStart=/usr/local/libexec/afterbell-watchdog.sh#' \
  /etc/systemd/system/afterbell-backup.service /etc/systemd/system/afterbell-watchdog.service
sudo sed -i 's#HEALTH=/home/ubuntu/afterbell/scripts/healthcheck.sh#HEALTH=/usr/local/libexec/afterbell-healthcheck.sh#' /usr/local/libexec/afterbell-watchdog.sh
sudo systemctl daemon-reload
sudo systemctl enable --now afterbell-recorder.service afterbell-dashboard.service afterbell-guard.service
sudo systemctl enable --now afterbell-backup.timer afterbell-watchdog.timer
sudo systemctl --no-pager --full status afterbell-recorder.service afterbell-dashboard.service afterbell-guard.service afterbell-backup.timer afterbell-watchdog.timer
