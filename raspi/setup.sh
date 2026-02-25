#!/usr/bin/env bash
# ── First-time Pi bootstrap ────────────────────────────────────────────────────
# Run this once after copying the project to the Pi:
#   bash setup.sh
#
# What it does:
#   1. Installs UV (if missing)
#   2. Installs Python deps from uv.lock
#   3. Reminds you about RF24 and firebase-key.json
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
die()  { echo -e "${RED}✗ $*${NC}"; exit 1; }

# ── 1. UV ──────────────────────────────────────────────────────────────────────

if command -v uv &>/dev/null; then
    ok "UV already installed: $(uv --version)"
else
    echo "Installing UV …"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Make uv available in the current shell session
    export PATH="$HOME/.local/bin:$PATH"
    ok "UV installed: $(uv --version)"
fi

# ── 2. Python deps ─────────────────────────────────────────────────────────────

echo "Installing Python dependencies from lockfile …"
uv sync --frozen
ok "Dependencies installed."

# ── 3. RF24 library check ──────────────────────────────────────────────────────

if python -c "import RF24" 2>/dev/null; then
    ok "RF24 library is importable."
else
    warn "RF24 library not found – the driver will run in mock mode."
    echo "  To install on Raspberry Pi OS:"
    echo "    pip install pyrf24"
    echo "  Or follow: https://github.com/nRF24/RF24#installation"
fi

# ── 4. Firebase key ────────────────────────────────────────────────────────────

if [ -f "firebase-key.json" ]; then
    ok "firebase-key.json present."
else
    warn "firebase-key.json not found."
    echo "  Copy it from your local machine:"
    echo "    scp raspi/firebase-key.json pi@<pi-ip>:~/talksig/"
fi

# ── 5. Config ──────────────────────────────────────────────────────────────────

if [ -f "config.txt" ]; then
    ok "config.txt found:"
    cat config.txt | sed 's/^/    /'
else
    echo "Creating default config.txt …"
    cat > config.txt <<'EOF'
color=Unknown
plate=UNKNOWN
model=Unknown
owner=Unknown
EOF
    ok "config.txt created – edit it or use the 'setinfo' command in testkit."
fi

# ── Done ───────────────────────────────────────────────────────────────────────

echo ""
ok "Setup complete."
echo ""
echo "  Start the server:"
echo "    uv run python server.py"
echo ""
echo "  Run the testkit (in another terminal):"
echo "    uv run python testkit.py"
echo ""
echo "  Install as a systemd service (run on this Pi):"
echo "    make install"
echo ""
echo "  Or from your laptop over SSH:"
echo "    make service"
echo ""
