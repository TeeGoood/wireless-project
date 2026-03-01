"""
FastAPI server – HTTP static files + WebSocket event bus for RF24 communication.

WebSocket endpoints:
  ws://<host>:8000/ws             – RF24 event bus (car-to-car messages)
  ws://<host>:8000/ws/{username}  – Firebase user session

See rf24/schema.py for the RF24 event type reference.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import pydantic
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import firebase
from rf24.manager import RF24Manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Globals ───────────────────────────────────────────────────────────────────

manager = RF24Manager()
event_queue: asyncio.Queue[dict] = asyncio.Queue()
connected_clients: list[WebSocket] = []


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────


class OnlinePresence:
    """Manages this car's online presence in Firebase at /online/{car_id}."""

    def __init__(self, rf24_manager: RF24Manager, interval: float = 60) -> None:
        self._manager = rf24_manager
        self._interval = interval
        self._task: asyncio.Task | None = None

    @property
    def _ref_path(self) -> str:
        return f"online/{self._manager.get_info()['car_id']}"

    def _build_payload(self) -> dict:
        info = self._manager.get_info()
        info["last_seen"] = datetime.now().isoformat()
        return info

    def start(self) -> None:
        """Register presence immediately and start the background heartbeat."""
        try:
            firebase.set(self._ref_path, self._build_payload())
            logger.info("Registered online presence at /%s", self._ref_path)
        except Exception:
            logger.exception("Failed to register online presence on startup")
        self._task = asyncio.create_task(self._loop(), name="firebase-online-pusher")

    def remove_old_online(self, ref_path: str) -> None:
        """Remove old online presence entries from Firebase."""
        try:
            firebase.delete(ref_path)
            logger.info("Removed old online presence at /%s", ref_path)
        except Exception:
            logger.exception("Failed to remove old online presence at /%s", ref_path)

    def stop(self) -> None:
        """Cancel the heartbeat and remove presence from Firebase."""
        if self._task:
            self._task.cancel()
            self._task = None
        try:
            firebase.delete(self._ref_path)
            logger.info("Removed online presence at /%s", self._ref_path)
        except Exception:
            logger.exception("Failed to remove online presence on shutdown")

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                firebase.set(self._ref_path, self._build_payload())
                logger.info("Updated online presence at /%s", self._ref_path)
            except Exception:
                logger.exception("Failed to update online presence in Firebase")


online_presence = OnlinePresence(manager, interval=20)


class EventStats:
    """Track counts for every RF24 event type and push to Firebase.

    Data is stored at /stats/{car_id} and is never cleaned up on shutdown
    because it is historical.  Existing counts are loaded from Firebase on
    start so counters survive server restarts.
    """

    def __init__(self, rf24_manager: RF24Manager) -> None:
        self._manager = rf24_manager
        self._counts: dict[str, int] = {}
        self._sounds: dict[str, int] = {}

    @property
    def _ref_path(self) -> str:
        return f"stats/{self._manager.get_info()['car_id']}"

    def start(self) -> None:
        """Load existing counts from Firebase (if any)."""
        try:
            data = firebase.get(self._ref_path)
            if isinstance(data, dict):
                sounds = data.pop("sounds", None)
                self._counts = {k: int(v) for k, v in data.items()}
                if isinstance(sounds, dict):
                    self._sounds = {k: int(v) for k, v in sounds.items()}
            logger.info("Loaded event stats from /%s: %s", self._ref_path, self._counts)
        except Exception:
            logger.exception("Failed to load event stats from Firebase")

    def record(self, event: dict) -> None:
        """Increment the counter for the event's type and push to Firebase."""
        event_type = event.get("type", "")
        if not event_type:
            return
        self._counts[event_type] = self._counts.get(event_type, 0) + 1
        self._push()

    def record_sound(self, sound_id: int) -> None:
        """Increment the counter for a specific sound_id."""
        key = str(sound_id)
        self._sounds[key] = self._sounds.get(key, 0) + 1
        self._push()

    def _push(self) -> None:
        try:
            payload = {**self._counts, "sounds": self._sounds}
            firebase.set(self._ref_path, payload)
            logger.info("Updated event stats at /%s: %s", self._ref_path, self._counts)
        except Exception:
            logger.exception("Failed to push event stats to Firebase")


