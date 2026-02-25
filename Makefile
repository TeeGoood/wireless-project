# ── Target Pi (override: make deploy PI=pi@192.168.1.10) ─────────────────────
# NOTE: no inline comments after variable assignments – trailing spaces break commands.
PI      ?= pi@raspberrypi.local
PI_DIR  ?= ~/talksig
SERVICE ?= talksig

# ServerAliveInterval: send a keepalive packet every 60 s.
# ServerAliveCountMax: give up after 30 missed replies (= 30 min max idle).
# This keeps the connection alive during the RF24 source build (~15–20 min).
SSHOPTS := -o ServerAliveInterval=60 -o ServerAliveCountMax=30

# REMOTE: login shell over SSH so ~/.profile is sourced and ~/.local/bin
# (where uv installs itself) is on PATH.  Use this for any command that
# calls uv or scripts that call uv.  Plain `ssh` is used for everything else.
REMOTE := ssh $(SSHOPTS) $(PI) bash -lc

.PHONY: help firstrun sync deploy rf24 service install logs restart restart-pi stop status shell

help:
	@echo ""
	@echo "  ── First time (from your laptop, no Pi login needed) ──────────"
	@echo "  make firstrun  sync + bootstrap + RF24 driver + systemd service"
	@echo ""
	@echo "  ── Day-to-day (from your laptop) ──────────────────────────────"
	@echo "  make sync      push source files to the Pi (no restart)"
	@echo "  make deploy    sync + uv sync + restart service"
	@echo ""
	@echo "  ── Individual steps (via SSH, idempotent – safe to re-run) ────"
	@echo "  make rf24      install RF24 C++ lib + pyrf24  (~15 min first run)"
	@echo "  make service   install / refresh the systemd service unit"
	@echo ""
	@echo "  ── Run directly ON the Raspberry Pi ───────────────────────────"
	@echo "  make install   full local setup: deps + RF24 driver + service"
	@echo ""
	@echo "  ── Service management ──────────────────────────────────────────"
	@echo "  make logs      tail live service logs"
	@echo "  make restart   restart the service"
	@echo "  make stop      stop the service"
	@echo "  make status    show service status"
	@echo "  make shell     open an SSH shell on the Pi"
	@echo ""
	@echo "  Override target:  make deploy PI=pi@192.168.1.100"
	@echo ""

# ── Sync ──────────────────────────────────────────────────────────────────────
# Push raspi/ to the Pi.  uv.lock IS included so `uv sync --frozen` works.
# -e ssh is required – macOS ships with rsync 2.6.9 which doesn't default to SSH.

sync:
	ssh $(PI) "mkdir -p $(PI_DIR)"
	rsync -avz --progress -e ssh \
		--exclude '__pycache__/' \
		--exclude '*.pyc' \
		--exclude '.git/' \
		--exclude '.python-version' \
		--exclude 'firebase-key.json' \
		--exclude 'config.txt' \
		--exclude '.venv/' \
		--exclude 'vendor/' \
		raspi/ $(PI):$(PI_DIR)/
	@echo ""
	@echo "⚠  Remember to copy firebase-key.json if it changed:"
	@echo "   scp raspi/firebase-key.json $(PI):$(PI_DIR)/"

# ── First-time setup (from your laptop, no manual Pi login required) ──────────
#
#   make firstrun
#
# Runs three idempotent steps in order; each can be re-run individually
# if interrupted (e.g. RF24 build timeout → just re-run `make rf24`).

firstrun: sync
	@echo ""
	@echo "━━━  Step 1 / 3 – bootstrap (uv, deps, groups, config)  ━━━"
	$(REMOTE) "PI_DIR='$(PI_DIR)'; cd $(PI_DIR) && bash setup.sh"
	@echo ""
	@echo "━━━  Step 2 / 3 – RF24 driver (wheel or source build ~15 min)  ━━━"
	$(REMOTE) "PI_DIR='$(PI_DIR)'; cd $(PI_DIR) && bash scripts/install-rf24.sh"
	@echo ""
	@echo "━━━  Step 3 / 3 – systemd service  ━━━"
	$(REMOTE) "PI_DIR='$(PI_DIR)'; cd $(PI_DIR) && bash scripts/install-service.sh $(SERVICE)"
	@echo ""
	@echo "✓ First-time setup complete."
	@echo "  If SPI was just enabled, reboot the Pi and the service starts automatically:"
	@echo "    make restart-pi"
	@echo ""

# ── Day-to-day deploy ─────────────────────────────────────────────────────────

deploy: sync
	$(REMOTE) 'cd $(PI_DIR) && uv sync'
	ssh $(SSHOPTS) $(PI) "sudo systemctl restart $(SERVICE) 2>/dev/null || true"
	@echo "✓ Deployed and restarted."

# ── Individual setup steps (all idempotent, safe to re-run) ──────────────────

rf24:
	$(REMOTE) 'cd $(PI_DIR) && bash scripts/install-rf24.sh'

service:
	$(REMOTE) "PI_DIR='$(PI_DIR)'; cd $(PI_DIR) && bash scripts/install-service.sh $(SERVICE)"
	@echo "✓ Service installed and started."

# ── On-Pi install (run directly on the Raspberry Pi) ─────────────────────────
#
#   cd ~/talksig && make install
#
# Equivalent to `make firstrun` but runs locally instead of over SSH.

install:
	bash setup.sh
	bash scripts/install-rf24.sh
	bash scripts/install-service.sh $(SERVICE)
	@echo ""
	@echo "✓ $(SERVICE) installed and started."
	@echo ""

# ── Service management ────────────────────────────────────────────────────────

logs:
	ssh $(SSHOPTS) $(PI) "journalctl -u $(SERVICE) -f --output=cat"

restart:
	ssh $(SSHOPTS) $(PI) "sudo systemctl restart $(SERVICE)"

restart-pi:
	ssh $(SSHOPTS) $(PI) "sudo reboot"

stop:
	ssh $(SSHOPTS) $(PI) "sudo systemctl stop $(SERVICE)"

status:
	ssh $(SSHOPTS) $(PI) "sudo systemctl status $(SERVICE)"

shell:
	ssh $(PI)
