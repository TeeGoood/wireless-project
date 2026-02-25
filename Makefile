# ── Deployment config (override on the CLI: make deploy PI=pi@192.168.1.10) ──
# NOTE: never put inline comments after variable assignments in Make –
#       spaces before # become part of the value and break commands.
PI      ?= pi@raspberrypi.local
PI_DIR  ?= ~/talksig
SERVICE ?= talksig

# ── Local shortcuts ───────────────────────────────────────────────────────────

.PHONY: help sync deploy service install logs restart stop status shell

help:
	@echo ""
	@echo "  ── From your laptop (deploys to Pi over SSH) ──────────────────"
	@echo "  make sync      rsync source files to the Pi (no restart)"
	@echo "  make deploy    sync + install deps + restart service"
	@echo "  make service   install / enable the systemd service (first time)"
	@echo ""
	@echo "  ── Run directly ON the Raspberry Pi ───────────────────────────"
	@echo "  make install   bootstrap deps + install + enable systemd service"
	@echo ""
	@echo "  ── Remote helpers (SSH) ────────────────────────────────────────"
	@echo "  make logs      tail live service logs"
	@echo "  make restart   restart the service on the Pi"
	@echo "  make stop      stop the service on the Pi"
	@echo "  make status    show service status"
	@echo "  make shell     open an SSH shell on the Pi"
	@echo ""
	@echo "  Override Pi target:  make deploy PI=pi@192.168.1.100"
	@echo ""

# Sync source files to the Pi (skips secrets, caches, git history)
# -e ssh is required – macOS ships with rsync 2.6.9 which doesn't default to SSH
sync:
	ssh $(PI) "mkdir -p $(PI_DIR)"
	rsync -avz --progress -e ssh \
		--exclude '__pycache__/' \
		--exclude '*.pyc' \
		--exclude '.git/' \
		--exclude '.python-version' \
		--exclude 'firebase-key.json' \
		--exclude 'uv.lock' \
		--exclude '*/config.txt' \
		raspi/ $(PI):$(PI_DIR)/
	@echo ""
	@echo "⚠  Remember to copy firebase-key.json manually if it changed:"
	@echo "   scp raspi/firebase-key.json $(PI):$(PI_DIR)/"

# Full deploy: sync → install deps → restart
deploy: sync
	ssh $(PI) "cd $(PI_DIR) && uv sync --frozen"
	ssh $(PI) "sudo systemctl restart $(SERVICE) 2>/dev/null || true"
	@echo "✓ Deployed and restarted."

# Install the systemd service (run from your laptop via SSH)
service:
	ssh $(PI) "cd $(PI_DIR) && \
		_user=\$$(whoami) && \
		_uv=\$$(which uv 2>/dev/null || echo \$$HOME/.local/bin/uv) && \
		sed \
			-e 's|{{PI_DIR}}|$(PI_DIR)|g' \
			-e \"s|{{USER}}|\$$_user|g\" \
			-e \"s|{{UV_BIN}}|\$$_uv|g\" \
			talksig.service \
			| sudo tee /etc/systemd/system/$(SERVICE).service > /dev/null \
		&& sudo systemctl daemon-reload \
		&& sudo systemctl enable --now $(SERVICE)"
	@echo "✓ Service enabled and started."

# ── On-Pi install (run this directly on the Raspberry Pi) ────────────────────
#
#   cd ~/talksig && make install
#
install:
	bash setup.sh
	sed \
		-e 's|{{PI_DIR}}|$(CURDIR)|g' \
		-e 's|{{USER}}|$(shell whoami)|g' \
		-e 's|{{UV_BIN}}|$(shell which uv 2>/dev/null || echo $(HOME)/.local/bin/uv)|g' \
		talksig.service \
		| sudo tee /etc/systemd/system/$(SERVICE).service > /dev/null
	sudo systemctl daemon-reload
	sudo systemctl enable --now $(SERVICE)
	@echo ""
	@echo "✓ $(SERVICE) installed and started."
	@echo "  Logs:    journalctl -u $(SERVICE) -f"
	@echo "  Status:  systemctl status $(SERVICE)"
	@echo ""

# ── Remote helpers ────────────────────────────────────────────────────────────

logs:
	ssh $(PI) "journalctl -u $(SERVICE) -f --output=cat"

restart:
	ssh $(PI) "sudo systemctl restart $(SERVICE)"

stop:
	ssh $(PI) "sudo systemctl stop $(SERVICE)"

status:
	ssh $(PI) "sudo systemctl status $(SERVICE)"

shell:
	ssh $(PI)