event_stats = EventStats(manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    manager.start(loop, event_queue)
    forwarder = asyncio.create_task(_event_forwarder(), name="rf24-event-forwarder")
    event_stats.start()
    online_presence.start()
    logger.info("Server started")
    yield
    online_presence.stop()
    forwarder.cancel()
    manager.stop()
    logger.info("Server stopped")


app = FastAPI(title="Car RF24 Gateway", lifespan=lifespan)
app.mount("/web", StaticFiles(directory="assets", html=True), name="static")


# ── HTTP ──────────────────────────────────────────────────────────────────────


@app.get("/")
async def root():
    return FileResponse("assets/index.html")


class User(pydantic.BaseModel):
    name: str


@app.post("/users/")
async def create_user(data: User):
    return firebase.push("users", {"name": data.name})


@app.get("/users/")
async def get_users():
    return firebase.get("users")


# ── WebSocket – RF24 event bus ────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    logger.info("WebSocket client connected (%d total)", len(connected_clients))

    await _send(
        ws,
        {
            "type": "init",
            "payload": {
                "info": manager.get_info(),
                "nearby": manager.get_nearby(),
                "state": manager.get_state(),
            },
        },
    )

    try:
        while True:
            raw = await ws.receive_text()
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                await _send(ws, _err("Invalid JSON"))
                continue
            await _handle_client_event(ws, event)

    except WebSocketDisconnect:
        pass
    finally:
        if ws in connected_clients:
            connected_clients.remove(ws)
        logger.info(
            "WebSocket client disconnected (%d remaining)", len(connected_clients)
        )


# ── WebSocket – Firebase user session ─────────────────────────────────────────


@app.websocket("/ws/{username}")
async def websocket_user_endpoint(websocket: WebSocket, username: str):
    await websocket.accept()
    try:
        counter = 0
        while True:
            await asyncio.sleep(1)
            counter += 1
            await websocket.send_text(f"{username} message #{counter}")
    except WebSocketDisconnect:
        logger.info("%s disconnected", username)


# ── RF24 event handling ───────────────────────────────────────────────────────


async def _handle_client_event(ws: WebSocket, event: dict) -> None:
    t = event.get("type")
    p = event.get("payload", {})
    event_stats.record(event)

    match t:
        case "changeInfo":
            id = manager.get_info().get("car_id", "")
            manager.handle_change_info(p)
            online_presence.remove_old_online(f"online/{id}")
        case "getInfo":
            await _broadcast({"type": "infoUpdated", "payload": manager.get_info()})
        case "scan":
            manager.handle_scan()
        case "beacon":
            manager.handle_beacon()
        case "getNearby":
            await _broadcast(
                {
                    "type": "nearbyList",
                    "payload": {"cars": manager.get_nearby()},
                }
            )
        case "connect":
            manager.handle_connect(p.get("car_id", ""))
        case "acceptConnection":
            manager.handle_accept_connection(p.get("car_id", ""))
        case "rejectConnection":
            manager.handle_reject_connection(p.get("car_id", ""))
        case "disconnect":
            manager.handle_disconnect()
        case "sendText":
            manager.handle_send_text(str(p.get("text", "")))
        case "sendSound":
            sound_id = int(p.get("sound_id", 0))
            manager.handle_send_sound(sound_id)
            event_stats.record_sound(sound_id)
        case "sendHonk":
            manager.handle_send_honk()
        case "sendPing":
            manager.handle_send_ping()
        case _:
            logger.warning("Unknown event type: %s", t)
            await _send(ws, _err(f"Unknown event type: {t!r}"))


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _event_forwarder() -> None:
    """Drain the RF24 event queue and fan out to all WebSocket clients."""
    while True:
        event = await event_queue.get()
        event_stats.record(event)
        await _broadcast(event)


async def _broadcast(event: dict) -> None:
    dead: list[WebSocket] = []
    for ws in connected_clients:
        if not await _send(ws, event):
            dead.append(ws)
    for ws in dead:
        connected_clients.remove(ws)


async def _send(ws: WebSocket, event: dict) -> bool:
    try:
        await ws.send_text(json.dumps(event))
        return True
    except Exception:
        return False


def _err(message: str) -> dict:
    return {"type": "error", "payload": {"message": message}}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
