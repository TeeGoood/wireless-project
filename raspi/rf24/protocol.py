"""
Binary RF24 packet protocol.

Every packet is exactly 32 bytes:
    [0]     msg_type  (1 byte  – MsgType enum)
    [1:6]   from_id   (5 bytes – sender's car ID, derived from plate hash)
    [6:32]  data      (26 bytes – type-specific payload, null-padded)

Message type map
----------------
  0x01  BEACON           Broadcast presence; data = plate (≤26 bytes, null-padded)
  0x03  CONN_REQUEST     Request a P2P connection
  0x04  CONN_ACCEPT      Accept a pending connection
  0x05  CONN_REJECT      Reject a pending connection
  0x06  CONN_CLOSE       Graceful disconnect notification (tells peer to drop state)
  0x07  INFO             One metadata field; data[0]=field_id, data[1:]=value
  0x10  PING             Round-trip probe; data[0:2]=seq (big-endian uint16)
  0x11  PONG             Reply to PING; same data layout
  0x20  TEXT             Text message; data = utf-8 text (≤26 bytes)
  0x21  SOUND            Sound event; data[0]=sound_id
  0x22  HONK             Honk; no data payload

INFO field_id values: 0=color, 1=plate, 2=model, 3=owner
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

PAYLOAD_SIZE = 32
_HEADER = 1 + 5  # msg_type + from_id
_DATA_LEN = PAYLOAD_SIZE - _HEADER  # 26 bytes


class MsgType(IntEnum):
    BEACON       = 0x01
    CONN_REQUEST = 0x03
    CONN_ACCEPT  = 0x04
    CONN_REJECT  = 0x05
    CONN_CLOSE   = 0x06
    INFO         = 0x07
    PING         = 0x10
    PONG         = 0x11
    TEXT         = 0x20
    SOUND        = 0x21
    HONK         = 0x22


INFO_FIELDS = ("color", "plate", "model", "owner")


@dataclass
class RFPacket:
    msg_type: MsgType
    from_id: bytes   # 5 bytes
    data: bytes      # 26 bytes


# ── Low-level pack / unpack ───────────────────────────────────────────────────


def encode(msg_type: MsgType, from_id: bytes, data: bytes = b"") -> bytes:
    """Build a 32-byte RF24 payload."""
    assert len(from_id) == 5, "from_id must be exactly 5 bytes"
    padded = (data + b"\x00" * _DATA_LEN)[:_DATA_LEN]
    return bytes([int(msg_type)]) + from_id + padded


def decode(raw: bytes | bytearray) -> Optional[RFPacket]:
    """Parse a 32-byte RF24 payload.  Returns None for malformed packets."""
    if len(raw) < PAYLOAD_SIZE:
        return None
    try:
        msg_type = MsgType(raw[0])
    except ValueError:
        return None
    return RFPacket(
        msg_type=msg_type,
        from_id=bytes(raw[1:6]),
        data=bytes(raw[6:32]),
    )


# ── Packet builders ───────────────────────────────────────────────────────────


def make_beacon(from_id: bytes, plate: str) -> bytes:
    return encode(MsgType.BEACON, from_id, plate.encode()[:_DATA_LEN])


def make_conn_request(from_id: bytes) -> bytes:
    return encode(MsgType.CONN_REQUEST, from_id)


def make_conn_accept(from_id: bytes) -> bytes:
    return encode(MsgType.CONN_ACCEPT, from_id)


def make_conn_reject(from_id: bytes) -> bytes:
    return encode(MsgType.CONN_REJECT, from_id)


def make_conn_close(from_id: bytes) -> bytes:
    return encode(MsgType.CONN_CLOSE, from_id)


def make_info(from_id: bytes, field_id: int, value: str) -> bytes:
    """INFO packet: field_id selects which metadata field is being sent."""
    data = bytes([field_id & 0xFF]) + value.encode()[:(_DATA_LEN - 1)]
    return encode(MsgType.INFO, from_id, data)


def make_ping(from_id: bytes, seq: int) -> bytes:
    return encode(MsgType.PING, from_id, struct.pack(">H", seq & 0xFFFF))


def make_pong(from_id: bytes, seq: int) -> bytes:
    return encode(MsgType.PONG, from_id, struct.pack(">H", seq & 0xFFFF))


def make_text(from_id: bytes, text: str) -> bytes:
    return encode(MsgType.TEXT, from_id, text.encode()[:_DATA_LEN])


def make_sound(from_id: bytes, sound_id: int) -> bytes:
    return encode(MsgType.SOUND, from_id, bytes([sound_id & 0xFF]))


def make_honk(from_id: bytes) -> bytes:
    return encode(MsgType.HONK, from_id)


# ── Packet parsers ────────────────────────────────────────────────────────────


def parse_beacon(pkt: RFPacket) -> dict:
    return {"plate": pkt.data.rstrip(b"\x00").decode(errors="replace")}


def parse_info(pkt: RFPacket) -> dict:
    if not pkt.data:
        return {}
    field_id = pkt.data[0]
    value = pkt.data[1:].rstrip(b"\x00").decode(errors="replace")
    key = INFO_FIELDS[field_id] if field_id < len(INFO_FIELDS) else f"field_{field_id}"
    return {key: value}


def parse_ping_seq(pkt: RFPacket) -> int:
    return struct.unpack(">H", pkt.data[:2])[0] if len(pkt.data) >= 2 else 0


def parse_text(pkt: RFPacket) -> dict:
    return {"text": pkt.data.rstrip(b"\x00").decode(errors="replace")}


def parse_sound(pkt: RFPacket) -> dict:
    return {"sound_id": pkt.data[0] if pkt.data else 0}
