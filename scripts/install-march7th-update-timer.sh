#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$PROJECT_ROOT" == *" "* ]]; then
    echo "The project path must not contain spaces for the systemd service." >&2
    exit 1
fi

RUN_USER="${SUDO_USER:-$(id -un)}"
RUN_GROUP="$(id -gn "$RUN_USER")"
SERVICE_PATH="/etc/systemd/system/gamesavior-march7th-update.service"
TIMER_PATH="/etc/systemd/system/gamesavior-march7th-update.timer"

sudo tee "$SERVICE_PATH" >/dev/null <<EOF
[Unit]
Description=Check for and safely deploy March7thAssistant updates
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
User=$RUN_USER
Group=$RUN_GROUP
WorkingDirectory=$PROJECT_ROOT
ExecStart=/bin/bash $PROJECT_ROOT/scripts/update-march7th-image.sh
TimeoutStartSec=infinity
EOF

sudo tee "$TIMER_PATH" >/dev/null <<'EOF'
[Unit]
Description=Check for March7thAssistant updates every six hours

[Timer]
OnBootSec=15min
OnUnitActiveSec=6h
RandomizedDelaySec=15min
Persistent=true
Unit=gamesavior-march7th-update.service

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now gamesavior-march7th-update.timer
sudo systemctl list-timers gamesavior-march7th-update.timer
