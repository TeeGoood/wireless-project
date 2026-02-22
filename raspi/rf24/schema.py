"""
Event-driven message schema for car-to-car RF24 communication.

Every message on the WebSocket has the shape:
    { "type": "<EventType>", "payload": { ... } }

UI → Server commands
--------------------
  changeInfo       Update car metadata in config.txt
  getInfo          Request current car info
  scan             Start beacon-broadcasting scan for nearby cars
  beacon           Send a single one-shot beacon
  connect          Initiate a connection to a discovered car
  acceptConnection Accept an incoming connection request
  rejectConnection Reject an incoming connection request
  disconnect       Tear down the active connection
  sendText         Send a text message to the connected car
  sendSound        Send a sound event to the connected car
  sendHonk         Send a honk to the connected car
  sendPing         Send a ping to measure round-trip latency

Server → UI events
------------------
  init             Sent on WS connect – current state snapshot
  infoUpdated      Car metadata was updated (own car)
  scanStarted      Scan mode activated
  carDiscovered    A new car was seen on the broadcast channel
  carInfoUpdated   Full metadata received for a discovered car
  connectionRequest Another car wants to connect (needs accept/reject)
  connectionAccepted Connection is live
  connectionRejected Connection was rejected by the remote car
  disconnected     Active connection ended
  messageReceived  Incoming text / sound / honk / ping / pong
  nearbyList       Response to getNearby – list of discovered cars
  error            Something went wrong
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


# ── Shared ────────────────────────────────────────────────────────────────────


class CarInfo(BaseModel):
    """Car metadata stored in config.txt.  Each field ≤ 25 chars (RF24 limit)."""

    color: str = Field(default="Unknown", max_length=25)
    plate: str = Field(default="UNKNOWN", max_length=25)
    model: str = Field(default="Unknown", max_length=25)
    owner: str = Field(default="Unknown", max_length=25)


class Event(BaseModel):
    """Generic event envelope – used for both inbound and outbound messages."""

    type: str
    payload: dict[str, Any] = {}


# ── UI → Server payloads ──────────────────────────────────────────────────────


class ChangeInfoPayload(CarInfo):
    """Payload for the 'changeInfo' command."""


class ConnectPayload(BaseModel):
    """Payload for the 'connect' command."""

    car_id: str  # hex string e.g. "a1b2c3d4e5"


class AcceptConnectionPayload(BaseModel):
    car_id: str


class RejectConnectionPayload(BaseModel):
    car_id: str


class SendTextPayload(BaseModel):
    text: str = Field(max_length=26)


class SendSoundPayload(BaseModel):
    sound_id: int = Field(ge=0, le=255)


# ── Server → UI payloads ──────────────────────────────────────────────────────


class InitPayload(BaseModel):
    info: dict[str, Any]
    nearby: list[dict[str, Any]]
    state: str


class DiscoveredCarPayload(BaseModel):
    car_id: str
    plate: str  # quick identifier extracted from BEACON packet


class CarInfoUpdatedPayload(CarInfo):
    car_id: str


class ConnectionRequestPayload(BaseModel):
    car_id: str
    plate: str


class ConnectionAcceptedPayload(BaseModel):
    car_id: str


class ConnectionRejectedPayload(BaseModel):
    car_id: str


class MessageReceivedPayload(BaseModel):
    car_id: str
    kind: Literal["text", "sound", "honk", "ping", "pong"]
    text: str | None = None
    sound_id: int | None = None
    latency_ms: int | None = None


class NearbyListPayload(BaseModel):
    cars: list[dict[str, Any]]


class ErrorPayload(BaseModel):
    message: str
