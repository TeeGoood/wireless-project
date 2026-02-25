PI      ?= pi@raspberrypi.local
PI_DIR  ?= ~/talksig
SERVICE ?= talksig

# Login shell so ~/.profile is sourced and uv is on PATH.
# Keepalive prevents the connection dropping during the RF24 build (~15 min).
SSHOPTS := -o ServerAliveInterval=60 -o ServerAliveCountMax=30
REMOTE  := ssh $(SSHOPTS) $(PI) bash -lc

# Prepend ~/.local/bin (where uv lives) before every remote command.
# Needed the first time (uv just installed, ~/.profile not yet re-sourced)
# and as a safety net on all subsequent calls.
UV_PATH := export PATH="$$HOME/.local/bin:$$PATH";

.PHONY: help sync deploy base rf24 service firstrun logs restart testkit shell status

# ── Help ──────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  ── First-time setup (run each step or all at once) ────────────"
	@echo "  make sync      push source files to the Pi"
	@echo "  make base      system setup: uv, spi, gpio groups"
	@echo "  make rf24      build RF24 Python driver  (~15 min)"
	@echo "  make service   install / refresh the systemd service"
	@echo ""
	@echo "  make firstrun  all four steps above in order"
	@echo ""
	@echo "  ── Day-to-day ─────────────────────────────────────────────────"
	@echo "  make deploy    sync + install deps + restart service"
	@echo "  make logs      tail live service logs"
	@echo "  make restart   restart the service"
	@echo "  make status    show service status"
	@echo "  make testkit   run the interactive testkit on the Pi"
	@echo "  make shell     open an SSH shell on the Pi"
	@echo ""
	@echo "  Override Pi:   make deploy PI=pi@192.168.1.100"
	@echo ""

# ── Sync ──────────────────────────────────────────────────────────────────────

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

# ── First-time setup steps (all idempotent – safe to re-run individually) ────

base: sync
	$(REMOTE) "$(UV_PATH) bash $(PI_DIR)/setup.sh"
	$(REMOTE) "grep -qF '.local/bin' ~/.profile || echo 'export PATH=\"\$$HOME/.local/bin:\$$PATH\"' >> ~/.profile"

rf24:
	$(REMOTE) "$(UV_PATH) bash $(PI_DIR)/scripts/install-rf24.sh"

service:
	$(REMOTE) "$(UV_PATH) bash $(PI_DIR)/scripts/install-service.sh $(SERVICE)"

# ── firstrun: all steps in order, each independently resumable ────────────────
#
#   make firstrun           – full first-time setup
#   make base               – re-run just the system bootstrap
#   make rf24               – re-run just the RF24 build (e.g. after a timeout)
#   make service            – re-install just the systemd service

firstrun: base rf24 service
	@echo ""
	@echo "✓ First-time setup complete."
	@echo "  Start or check the service:"
	@echo "    make logs"
	@echo ""

# ── Day-to-day ────────────────────────────────────────────────────────────────

deploy: sync
	$(REMOTE) "$(UV_PATH) uv --directory $(PI_DIR) sync --inexact"
	ssh $(SSHOPTS) $(PI) "sudo systemctl restart $(SERVICE) 2>/dev/null || true"
	@echo "✓ Deployed and restarted."

logs:
	ssh $(SSHOPTS) $(PI) "journalctl -u $(SERVICE) -f --output=cat"

restart:
	ssh $(SSHOPTS) $(PI) "sudo systemctl restart $(SERVICE)"

testkit:
	ssh $(SSHOPTS) -t $(PI) "$(UV_PATH) uv --directory $(PI_DIR) run python testkit.py"

shell:
	ssh -t $(PI)

status:
	ssh $(SSHOPTS) $(PI) "sudo systemctl status $(SERVICE)"
