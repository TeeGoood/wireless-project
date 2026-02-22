"""
High-level RF24 manager – state machine for car-to-car communication.

Architecture
------------
  The manager runs RF24 I/O in a daemon thread (RF24 is blocking).
  It communicates with the async FastAPI layer via an asyncio.Queue
  so the WebSocket handler can ``await`` events without blocking.

Connection state machine
------------------------

  IDLE ──scan──► SCANNING ──(beacon from unknown car)──► SCANNING
                             (user calls connect)──────► CONNECTING
                                                             │
  IDLE ◄──(CONN_REJECT rx)──────────────────────────────────┘
  CONNECTED ◄──(CONN_ACCEPT rx)─────────────────────────────┘

  IDLE ──(CONN_REQUEST rx)──► PENDING_ACCEPT
  CONNECTED ◄──(user accepts)─────────────────┘
  IDLE ◄──(user rejects)──────────────────────┘

Event types emitted to the UI
------------------------------
  init               Snapshot of state on WS connect (sent by server, not here)
  scanStarted        Scan mode activated
  carDiscovered      New car spotted on broadcast channel
  carInfoUpdated     Full metadata received from a discovered car
  infoUpdated        Own car metadata was changed
  connectionRequest  Remote car wants to connect
  connectionAccepted Connection is live (sent to both initiator and acceptor)
  connectionRejected Remote car rejected our connection request
  disconnected       Active connection torn down
  messageReceived    text / sound / honk / ping / pong from peer
  error              Something went wrong
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from enum import Enum
from typing import Optional

from .config import read_config, write_config
from .driver import RF24Driver, make_car_id
from .protocol import (
    MsgType,
    RFPacket,
    decode,
    make_beacon,
    make_conn_accept,
    make_conn_close,
    make_conn_reject,
    make_conn_request,
    make_honk,
    make_info,
    make_ping,
    make_pong,
    make_sound,
    make_text,
    parse_beacon,
    parse_info,
    parse_ping_seq,
    parse_sound,
    parse_text,
)

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    IDLE           = "idle"
    SCANNING       = "scanning"
    PENDING_ACCEPT = "pending_accept"  # Got CONN_REQUEST; waiting for user
    CONNECTING     = "connecting"      # Sent CONN_REQUEST; waiting for CONN_ACCEPT
    CONNECTED      = "connected"


class RF24Manager:
    """Coordinates RF24 radio, car metadata, and WebSocket event delivery."""

    BEACON_INTERVAL = 2.0   # seconds between periodic beacons while scanning
    PING_TIMEOUT    = 5.0   # seconds after which an unanswered ping is forgotten

    def __init__(self) -> None:
        self._config: dict[str, str] = {}
        self._car_id: bytes = b"\x00" * 5

        self._driver: Optional[RF24Driver] = None
        self._state = ConnectionState.IDLE
        self._state_lock = threading.Lock()

        # Discovered cars: hex_car_id → {plate, color, model, owner, ...}
        self._nearby: dict[str, dict] = {}

        # The single active peer (hex car_id string)
        self._peer: Optional[str] = None

        # Ping tracking
        self._ping_seq: int = 0
        self._ping_sent_at: float = 0.0

        # asyncio integration (set in start())
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._event_queue: Optional[asyncio.Queue] = None

        # Beacon timer
        self._beacon_timer: Optional[threading.Timer] = None

    # ── Startup / Shutdown ────────────────────────────────────────────────────

    def start(
        self,
        loop: asyncio.AbstractEventLoop,
        event_queue: asyncio.Queue,
    ) -> None:
        self._loop = loop
        self._event_queue = event_queue
        self._reload_config()

        self._driver = RF24Driver(
            car_id=self._car_id,
            on_receive=self._on_raw_receive,
        )
        self._driver.start()
        logger.info("RF24Manager started | car_id=%s", self._car_id.hex())

    def stop(self) -> None:
        self._stop_beacon_timer()
        if self._driver:
            self._driver.stop()

    # ── Config ────────────────────────────────────────────────────────────────

    def _reload_config(self) -> None:
        self._config = read_config()
        self._car_id = make_car_id(self._config["plate"])

    def handle_change_info(self, payload: dict) -> None:
        """Write new car metadata to config.txt and hot-reload the RF24 address."""
        valid = {k: str(v) for k, v in payload.items() if k in ("color", "plate", "model", "owner")}
        write_config(valid)
        self._reload_config()
        if self._driver:
            self._driver.update_car_id(self._car_id)
        self._emit("infoUpdated", self.get_info())

    def get_info(self) -> dict:
        return {**self._config, "car_id": self._car_id.hex()}

    def get_nearby(self) -> list[dict]:
        return [{"car_id": cid, **info} for cid, info in self._nearby.items()]

    def get_state(self) -> str:
        return self._state.value

    # ── Scanning / Beaconing ──────────────────────────────────────────────────

    def handle_scan(self) -> None:
        """Start broadcasting beacons and collecting nearby cars."""
        with self._state_lock:
            self._state = ConnectionState.SCANNING
        self._nearby.clear()
        self._emit("scanStarted", {})
        self._send_beacon()
        self._schedule_beacon()
        logger.info("Scan started")

    def handle_beacon(self) -> None:
        """Send a single one-shot beacon without entering scan mode."""
        self._send_beacon()

    def _send_beacon(self) -> None:
        if not self._driver:
            return
        pkt = make_beacon(self._car_id, self._config.get("plate", "?"))
        self._driver.broadcast(pkt)
        logger.debug("Beacon broadcast")

    def _schedule_beacon(self) -> None:
        with self._state_lock:
            if self._state != ConnectionState.SCANNING:
                return
        self._beacon_timer = threading.Timer(self.BEACON_INTERVAL, self._beacon_tick)
        self._beacon_timer.daemon = True
        self._beacon_timer.start()

    def _beacon_tick(self) -> None:
        self._send_beacon()
        self._schedule_beacon()

    def _stop_beacon_timer(self) -> None:
        if self._beacon_timer:
            self._beacon_timer.cancel()
            self._beacon_timer = None

    # ── Connection ────────────────────────────────────────────────────────────

    def handle_connect(self, car_id_hex: str) -> None:
        """Initiate a connection request to a discovered car."""
        if not car_id_hex:
            self._emit("error", {"message": "car_id is required"})
            return
        if car_id_hex not in self._nearby:
            self._emit("error", {"message": f"Car {car_id_hex} not in scan results. Run scan first."})
            return
        with self._state_lock:
            if self._state == ConnectionState.CONNECTED:
                self._emit("error", {"message": "Already connected. Disconnect first."})
                return
            self._state = ConnectionState.CONNECTING
        self._peer = car_id_hex
        self._stop_beacon_timer()
        pkt = make_conn_request(self._car_id)
        self._driver.send(bytes.fromhex(car_id_hex), pkt)
        logger.info("CONN_REQUEST sent → %s", car_id_hex)

    def handle_accept_connection(self, car_id_hex: str) -> None:
        """Accept a pending incoming connection request."""
        with self._state_lock:
            if self._state != ConnectionState.PENDING_ACCEPT:
                self._emit("error", {"message": "No pending connection to accept"})
                return
            self._state = ConnectionState.CONNECTED
        self._peer = car_id_hex

        pkt = make_conn_accept(self._car_id)
        self._driver.send(bytes.fromhex(car_id_hex), pkt)

        # Exchange full metadata with the new peer
        self._send_info_to(bytes.fromhex(car_id_hex))

        self._emit("connectionAccepted", {"car_id": car_id_hex})
        logger.info("Connection accepted ↔ %s", car_id_hex)

    def handle_reject_connection(self, car_id_hex: str) -> None:
        """Reject a pending incoming connection request."""
        with self._state_lock:
            self._state = ConnectionState.IDLE
        self._peer = None

        pkt = make_conn_reject(self._car_id)
        self._driver.send(bytes.fromhex(car_id_hex), pkt)
        self._emit("connectionRejected", {"car_id": car_id_hex})
        logger.info("Connection rejected ← %s", car_id_hex)

    def handle_disconnect(self) -> None:
        """Cancel a pending connection request or tear down an active connection.

        Works from both CONNECTING and CONNECTED states:
          CONNECTING → sends CONN_REJECT so the remote car knows the attempt
                       is cancelled before it has a chance to accept.
          CONNECTED  → sends CONN_CLOSE as before.

        This prevents the race where Car B accepts after Car A already gave up,
        leaving Car B thinking it is connected and free to send messages.
        """
        with self._state_lock:
            state = self._state
            peer  = self._peer
            if state not in (ConnectionState.CONNECTING, ConnectionState.CONNECTED):
                return
            self._state = ConnectionState.IDLE
        self._peer = None

        if peer and self._driver:
            if state == ConnectionState.CONNECTED:
                self._driver.send(bytes.fromhex(peer), make_conn_close(self._car_id))
            else:  # CONNECTING – cancel before the other side has accepted
                self._driver.send(bytes.fromhex(peer), make_conn_reject(self._car_id))

        self._emit("disconnected", {})

    # ── Messaging (requires active connection) ────────────────────────────────

    def handle_send_text(self, text: str) -> None:
        if not self._assert_connected():
            return
        pkt = make_text(self._car_id, text[:26])
        self._driver.send(bytes.fromhex(self._peer), pkt)

    def handle_send_sound(self, sound_id: int) -> None:
        if not self._assert_connected():
            return
        pkt = make_sound(self._car_id, sound_id)
        self._driver.send(bytes.fromhex(self._peer), pkt)

    def handle_send_honk(self) -> None:
        if not self._assert_connected():
            return
        pkt = make_honk(self._car_id)
        self._driver.send(bytes.fromhex(self._peer), pkt)

    def handle_send_ping(self) -> None:
        if not self._assert_connected():
            return
        self._ping_seq = (self._ping_seq + 1) % 0xFFFF
        self._ping_sent_at = time.monotonic()
        pkt = make_ping(self._car_id, self._ping_seq)
        self._driver.send(bytes.fromhex(self._peer), pkt)

    def _assert_connected(self) -> bool:
        with self._state_lock:
            ok = self._state == ConnectionState.CONNECTED
        if not ok:
            self._emit("error", {"message": "Not connected to any car"})
        return ok

    # ── Raw receive dispatch ──────────────────────────────────────────────────

    def _on_raw_receive(self, raw: bytes) -> None:
        """Called from the RF24 receive thread for every incoming packet."""
        pkt = decode(raw)
        if not pkt:
            return

        from_hex = pkt.from_id.hex()
        t = pkt.msg_type

        # Discard our own transmissions if the radio echoes them back
        if from_hex == self._car_id.hex():
            return

        dispatch = {
            MsgType.BEACON:       lambda: self._rx_beacon(from_hex, pkt),
            MsgType.CONN_REQUEST: lambda: self._rx_conn_request(from_hex),
            MsgType.CONN_ACCEPT:  lambda: self._rx_conn_accept(from_hex),
            MsgType.CONN_REJECT:  lambda: self._rx_conn_reject(from_hex),
            MsgType.CONN_CLOSE:   lambda: self._rx_conn_close(from_hex),
            MsgType.INFO:         lambda: self._rx_info(from_hex, pkt),
            MsgType.PING:         lambda: self._rx_ping(from_hex, pkt),
            MsgType.PONG:         lambda: self._rx_pong(from_hex, pkt),
            MsgType.TEXT:         lambda: self._rx_message(from_hex, "text", parse_text(pkt)),
            MsgType.SOUND:        lambda: self._rx_message(from_hex, "sound", parse_sound(pkt)),
            MsgType.HONK:         lambda: self._rx_message(from_hex, "honk", {}),
        }

        handler = dispatch.get(t)
        if handler:
            handler()

    # ── Receive handlers ──────────────────────────────────────────────────────

    def _rx_beacon(self, from_hex: str, pkt: RFPacket) -> None:
        info = parse_beacon(pkt)
        if from_hex not in self._nearby:
            self._nearby[from_hex] = info
            self._emit("carDiscovered", {"car_id": from_hex, **info})
            logger.info("Discovered car %s (plate=%s)", from_hex, info.get("plate"))
        else:
            self._nearby[from_hex].update(info)

    def _rx_conn_request(self, from_hex: str) -> None:
        with self._state_lock:
            if self._state not in (ConnectionState.IDLE, ConnectionState.SCANNING):
                # Already busy – auto-reject
                self._driver.send(
                    bytes.fromhex(from_hex),
                    make_conn_reject(self._car_id),
                )
                return
            self._state = ConnectionState.PENDING_ACCEPT
        self._stop_beacon_timer()
        info = self._nearby.get(from_hex, {})
        self._emit("connectionRequest", {
            "car_id": from_hex,
            "plate": info.get("plate", from_hex),
        })
        logger.info("CONN_REQUEST received ← %s", from_hex)

    def _rx_conn_accept(self, from_hex: str) -> None:
        with self._state_lock:
            if self._state != ConnectionState.CONNECTING or self._peer != from_hex:
                return
            self._state = ConnectionState.CONNECTED

        # Exchange full metadata now that the connection is live
        self._send_info_to(bytes.fromhex(from_hex))

        self._emit("connectionAccepted", {"car_id": from_hex})
        logger.info("Connection accepted ↔ %s", from_hex)

    def _rx_conn_reject(self, from_hex: str) -> None:
        # Determine which event to raise before releasing the lock.
        event = None
        with self._state_lock:
            if self._peer != from_hex:
                return
            if self._state == ConnectionState.CONNECTING:
                # Normal rejection: remote declined our request.
                event = "connectionRejected"
                self._state = ConnectionState.IDLE
            elif self._state == ConnectionState.CONNECTED:
                # Race condition: we accepted, but the initiator cancelled
                # before our CONN_ACCEPT arrived.  Treat it like a close.
                event = "peerDisconnected"
                self._state = ConnectionState.IDLE
        if event is None:
            return
        self._peer = None
        self._emit(event, {"car_id": from_hex})
        logger.info("CONN_REJECT received ← %s (raised: %s)", from_hex, event)

    def _rx_conn_close(self, from_hex: str) -> None:
        with self._state_lock:
            if self._peer != from_hex:
                return  # Not our current peer – ignore stale packet
            self._state = ConnectionState.IDLE
        self._peer = None
        self._emit("peerDisconnected", {"car_id": from_hex})
        logger.info("Peer disconnected ← %s", from_hex)

    def _rx_info(self, from_hex: str, pkt: RFPacket) -> None:
        info = parse_info(pkt)
        if from_hex not in self._nearby:
            self._nearby[from_hex] = {}
        self._nearby[from_hex].update(info)
        self._emit("carInfoUpdated", {"car_id": from_hex, **self._nearby[from_hex]})

    def _rx_ping(self, from_hex: str, pkt: RFPacket) -> None:
        if not self._is_from_peer(from_hex):
            return  # Don't pong strangers – prevents unsolicited ping floods
        seq = parse_ping_seq(pkt)
        self._driver.send(bytes.fromhex(from_hex), make_pong(self._car_id, seq))
        self._emit("messageReceived", {"car_id": from_hex, "kind": "ping"})

    def _rx_pong(self, from_hex: str, pkt: RFPacket) -> None:
        if not self._is_from_peer(from_hex):
            return
        seq = parse_ping_seq(pkt)
        if seq == self._ping_seq and self._ping_sent_at:
            latency_ms = int((time.monotonic() - self._ping_sent_at) * 1000)
            self._ping_sent_at = 0.0
            self._emit("messageReceived", {
                "car_id": from_hex,
                "kind": "pong",
                "latency_ms": latency_ms,
            })

    def _rx_message(self, from_hex: str, kind: str, extra: dict) -> None:
        if not self._is_from_peer(from_hex):
            return  # Silently drop messages from non-peers
        self._emit("messageReceived", {"car_id": from_hex, "kind": kind, **extra})

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _is_from_peer(self, from_hex: str) -> bool:
        """Return True only if the sender is our active, connected peer.

        Used to gate all message handlers so that a car which holds a stale
        CONN_ACCEPT (because we cancelled mid-handshake) cannot deliver
        messages, pings, or honks to us.
        """
        with self._state_lock:
            return (
                self._state == ConnectionState.CONNECTED
                and self._peer == from_hex
            )

    def _send_info_to(self, target: bytes) -> None:
        """Push all four metadata fields to the target car."""
        fields = [
            (0, self._config.get("color", "")),
            (1, self._config.get("plate", "")),
            (2, self._config.get("model", "")),
            (3, self._config.get("owner", "")),
        ]
        for field_id, value in fields:
            pkt = make_info(self._car_id, field_id, value)
            self._driver.send(target, pkt)

    def _emit(self, event_type: str, payload: dict) -> None:
        """Thread-safe push of an event into the asyncio queue."""
        if self._loop and self._event_queue:
            self._loop.call_soon_threadsafe(
                self._event_queue.put_nowait,
                {"type": event_type, "payload": payload},
            )
