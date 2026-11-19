#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV_BIN="$(command -v uv || echo "${HOME}/.local/bin/uv")"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "${UNIT_DIR}"

cat > "${UNIT_DIR}/aegean-eced-watchdog.service" <<EOF
[Unit]
Description=Aegean e-ÇED Ecological Watchdog (daily incremental poll & digest)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-${REPO_DIR}/.env
WorkingDirectory=${REPO_DIR}
ExecStart=${UV_BIN} run eced-watch --days 14 --max-digests 4
Nice=10
EOF

cat > "${UNIT_DIR}/aegean-eced-watchdog.timer" <<EOF
[Unit]
Description=Run Aegean e-ÇED Ecological Watchdog daily

[Timer]
OnCalendar=*-*-* 09:00:00
RandomizedDelaySec=15m
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now aegean-eced-watchdog.timer
systemctl --user list-timers aegean-eced-watchdog.timer --no-pager
