#!/usr/bin/env bash
# ── Systemd service installer ─────────────────────────────────────────────────
# Installs and enables the talksig systemd service on the local machine.
# Called by both `make install` (on-Pi) and `make service` (via SSH from laptop).
#
#   bash scripts/install-service.sh [service-name]
#
# Placeholders substituted automatically:
#   {{PI_DIR}}  → current working directory
#   {{USER}}    → current user
#   {{UV_BIN}}  → resolved path to the uv binary
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'; NC='\033[0m'
ok() { echo -e "${GREEN}✓  $*${NC}"; }

# Run from the project root (raspi/)
cd "$(dirname "${BASH_SOURCE[0]}")/.."

SERVICE="${1:-talksig}"
PI_DIR="$(pwd)"
CURRENT_USER="$(whoami)"
UV_BIN="$(which uv 2>/dev/null || echo "$HOME/.local/bin/uv")"

echo "Installing systemd service '$SERVICE' …"
echo "  Dir : $PI_DIR"
echo "  User: $CURRENT_USER"
echo "  UV  : $UV_BIN"

sed \
    -e "s|{{PI_DIR}}|$PI_DIR|g" \
    -e "s|{{USER}}|$CURRENT_USER|g" \
    -e "s|{{UV_BIN}}|$UV_BIN|g" \
    talksig.service \
    | sudo tee "/etc/systemd/system/${SERVICE}.service" > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE"
ok "Service '$SERVICE' installed and started."
echo "  Logs:   journalctl -u $SERVICE -f"
echo "  Status: systemctl status $SERVICE"
