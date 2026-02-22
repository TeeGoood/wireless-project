"""
FastAPI server – HTTP static files + WebSocket event bus for RF24 communication.

WebSocket endpoint: ws://<host>:8000/ws

Every message is a JSON object with the shape:
    { "type": "<event>", "payload": { ... } }

See rf24/schema.py for the full list of event types.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    manager.start(loop, event_queue)

    forwarder = asyncio.create_task(
        _event_forwarder(), name="rf24-event-forwarder"
    )
    logger.info("Server started")

    yield

    forwarder.cancel()
    manager.stop()
    logger.info("Server stopped")


app = FastAPI(title="Car RF24 Gateway", lifespan=lifespan)


# ── HTTP ──────────────────────────────────────────────────────────────────────


@app.get("/")
async def root():
    return FileResponse("index.html")


# ── WebSocket ─────────────────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    logger.info("WebSocket client connected (%d total)", len(connected_clients))

    # Send initial state snapshot
    await _send(ws, {
        "type": "init",
        "payload": {
            "info":   manager.get_info(),
            "nearby": manager.get_nearby(),
            "state":  manager.get_state(),
        },
    })

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
        logger.info("WebSocket client disconnected (%d remaining)", len(connected_clients))


async def _handle_client_event(ws: WebSocket, event: dict) -> None:
    t = event.get("type")
    p = event.get("payload", {})

    match t:
        # ── Config ────────────────────────────────────────────────────────────
        case "changeInfo":
            manager.handle_change_info(p)

        case "getInfo":
            await _broadcast({"type": "infoUpdated", "payload": manager.get_info()})

        # ── Discovery ─────────────────────────────────────────────────────────
        case "scan":
            manager.handle_scan()

        case "beacon":
            manager.handle_beacon()

        case "getNearby":
            await _broadcast({
                "type": "nearbyList",
                "payload": {"cars": manager.get_nearby()},
            })

        # ── Connection lifecycle ───────────────────────────────────────────────
        case "connect":
            car_id = p.get("car_id", "")
            manager.handle_connect(car_id)

        case "acceptConnection":
            car_id = p.get("car_id", "")
            manager.handle_accept_connection(car_id)

        case "rejectConnection":
            car_id = p.get("car_id", "")
            manager.handle_reject_connection(car_id)

        case "disconnect":
            manager.handle_disconnect()

        # ── Messaging ─────────────────────────────────────────────────────────
        case "sendText":
            manager.handle_send_text(str(p.get("text", "")))

        case "sendSound":
            manager.handle_send_sound(int(p.get("sound_id", 0)))

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

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
