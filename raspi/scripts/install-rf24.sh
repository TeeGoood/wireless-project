#!/usr/bin/env bash
# ── RF24 Toolchain Installer ───────────────────────────────────────────────────
# Run this once on the Raspberry Pi to get the RF24 hardware driver working.
#
#   cd ~/talksig
#   bash scripts/install-rf24.sh
#
# What it does (in order):
#   1. Detects the Raspberry Pi model
#   2. Enables the SPI interface in boot config
#   3. Installs system build tools via apt (git, cmake, g++, python3-dev)
#   4. Adds the current user to the spi + gpio groups
#   5. Installs the pyrf24 Python binding:
#        a) pre-built wheel from PyPI  (fast, works on Python ≤ 3.12)
#        b) build from source           (fallback, works on any Python, ~15 min)
#   6. Verifies the import
#
# Dependencies: bash, sudo, apt, git, uv (run setup.sh first)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Helpers ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'
ok() { echo -e "${GREEN}✓  $*${NC}"; }
warn() { echo -e "${YELLOW}⚠  $*${NC}"; }
info() { echo -e "${BOLD}▶  $*${NC}"; }
die() {
    echo -e "${RED}✗  $*${NC}"
    exit 1
}
hr() { echo "────────────────────────────────────────────────────────────"; }

# ── Always run from the project root (raspi/) ─────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
PROJECT_DIR="$(pwd)"

hr
echo "  RF24 Toolchain Installer"
echo "  Project: $PROJECT_DIR"
hr

NEEDS_REBOOT=false
NEEDS_RELOGIN=false

PATH=$HOME/.local/bin/:$PATH
# ── 1. Raspberry Pi detection ─────────────────────────────────────────────────
info "Detecting hardware …"
if [[ -f /proc/device-tree/model ]]; then
    MODEL=$(tr -d '\0' </proc/device-tree/model)
    ok "Running on: $MODEL"
    ON_PI=true
else
    warn "Not a Raspberry Pi (no device-tree model). SPI steps will be skipped."
    warn "The RF24 driver will run in mock mode – this is fine for local dev."
    ON_PI=false
fi

# ── 2. Enable SPI ─────────────────────────────────────────────────────────────
if [[ "$ON_PI" == true ]]; then
    info "Enabling SPI interface …"

    # Bookworm moved config to /boot/firmware; older OS uses /boot
    BOOT_CFG=""
    for candidate in /boot/firmware/config.txt /boot/config.txt; do
        [[ -f "$candidate" ]] && BOOT_CFG="$candidate" && break
    done

    if [[ -z "$BOOT_CFG" ]]; then
        warn "Boot config not found. Enable SPI manually: sudo raspi-config → Interface Options → SPI"
    else
        if grep -qE '^dtparam=spi=on' "$BOOT_CFG"; then
            ok "SPI already enabled in $BOOT_CFG."
        else
            # Remove any disabled line then append a clean one
            sudo sed -i '/^#*dtparam=spi=/d' "$BOOT_CFG"
            echo 'dtparam=spi=on' | sudo tee -a "$BOOT_CFG" >/dev/null
            ok "SPI enabled in $BOOT_CFG."
            NEEDS_REBOOT=true
        fi
    fi

    if ls /dev/spidev* &>/dev/null 2>&1; then
        ok "SPI device present: $(ls /dev/spidev* | tr '\n' ' ')"
    else
        warn "/dev/spidev* not found yet – may need a reboot."
    fi
fi

# ── 3. System build dependencies ──────────────────────────────────────────────
info "Installing system build dependencies …"
# python3-dev      – Python C headers for building native extensions
# cmake + g++      – build toolchain required for RF24 source builds
# libgpiod-dev     – GPIO library used by modern RF24 on 64-bit Pi OS
# git              – needed to clone pyrf24 when building from source
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    git \
    cmake \
    g++ \
    python3-dev \
    libgpiod-dev |
    grep -E '(Installed|already installed|upgraded)' || true
ok "System build deps ready."

