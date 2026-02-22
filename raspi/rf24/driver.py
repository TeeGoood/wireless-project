"""
Low-level nRF24L01+ hardware abstraction.

Raspberry Pi wiring (BCM numbering)
-------------------------------------
  nRF24 VCC  → 3.3 V  (pin 1 or 17)
  nRF24 GND  → GND    (pin 6, 9, 14, 20, 25, 30, 34, or 39)
  nRF24 CE   → GPIO 25  (pin 22)   ← CE_PIN
  nRF24 CSN  → GPIO 8   (pin 24)   ← SPI CE0  (CSN_PIN = 0)
  nRF24 SCK  → GPIO 11  (pin 23)   ← SPI0 CLK
  nRF24 MOSI → GPIO 10  (pin 19)   ← SPI0 MOSI
  nRF24 MISO → GPIO 9   (pin 21)   ← SPI0 MISO

Channel and address
-------------------------------------
  All cars share CHANNEL 76 and BROADCAST_ADDRESS for beacons.
  Each car also listens on its own unique 5-byte address (derived from
  the MD5 hash of its license plate) for direct / peer messages.

Mock mode
-------------------------------------
  If the RF24 library is not installed the driver runs in mock mode:
  sends are logged only, receives never fire.  Useful for local dev.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ── Import RF24 library (graceful fallback) ───────────────────────────────────

try:
    from RF24 import RF24, RF24_PA_HIGH, RF24_1MBPS  # type: ignore[import]

    _RF24_AVAILABLE = True
except ImportError:
    logger.warning(
        "RF24 library not found – running in MOCK mode. "
        "Install pyrf24 or the RF24 Python bindings on the Raspberry Pi."
    )
    _RF24_AVAILABLE = False

# ── Constants ─────────────────────────────────────────────────────────────────

BROADCAST_ADDRESS: bytes = b"\xe7\xe7\xe7\xe7\xe7"  # shared beacon channel
CE_PIN: int = 25  # BCM GPIO 25
CSN_PIN: int = 0  # SPI CE0  (/dev/spidev0.0)
CHANNEL: int = 76  # RF channel (0-125 MHz offset from 2.4 GHz)
PAYLOAD_SIZE: int = 32


def make_car_id(plate: str) -> bytes:
    """Derive a stable, unique 5-byte RF24 address from the license plate."""
    return hashlib.md5(plate.encode(), usedforsecurity=False).digest()[:5]


# ── Driver ────────────────────────────────────────────────────────────────────


class RF24Driver:
    """Wraps the RF24 radio in a background receive thread.

    The caller supplies an ``on_receive`` callback that is invoked from the
    receive thread whenever a 32-byte packet arrives.  The callback must be
    thread-safe (it will be called outside the asyncio event loop).

    Transmits are done synchronously via ``send()`` / ``broadcast()``.
    The driver holds a lock while touching the radio to serialise TX and RX.

    Pipe layout
    -----------
      Pipe 0 → car_id              (direct P2P channel – full 5-byte address,
                                    no MSB-sharing constraint with Pipe 1)
      Pipe 1 → BROADCAST_ADDRESS   (shared beacon channel – all cars listen)

    WHY Pipe 0, not Pipe 2:
      nRF24L01 pipes 2-5 share the upper 4 bytes of their address with Pipe 1
      and only their LSB is individually programmable.  Using an arbitrary
      MD5-derived address on Pipe 2 means the chip silently ignores the upper
      4 bytes – the car ends up listening on a completely different address
      than the one it advertised, so directed packets never arrive.
      Pipe 0 has a fully independent 5-byte address.  The RF24 library also
      caches the Pipe 0 address set via openReadingPipe(0, ...) and restores
      it automatically on every startListening() call, so the standard
      stopListening → openWritingPipe → write → startListening TX sequence
      in send() correctly puts Pipe 0 back without any extra steps.
    """

    def __init__(self, car_id: bytes, on_receive: Callable[[bytes], None]) -> None:
        assert len(car_id) == 5, "car_id must be 5 bytes"
        self._car_id = car_id
        self._on_receive = on_receive
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._radio = RF24(CE_PIN, CSN_PIN) if _RF24_AVAILABLE else None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if _RF24_AVAILABLE:
            self._init_radio()
        self._running = True
        self._thread = threading.Thread(
            target=self._receive_loop, name="rf24-rx", daemon=True
        )
        self._thread.start()
        logger.info(
            "RF24Driver started | car_id=%s | mock=%s",
            self._car_id.hex(),
            not _RF24_AVAILABLE,
        )

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._radio:
            self._radio.stopListening()
        logger.info("RF24Driver stopped")

    # ── Radio init ────────────────────────────────────────────────────────────

    def _init_radio(self) -> None:
        r = self._radio
        if not r.begin():
            raise RuntimeError("RF24 radio hardware not responding. Check wiring.")
        r.setPayloadSize(PAYLOAD_SIZE)
        r.setChannel(CHANNEL)
        r.setPALevel(RF24_PA_HIGH)
        r.setDataRate(RF24_1MBPS)
        r.setAutoAck(False)  # Manual ACK – broadcast-compatible

        # Pipe 0: this car's unique direct address (full 5-byte, no MSB constraint).
        # openReadingPipe(0, ...) caches the address internally so that
        # startListening() restores it after every openWritingPipe() call.
        r.openReadingPipe(0, self._car_id)
        # Pipe 1: shared broadcast / beacon address (all cars listen here)
        r.openReadingPipe(1, BROADCAST_ADDRESS)

        r.startListening()
        logger.info("RF24 radio initialised | channel=%d", CHANNEL)

    # ── Receive loop ──────────────────────────────────────────────────────────

    def _receive_loop(self) -> None:
        while self._running:
            if _RF24_AVAILABLE:
                self._poll_radio()
            time.sleep(0.01)  # 10 ms polling interval

    def _poll_radio(self) -> None:
        # Read outside the lock so send() can acquire it without deadlocking.
        raw: Optional[bytes] = None
        with self._lock:
            r = self._radio
            if r.available():
                raw = bytes(r.read(PAYLOAD_SIZE))
        if raw:
            self._on_receive(raw)

    # ── Transmit ──────────────────────────────────────────────────────────────

    def send(self, address: bytes, payload: bytes) -> bool:
        """Send a 32-byte payload to a specific 5-byte address.

        Temporarily stops listening, transmits, then resumes listening.
        Returns True on success, False on radio failure.
        """
        assert len(address) == 5, "address must be 5 bytes"
        assert len(payload) == PAYLOAD_SIZE, f"payload must be {PAYLOAD_SIZE} bytes"

        if not _RF24_AVAILABLE:
            logger.debug("MOCK TX → %s : %s", address.hex(), payload.hex())
            return True

        with self._lock:
            r = self._radio
            r.stopListening()
            r.openWritingPipe(address)
            ok = r.write(payload)
            # Restore listening state (reading pipes are remembered by the library)
            r.startListening()

        if not ok:
            logger.warning("TX failed → %s", address.hex())
        return ok

    def broadcast(self, payload: bytes) -> bool:
        """Send a payload on the shared broadcast channel."""
        return self.send(BROADCAST_ADDRESS, payload)

    # ── Dynamic address update ────────────────────────────────────────────────

    def update_car_id(self, car_id: bytes) -> None:
        """Hot-swap the P2P reading pipe when the plate (and thus ID) changes."""
        assert len(car_id) == 5
        self._car_id = car_id
        if _RF24_AVAILABLE:
            with self._lock:
                r = self._radio
                r.stopListening()
                # Re-open Pipe 0 to update both the hardware register and the
                # library's internal cache used by startListening().
                r.openReadingPipe(0, car_id)
                r.startListening()
        logger.info("RF24 P2P address updated → %s", car_id.hex())
