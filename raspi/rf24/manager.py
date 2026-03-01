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
  IDLE ◄──(CONN_REJECT rx / timeout)─────────────────────────┘
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
  carExpired         A car was removed after NEARBY_TTL seconds of silence
  infoUpdated        Own car metadata was changed
  connectionRequest  Remote car wants to connect
  connectionAccepted Connection is live (sent to both initiator and acceptor)
  connectionRejected Remote car rejected our connection request
  connectionCancelled Initiator withdrew the request before we decided
  disconnected       Active connection torn down (we initiated)
  peerDisconnected   Peer went away (CONN_CLOSE, heartbeat timeout, or cancel)
  messageReceived    text / sound / honk / ping / pong from peer
  messageFailed      A message could not be delivered (TX failure)
  error              Something went wrong
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
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
    parse_conn_nonce,
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

    BEACON_INTERVAL    = 1.0   # base seconds between periodic beacons
    BEACON_JITTER      = 0.5   # max random seconds added to each beacon interval
    NEARBY_TTL         = 5.0   # seconds of silence before a car is removed from nearby
    NEARBY_PRUNE_EVERY = 2.5   # how often the TTL pruner runs (NEARBY_TTL / 2)
    HEARTBEAT_INTERVAL = 3.0   # seconds between keepalive pings while connected
    HEARTBEAT_TIMEOUT  = 9.0   # seconds without a pong → declare peer lost
    CONN_TIMEOUT       = 10.0  # seconds to wait for CONN_ACCEPT before giving up

    def __init__(self) -> None:
        self._config: dict[str, str] = {}
        self._car_id: bytes = b"\x00" * 5

        self._driver: Optional[RF24Driver] = None
        self._state = ConnectionState.IDLE
        self._state_lock = threading.Lock()
        self._nearby_lock = threading.Lock()

        # Discovered cars: hex_car_id → {plate, color, model, owner, _seen_at}
        # _seen_at is an internal float (time.monotonic) used for TTL pruning.
        self._nearby: dict[str, dict] = {}

        # The single active peer (hex car_id string).
        # Set as soon as a connection is in-flight in either direction:
        #   CONNECTING    → peer we sent CONN_REQUEST to
        #   PENDING_ACCEPT → peer whose CONN_REQUEST we are considering
        #   CONNECTED     → our live peer
        self._peer: Optional[str] = None

        # Nonces for spam / replay prevention.
        # _conn_nonce:  random bytes we put in our outgoing CONN_REQUEST.
        #               Only a CONN_REJECT carrying this exact nonce can
        #               move us out of CONNECTING state.
        # _peer_nonce:  nonce from the CONN_REQUEST we are considering.
        #               Echoed back in our CONN_REJECT / used to verify cancel.
        self._conn_nonce: bytes = b"\x00\x00"
        self._peer_nonce: bytes = b"\x00\x00"

        # Ping tracking (manual user-initiated pings)
        self._ping_seq: int = 0
        self._ping_sent_at: float = 0.0

        # Heartbeat keepalive ping sequence – separate from user pings so that
        # heartbeat pings don't collide with (and corrupt) user ping/pong matching.
        self._hb_seq: int = 0

        # Heartbeat liveness – tracks when the last pong arrived
        self._last_pong_at: float = 0.0

        # asyncio integration (set in start())
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._event_queue: Optional[asyncio.Queue] = None

        # Timers
        self._beacon_timer: Optional[threading.Timer] = None
        self._prune_timer: Optional[threading.Timer] = None
        self._conn_timer: Optional[threading.Timer] = None
        self._pending_timer: Optional[threading.Timer] = None  # PENDING_ACCEPT guard
        self._heartbeat_timer: Optional[threading.Timer] = None

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
        # Always-on presence beacon – makes this car discoverable to others
        # without requiring a manual scan command first.
        self._send_beacon()
        self._schedule_beacon()
        # Always-on nearby pruner – removes out-of-range cars automatically.
        self._start_prune_timer()
        logger.info("RF24Manager started | car_id=%s", self._car_id.hex())

    def stop(self) -> None:
        self._stop_beacon_timer()
        self._stop_prune_timer()
        self._stop_conn_timer()
        self._stop_pending_timer()
        self._stop_heartbeat()
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
        # Strip the internal _seen_at key before returning to callers
        with self._nearby_lock:
            return [
                {"car_id": cid, **{k: v for k, v in info.items() if not k.startswith("_")}}
                for cid, info in self._nearby.items()
            ]

    def get_state(self) -> str:
        return self._state.value

    # ── Scanning / Beaconing ──────────────────────────────────────────────────

    def handle_scan(self) -> None:
        """Start broadcasting beacons and collecting nearby cars.

        Does NOT wipe the existing nearby list.  Stale entries are removed
        by the TTL pruner so a re-scan does not cause a UI flicker where all
        cars temporarily disappear and re-appear.

        The presence beacon is already running (started at server boot), so
        scan mode only needs to enable carDiscovered events and the TTL pruner.
        Re-emits carDiscovered for all cars already in the nearby list so the
        UI is always in sync when scan is called more than once.
        """
        with self._state_lock:
            self._state = ConnectionState.SCANNING
        self._emit("scanStarted", {})
        # Re-announce all currently-known cars so the UI is never out of sync
        # on a repeated scan call.
        with self._nearby_lock:
            existing = [
                {"car_id": cid, **{k: v for k, v in info.items() if not k.startswith("_")}}
                for cid, info in self._nearby.items()
            ]
        for entry in existing:
            self._emit("carDiscovered", entry)
        self._start_prune_timer()
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
        # No state gate – beacon fires in ALL states so this car is always
        # discoverable.  Jitter prevents a fleet from synchronising their
        # transmissions and flooding the broadcast channel simultaneously.
        interval = self.BEACON_INTERVAL + random.uniform(0, self.BEACON_JITTER)
        self._beacon_timer = threading.Timer(interval, self._beacon_tick)
        self._beacon_timer.daemon = True
        self._beacon_timer.start()

    def _beacon_tick(self) -> None:
        self._send_beacon()
        self._schedule_beacon()

    def _stop_beacon_timer(self) -> None:
        if self._beacon_timer:
            self._beacon_timer.cancel()
            self._beacon_timer = None

    # ── Nearby TTL pruner ─────────────────────────────────────────────────────

    def _start_prune_timer(self) -> None:
        self._stop_prune_timer()
        self._prune_timer = threading.Timer(self.NEARBY_PRUNE_EVERY, self._prune_tick)
        self._prune_timer.daemon = True
        self._prune_timer.start()

    def _prune_tick(self) -> None:
        now = time.monotonic()
        with self._nearby_lock:
            expired = [
                cid for cid, info in self._nearby.items()
                if now - info.get("_seen_at", now) > self.NEARBY_TTL
            ]
            for cid in expired:
                del self._nearby[cid]
        for cid in expired:
            self._emit("carExpired", {"car_id": cid})
            logger.info("Car expired (TTL=%.0fs) %s", self.NEARBY_TTL, cid)
        self._start_prune_timer()  # Reschedule

    def _stop_prune_timer(self) -> None:
        if self._prune_timer:
            self._prune_timer.cancel()
            self._prune_timer = None

    # ── Connection ────────────────────────────────────────────────────────────

    def handle_connect(self, car_id_hex: str) -> None:
        """Initiate a connection request to a discovered car."""
        if not car_id_hex:
            self._emit("error", {"message": "car_id is required"})
            return
        with self._nearby_lock:
            in_nearby = car_id_hex in self._nearby
        if not in_nearby:
            self._emit("error", {"message": f"Car {car_id_hex} not in scan results. Run scan first."})
            return
        with self._state_lock:
            if self._state == ConnectionState.CONNECTING and self._peer == car_id_hex:
                self._emit("error", {"message": "Already awaiting response from this car."})
                return
            if self._state in (ConnectionState.CONNECTING, ConnectionState.CONNECTED,
                               ConnectionState.PENDING_ACCEPT):
                self._emit("error", {"message": "Already in a connection. Disconnect first."})
                return
            self._state = ConnectionState.CONNECTING
            self._peer = car_id_hex
            self._conn_nonce = os.urandom(2)

        pkt = make_conn_request(self._car_id, self._conn_nonce)
        ok = self._driver.send(bytes.fromhex(car_id_hex), pkt)
        if not ok:
            # TX failed immediately – the car is likely out of range
            with self._state_lock:
                self._state = ConnectionState.IDLE
                self._peer = None
                self._conn_nonce = b"\x00\x00"
            self._emit("error", {"message": f"Car {car_id_hex} is out of range (TX failed)"})
            return

        # Start a timeout so we don't stay stuck in CONNECTING forever
        self._start_conn_timer()
        logger.info("CONN_REQUEST sent → %s (nonce=%s)", car_id_hex, self._conn_nonce.hex())

    def handle_accept_connection(self, car_id_hex: str) -> None:
        """Accept a pending incoming connection request."""
        with self._state_lock:
            if self._state != ConnectionState.PENDING_ACCEPT:
                self._emit("error", {"message": "No pending connection to accept"})
                return
            self._state = ConnectionState.CONNECTED
            self._peer = car_id_hex
            self._peer_nonce = b"\x00\x00"

        self._stop_pending_timer()
        pkt = make_conn_accept(self._car_id)
        self._driver.send(bytes.fromhex(car_id_hex), pkt)

        # Exchange full metadata with the new peer
        self._send_info_to(bytes.fromhex(car_id_hex))

        self._start_heartbeat()
        self._emit("connectionAccepted", {"car_id": car_id_hex})
        logger.info("Connection accepted ↔ %s", car_id_hex)

    def handle_reject_connection(self, car_id_hex: str) -> None:
        """Reject a pending incoming connection request."""
        with self._state_lock:
            if self._state != ConnectionState.PENDING_ACCEPT:
                return  # Nothing to reject; stale UI event, ignore safely
            peer = self._peer   # Use stored peer (set by _rx_conn_request), not arg
            self._state = ConnectionState.IDLE
            self._peer = None
            nonce, self._peer_nonce = self._peer_nonce, b"\x00\x00"

        self._stop_pending_timer()
        pkt = make_conn_reject(self._car_id, nonce)
        self._driver.send(bytes.fromhex(peer), pkt)
        self._emit("connectionRejected", {"car_id": peer})
        logger.info("Connection rejected ← %s", peer)

    def handle_disconnect(self) -> None:
        """Cancel any in-flight connection state or tear down an active connection.

        Handled states:
          PENDING_ACCEPT → we received a request but haven't responded; sends
                           CONN_REJECT so the initiator can clean up immediately.
          CONNECTING     → we sent a request; sends CONN_REJECT (with our nonce)
                           so the remote car knows the attempt is withdrawn.
          CONNECTED      → sends CONN_CLOSE for a clean teardown.

        IDLE / SCANNING → no-op (nothing to cancel).
        """
        with self._state_lock:
            state = self._state
            peer  = self._peer
            if state == ConnectionState.PENDING_ACCEPT:
                nonce, self._peer_nonce = self._peer_nonce, b"\x00\x00"
                self._conn_nonce = b"\x00\x00"
            elif state in (ConnectionState.CONNECTING, ConnectionState.CONNECTED):
                nonce, self._conn_nonce = self._conn_nonce, b"\x00\x00"
                self._peer_nonce = b"\x00\x00"
            else:
                return  # IDLE / SCANNING – nothing to cancel
            self._state = ConnectionState.IDLE
            self._peer  = None

        self._stop_conn_timer()
        self._stop_pending_timer()
        self._stop_heartbeat()

        if peer and self._driver:
            if state == ConnectionState.CONNECTED:
                self._driver.send(bytes.fromhex(peer), make_conn_close(self._car_id))
            else:  # CONNECTING or PENDING_ACCEPT – both signal cancellation via CONN_REJECT
                self._driver.send(bytes.fromhex(peer), make_conn_reject(self._car_id, nonce))

        self._emit("disconnected", {})

    # ── Connection timeout ────────────────────────────────────────────────────

    def _start_conn_timer(self) -> None:
        self._stop_conn_timer()
        self._conn_timer = threading.Timer(self.CONN_TIMEOUT, self._on_conn_timeout)
        self._conn_timer.daemon = True
        self._conn_timer.start()

    def _stop_conn_timer(self) -> None:
        if self._conn_timer:
            self._conn_timer.cancel()
            self._conn_timer = None

    def _on_conn_timeout(self) -> None:
        """Called when CONN_ACCEPT does not arrive within CONN_TIMEOUT seconds."""
        with self._state_lock:
            if self._state != ConnectionState.CONNECTING:
                return
            peer = self._peer
            self._state = ConnectionState.IDLE
            self._peer = None
            nonce, self._conn_nonce = self._conn_nonce, b"\x00\x00"
        # Notify the peer that we gave up so it can clean up its state
        if peer and self._driver:
            self._driver.send(bytes.fromhex(peer), make_conn_reject(self._car_id, nonce))
        self._emit("error", {"message": f"Connection to {peer} timed out (no response in {self.CONN_TIMEOUT:.0f}s)"})
        logger.info("CONN_TIMEOUT → %s", peer)

    # ── Pending-accept timeout ─────────────────────────────────────────────────

    def _start_pending_timer(self) -> None:
        self._stop_pending_timer()
        self._pending_timer = threading.Timer(self.CONN_TIMEOUT, self._on_pending_timeout)
        self._pending_timer.daemon = True
        self._pending_timer.start()

    def _stop_pending_timer(self) -> None:
        if self._pending_timer:
            self._pending_timer.cancel()
            self._pending_timer = None

    def _on_pending_timeout(self) -> None:
        """Auto-reject a CONN_REQUEST if the user takes too long to respond.

        Protects against the car getting stuck in PENDING_ACCEPT forever when
        the initiator's follow-up CONN_REJECT (sent by their own timeout handler)
        is lost over the radio.
        """
        with self._state_lock:
            if self._state != ConnectionState.PENDING_ACCEPT:
                return
            peer = self._peer
            nonce, self._peer_nonce = self._peer_nonce, b"\x00\x00"
            self._state = ConnectionState.IDLE
            self._peer = None
        if peer and self._driver:
            self._driver.send(bytes.fromhex(peer), make_conn_reject(self._car_id, nonce))
        self._emit("connectionCancelled", {"car_id": peer})
        logger.info("PENDING_ACCEPT timeout – auto-rejected %s", peer)

    # ── Heartbeat / keepalive ─────────────────────────────────────────────────

    def _start_heartbeat(self) -> None:
        self._last_pong_at = time.monotonic()
        self._stop_heartbeat()
        self._heartbeat_timer = threading.Timer(self.HEARTBEAT_INTERVAL, self._heartbeat_tick)
        self._heartbeat_timer.daemon = True
        self._heartbeat_timer.start()

    def _stop_heartbeat(self) -> None:
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
            self._heartbeat_timer = None

    def _heartbeat_tick(self) -> None:
        with self._state_lock:
            if self._state != ConnectionState.CONNECTED:
                return
            peer = self._peer

        # Declare peer lost if we haven't heard from them recently
        if time.monotonic() - self._last_pong_at > self.HEARTBEAT_TIMEOUT:
            with self._state_lock:
                self._state = ConnectionState.IDLE
                self._peer = None
            self._emit("peerDisconnected", {"car_id": peer})
            logger.info(
                "Heartbeat timeout (%.0fs) – peer %s declared lost",
                self.HEARTBEAT_TIMEOUT, peer,
            )
            return

        # Send a keepalive ping and reschedule.
        # Uses _hb_seq (not _ping_seq) so heartbeat pings don't interfere with
        # user-initiated ping/pong latency tracking.
        self._hb_seq = (self._hb_seq + 1) % 0x10000
        pkt = make_ping(self._car_id, self._hb_seq)
        self._driver.send(bytes.fromhex(peer), pkt)

        self._heartbeat_timer = threading.Timer(self.HEARTBEAT_INTERVAL, self._heartbeat_tick)
        self._heartbeat_timer.daemon = True
        self._heartbeat_timer.start()

    # ── Messaging (requires active connection) ────────────────────────────────

    def _extend_heartbeat_after_send(self) -> None:
        """After we send to the peer, extend our heartbeat window so we don't
        declare them dead while they're busy processing our message.
        Backend-only: no change to WebSocket events; works with current frontend."""
        self._last_pong_at = time.monotonic()

    def handle_send_text(self, text: str) -> None:
        peer = self._assert_connected()
        if not peer:
            return
        pkt = make_text(self._car_id, text[:26])
        if not self._driver.send(bytes.fromhex(peer), pkt):
            self._emit("messageFailed", {"kind": "text"})
        else:
            self._extend_heartbeat_after_send()

    def handle_send_sound(self, sound_id: int) -> None:
        peer = self._assert_connected()
        if not peer:
            return
        pkt = make_sound(self._car_id, sound_id)
        if not self._driver.send(bytes.fromhex(peer), pkt):
            self._emit("messageFailed", {"kind": "sound"})
        else:
            self._extend_heartbeat_after_send()

    def handle_send_honk(self) -> None:
        peer = self._assert_connected()
        if not peer:
            return
        pkt = make_honk(self._car_id)
        if not self._driver.send(bytes.fromhex(peer), pkt):
            self._emit("messageFailed", {"kind": "honk"})
        else:
            self._extend_heartbeat_after_send()

    def handle_send_ping(self) -> None:
        peer = self._assert_connected()
        if not peer:
            return
        self._ping_seq = (self._ping_seq + 1) % 0x10000
        self._ping_sent_at = time.monotonic()
        pkt = make_ping(self._car_id, self._ping_seq)
        self._driver.send(bytes.fromhex(peer), pkt)

    def _assert_connected(self) -> Optional[str]:
        """Return the peer hex string if connected, None otherwise.

        The peer is captured inside the lock so callers get a valid snapshot
        that won't become None even if handle_disconnect() fires concurrently.
        """
        with self._state_lock:
            if self._state == ConnectionState.CONNECTED:
                return self._peer
        self._emit("error", {"message": "Not connected to any car"})
        return None

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
            MsgType.CONN_REQUEST: lambda: self._rx_conn_request(from_hex, pkt),
            MsgType.CONN_ACCEPT:  lambda: self._rx_conn_accept(from_hex),
            MsgType.CONN_REJECT:  lambda: self._rx_conn_reject(from_hex, pkt),
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
        now = time.monotonic()
        with self._nearby_lock:
            is_new = from_hex not in self._nearby
            if is_new:
                self._nearby[from_hex] = {**info, "_seen_at": now}
            else:
                # Refresh TTL and update plate (may have changed via setinfo)
                self._nearby[from_hex].update({**info, "_seen_at": now})
        if is_new:
            self._emit("carDiscovered", {"car_id": from_hex, **info})
            logger.info("Discovered car %s (plate=%s)", from_hex, info.get("plate"))

    def _rx_conn_request(self, from_hex: str, pkt: RFPacket) -> None:
        nonce = parse_conn_nonce(pkt)
        with self._state_lock:
            if self._state not in (ConnectionState.IDLE, ConnectionState.SCANNING):
                # Already busy – auto-reject, echoing the nonce so the sender
                # can correlate this rejection with the exact request they sent.
                self._driver.send(
                    bytes.fromhex(from_hex),
                    make_conn_reject(self._car_id, nonce),
                )
                return
            self._state = ConnectionState.PENDING_ACCEPT
            # Store the requester and their nonce inside the lock so that:
            #   • _rx_conn_reject can detect if they cancel before we accept
            #   • handle_reject_connection can echo the right nonce back
            self._peer       = from_hex
            self._peer_nonce = nonce

        with self._nearby_lock:
            info = dict(self._nearby.get(from_hex, {}))
        self._emit("connectionRequest", {
            "car_id": from_hex,
            "plate": info.get("plate", from_hex),
        })
        # Guard: if the user never responds (and the initiator's CONN_REJECT is
        # lost over the radio), we'll auto-reject after CONN_TIMEOUT seconds.
        self._start_pending_timer()
        logger.info("CONN_REQUEST received ← %s (nonce=%s)", from_hex, nonce.hex())

    def _rx_conn_accept(self, from_hex: str) -> None:
        with self._state_lock:
            if self._state != ConnectionState.CONNECTING or self._peer != from_hex:
                return
            self._state = ConnectionState.CONNECTED

        self._stop_conn_timer()

        # Exchange full metadata now that the connection is live
        self._send_info_to(bytes.fromhex(from_hex))

        self._start_heartbeat()
        self._emit("connectionAccepted", {"car_id": from_hex})
        logger.info("Connection accepted ↔ %s", from_hex)

    def _rx_conn_reject(self, from_hex: str, pkt: RFPacket) -> None:
        nonce = parse_conn_nonce(pkt)
        event = None
        prev_state = None
        with self._state_lock:
            if self._peer != from_hex:
                return

            if self._state == ConnectionState.CONNECTING:
                if nonce != self._conn_nonce:
                    logger.debug(
                        "Stale CONN_REJECT from %s (nonce %s ≠ %s) – ignored",
                        from_hex, nonce.hex(), self._conn_nonce.hex(),
                    )
                    return
                event = "connectionRejected"
                prev_state = ConnectionState.CONNECTING
                self._state = ConnectionState.IDLE

            elif self._state == ConnectionState.PENDING_ACCEPT:
                if nonce != self._peer_nonce:
                    logger.debug("Stale/spoofed CONN_REJECT while PENDING_ACCEPT – ignored")
                    return
                event = "connectionCancelled"
                self._state = ConnectionState.IDLE

            elif self._state == ConnectionState.CONNECTED:
                # Race: we accepted but initiator cancelled before CONN_ACCEPT arrived
                event = "peerDisconnected"
                prev_state = ConnectionState.CONNECTED
                self._state = ConnectionState.IDLE

            if event is not None:
                self._peer       = None
                self._conn_nonce = b"\x00\x00"
                self._peer_nonce = b"\x00\x00"

        if event is None:
            return

        # Cancel whichever timer was running for this state
        if prev_state == ConnectionState.CONNECTING:
            self._stop_conn_timer()
        elif prev_state == ConnectionState.CONNECTED:
            self._stop_heartbeat()
        else:
            # PENDING_ACCEPT cancellation – stop the pending timeout guard
            self._stop_pending_timer()

        self._emit(event, {"car_id": from_hex})
        logger.info("CONN_REJECT received ← %s → %s", from_hex, event)

    def _rx_conn_close(self, from_hex: str) -> None:
        with self._state_lock:
            if self._peer != from_hex:
                return  # Not our current peer – ignore stale packet
            self._state = ConnectionState.IDLE
            self._peer = None
        self._stop_heartbeat()
        self._emit("peerDisconnected", {"car_id": from_hex})
        logger.info("Peer disconnected ← %s", from_hex)

    def _rx_info(self, from_hex: str, pkt: RFPacket) -> None:
        info = parse_info(pkt)
        now = time.monotonic()
        with self._nearby_lock:
            if from_hex not in self._nearby:
                # INFO arrived before a beacon – create a stub entry so metadata
                # is not lost, and mark _seen_at so TTL pruning works correctly.
                self._nearby[from_hex] = {"_seen_at": now}
                emit_discovered = True
            else:
                emit_discovered = False
            self._nearby[from_hex].update(info)
            public = {k: v for k, v in self._nearby[from_hex].items() if not k.startswith("_")}
        if emit_discovered:
            self._emit("carDiscovered", {"car_id": from_hex, **public})
        # Expose only non-internal keys to the UI
        self._emit("carInfoUpdated", {"car_id": from_hex, **public})

    def _rx_ping(self, from_hex: str, pkt: RFPacket) -> None:
        if not self._is_from_peer(from_hex):
            return  # Don't pong strangers – prevents unsolicited ping floods
        seq = parse_ping_seq(pkt)
        self._driver.send(bytes.fromhex(from_hex), make_pong(self._car_id, seq))
        # A ping also counts as liveness evidence
        self._last_pong_at = time.monotonic()
        self._emit("messageReceived", {"car_id": from_hex, "kind": "ping"})

    def _rx_pong(self, from_hex: str, pkt: RFPacket) -> None:
        if not self._is_from_peer(from_hex):
            return
        # Update liveness timestamp – resets the heartbeat timeout window
        self._last_pong_at = time.monotonic()
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
        # Any traffic from peer (text/sound/honk) counts as liveness – avoids
        # peerDisconnected when the other side is busy sending and misses our pings.
        # Backend-only: payload unchanged (car_id, kind, text/etc); current frontend unchanged.
        self._last_pong_at = time.monotonic()
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