# ── 4. SPI + GPIO group membership ───────────────────────────────────────────
info "Configuring SPI / GPIO group membership …"
for GROUP in spi gpio; do
    if getent group "$GROUP" &>/dev/null; then
        if id -nG "$USER" | grep -qw "$GROUP"; then
            ok "User '$USER' is already in group '$GROUP'."
        else
            sudo usermod -aG "$GROUP" "$USER"
            ok "Added '$USER' to group '$GROUP'."
            NEEDS_RELOGIN=true
        fi
    else
        warn "Group '$GROUP' not found – skipping (might not be a Pi)."
    fi
done

# ── 5. pyrf24 Python binding ──────────────────────────────────────────────────
info "Installing pyrf24 Python binding …"

if ! command -v $HOME/.local/bin/uv &>/dev/null; then
    die "uv not found. Run 'bash setup.sh' first to install uv."
fi

# Detect which Python the venv uses (for reporting)
VENV_PY=$($HOME/.local/bin/uv run python --version 2>&1 || echo "unknown")
info "Target Python: $VENV_PY"

# ── 5a. Clone / update pyrf24 source into vendor/ ────────────────────────────
#
# Cloning into the repo (vendor/pyrf24/) keeps the source persistent so that:
#   • uv sync on subsequent deploys finds it immediately (no re-clone needed)
#   • pyproject.toml tracks it as a real dependency (not a side-channel install)
#   • `uv sync` won't wipe it the way `uv pip install` gets wiped by --frozen

VENDOR_DIR="$PROJECT_DIR/vendor/pyrf24"

if [[ -d "$VENDOR_DIR/.git" ]]; then
    info "vendor/pyrf24 already present – updating …"
    git -C "$VENDOR_DIR" pull --recurse-submodules --quiet
    ok "vendor/pyrf24 updated."
else
    info "Cloning nRF24/pyrf24 into vendor/pyrf24/ …"
    warn "This clone includes C++ submodules and may take a minute."
    mkdir -p "$PROJECT_DIR/vendor"
    git clone \
        --depth=1 \
        --recurse-submodules \
        --shallow-submodules \
        https://github.com/nRF24/pyrf24.git \
        "$VENDOR_DIR"
    ok "vendor/pyrf24 cloned."
fi

# ── 5b. Build + install via uv pip ───────────────────────────────────────────
#
# pyrf24 is intentionally NOT declared in pyproject.toml – it is Linux-only and
# the path dependency would break `uv sync` on Mac/Windows (uv validates paths
# eagerly regardless of platform markers).
#
# Instead, we install it directly with `uv pip install` here, and `make deploy`
# uses `uv sync --inexact` so uv doesn't remove it on subsequent deploys.

info "Building pyrf24 from vendor/pyrf24/ (first run ~10-20 min) …"
warn "This takes 10-20 minutes on a Pi 4. Grab a coffee ☕"
uv pip install --no-build-isolation --reinstall "$VENDOR_DIR"
ok "pyrf24 built and installed."

# ── 6. Verify ─────────────────────────────────────────────────────────────────
info "Verifying RF24 import …"
if uv run python -c "
import pyrf24
ver = getattr(pyrf24, '__version__', 'unknown')
print(f'  RF24 version: {ver}')
" 2>/dev/null; then
    ok "RF24 imported successfully – hardware driver is active."
else
    warn "RF24 import failed."
    if [[ "$ON_PI" == true ]] && [[ "$NEEDS_REBOOT" == true ]]; then
        warn "This is expected – SPI was just enabled. Reboot, then re-run this script."
    else
        warn "The server will fall back to mock mode."
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
hr
ok "RF24 toolchain install complete."
echo ""

if [[ "$NEEDS_REBOOT" == true ]]; then
    echo -e "${YELLOW}⚠  SPI was just enabled in boot config.${NC}"
    echo "   Reboot the Pi before starting the server:"
    echo "     sudo reboot"
    echo "   Then re-run this script to verify the import."
    echo ""
fi

if [[ "$NEEDS_RELOGIN" == true ]]; then
    echo -e "${YELLOW}⚠  Group membership changed.${NC}"
    echo "   Log out and back in (or run the command below) for it to take effect:"
    echo "     exec su - \$USER"
    echo ""
fi

if [[ "$NEEDS_REBOOT" == false ]] && [[ "$NEEDS_RELOGIN" == false ]]; then
    echo "  Start the server (no sudo needed):"
    echo "    uv run python server.py"
    echo ""
fi
hr
