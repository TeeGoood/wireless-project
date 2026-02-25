#!/usr/bin/env bash
# ── Project bootstrap ─────────────────────────────────────────────────────────
# Run this once after copying the project to the Pi:
#   bash setup.sh
#
# For the full install including the RF24 hardware driver, run:
#   bash setup.sh --with-rf24
#   (or afterwards: bash scripts/install-rf24.sh)
#
# What it does:
#   1. Installs UV (if missing)
#   2. Installs Python deps from uv.lock
#   3. Adds current user to spi + gpio groups
#   4. Checks for firebase-key.json
#   5. Creates a default config.txt if missing
#   6. Optionally runs scripts/install-rf24.sh (--with-rf24 flag)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
die()  { echo -e "${RED}✗ $*${NC}"; exit 1; }

WITH_RF24=false
for arg in "$@"; do
    [[ "$arg" == "--with-rf24" ]] && WITH_RF24=true
done

# Run from the directory the script lives in
cd "$(dirname "${BASH_SOURCE[0]}")"

# ── 1. UV ──────────────────────────────────────────────────────────────────────

if command -v uv &>/dev/null; then
    ok "UV already installed: $(uv --version)"
else
    echo "Installing UV …"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    ok "UV installed: $(uv --version)"
fi

# ── 2. Python deps ─────────────────────────────────────────────────────────────

echo "Installing Python dependencies from lockfile …"
uv sync --frozen
ok "Dependencies installed."

# ── 3. SPI + GPIO group membership ────────────────────────────────────────────

NEEDS_RELOGIN=false
for GROUP in spi gpio; do
    if getent group "$GROUP" &>/dev/null; then
        if id -nG "$USER" | grep -qw "$GROUP"; then
            ok "User '$USER' is already in group '$GROUP'."
        else
            echo "Adding '$USER' to group '$GROUP' …"
            sudo usermod -aG "$GROUP" "$USER"
            ok "Added to '$GROUP'."
            NEEDS_RELOGIN=true
        fi
    else
        warn "Group '$GROUP' does not exist – skipping (not running on a Pi?)."
    fi
done

# ── 4. Firebase key ────────────────────────────────────────────────────────────

if [ -f "firebase-key.json" ]; then
    ok "firebase-key.json present."
else
    warn "firebase-key.json not found."
    echo "  Copy it from your local machine:"
    echo "    scp raspi/firebase-key.json <user>@<pi-ip>:~/talksig/"
fi

# ── 5. Config ──────────────────────────────────────────────────────────────────

if [ -f "config.txt" ]; then
    ok "config.txt found:"
    sed 's/^/    /' config.txt
else
    echo "Creating default config.txt …"
    cat > config.txt <<'EOF'
color=Unknown
plate=UNKNOWN
model=Unknown
owner=Unknown
EOF
    ok "config.txt created – edit it or use 'setinfo' in the testkit."
fi

# ── 6. RF24 toolchain (optional) ──────────────────────────────────────────────

if [ "$WITH_RF24" = true ]; then
    echo ""
    echo "Running RF24 toolchain installer …"
    bash scripts/install-rf24.sh
fi

# ── Done ───────────────────────────────────────────────────────────────────────

echo ""
ok "Setup complete."
echo ""

if [ "$NEEDS_RELOGIN" = true ]; then
    echo -e "${YELLOW}⚠  Group membership changed – log out and back in first:${NC}"
    echo "     exec su - \$USER"
    echo ""
fi

if [ "$WITH_RF24" = false ]; then
    echo "  To install the RF24 hardware driver (required on the Pi):"
    echo "    bash scripts/install-rf24.sh"
    echo ""
fi

echo "  Start the server (no sudo needed after re-login):"
echo "    uv run python server.py"
echo ""
echo "  Run the testkit (in another terminal):"
echo "    uv run python testkit.py"
echo ""
echo "  Install as a systemd service:"
echo "    make install"
echo ""
