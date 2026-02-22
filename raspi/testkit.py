#!/usr/bin/env python3
"""
RF24 Car Communication – CLI Testkit
=====================================
Interactive terminal client for the RF24 WebSocket event bus.
Useful for smoke-testing without a browser UI.

Usage
-----
  # On the Pi itself (server already running):
  python testkit.py

  # From a laptop over SSH / LAN:
  python testkit.py --host 192.168.1.100

  # Custom port:
  python testkit.py --host raspi.local --port 8080

Commands
--------
  info                        Show own car info
  setinfo key=val [key=val]   Update metadata  (color/plate/model/owner)
  scan                        Start scanning for nearby cars
  beacon                      Send a one-shot beacon (no periodic repeat)
  nearby                      List currently discovered cars
  connect <car_id>            Connect to a discovered car (hex ID)
  accept  <car_id>            Accept an incoming connection request
  reject  <car_id>            Reject an incoming connection request
  disconnect                  Tear down the active connection
  text    <message>           Send text to the connected car
  sound   <0-255>             Send a sound event
  honk                        Send a honk
  ping                        Send a ping (latency shown in pong reply)
  help                        Print this command list
  quit / exit / Ctrl-C        Exit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from typing import Optional

import websockets
from websockets.asyncio.client import ClientConnection

# ── ANSI colour helpers ───────────────────────────────────────────────────────

USE_COLOUR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOUR else text


def green(t: str)  -> str: return _c("92", t)
def yellow(t: str) -> str: return _c("93", t)
def cyan(t: str)   -> str: return _c("96", t)
def red(t: str)    -> str: return _c("91", t)
def bold(t: str)   -> str: return _c("1",  t)
def dim(t: str)    -> str: return _c("2",  t)
def magenta(t: str)-> str: return _c("95", t)


# ── Pretty-print incoming events ──────────────────────────────────────────────

def _ts() -> str:
    return dim(datetime.now().strftime("%H:%M:%S"))


def print_event(event: dict) -> None:
    t = event.get("type", "?")
    p = event.get("payload", {})

    match t:
        case "init":
            info   = p.get("info", {})
            nearby = p.get("nearby", [])
            state  = p.get("state", "?")
            print(f"\n{_ts()} {bold('── Connected to server ──')}")
            print(f"  Car ID : {cyan(info.get('car_id', '?'))}")
            print(f"  Plate  : {bold(info.get('plate', '?'))}")
            print(f"  Color  : {info.get('color', '?')}")
            print(f"  Model  : {info.get('model', '?')}")
            print(f"  Owner  : {info.get('owner', '?')}")
            print(f"  State  : {yellow(state)}")
            if nearby:
                print(f"  Nearby : {len(nearby)} car(s) already discovered")

        case "infoUpdated":
            print(f"\n{_ts()} {green('✓ Info updated')}")
            for k, v in p.items():
                if k != "car_id":
                    print(f"  {k}: {v}")

        case "scanStarted":
            print(f"\n{_ts()} {yellow('⟳ Scan started')} – broadcasting beacons every 2 s …")

        case "carDiscovered":
            print(
                f"\n{_ts()} {green('◉ Car discovered')}"
                f"  id={cyan(p.get('car_id','?'))}"
                f"  plate={bold(p.get('plate','?'))}"
            )
            print(f"         → To connect: {dim('connect ' + p.get('car_id','<id>'))}")

        case "carInfoUpdated":
            cid = p.get("car_id", "?")
            print(f"\n{_ts()} {cyan('ℹ Car info')}  id={cyan(cid)}")
            for k in ("color", "plate", "model", "owner"):
                if k in p:
                    print(f"  {k}: {p[k]}")

        case "connectionRequest":
            print(
                f"\n{_ts()} {yellow('⚡ Connection request')} from"
                f" {bold(p.get('plate', '?'))} [{cyan(p.get('car_id','?'))}]"
            )
            print(f"         → {dim('accept ' + p.get('car_id','<id>'))}  or  {dim('reject ' + p.get('car_id','<id>'))}")

        case "connectionAccepted":
            print(f"\n{_ts()} {green('✔ Connected')} with {cyan(p.get('car_id','?'))}")

        case "connectionRejected":
            print(f"\n{_ts()} {red('✗ Connection rejected')} by {cyan(p.get('car_id','?'))}")

        case "disconnected":
            print(f"\n{_ts()} {yellow('↯ Disconnected')}")

        case "messageReceived":
            kind = p.get("kind", "?")
            cid  = cyan(p.get("car_id", "?"))
            match kind:
                case "text":
                    print(f"\n{_ts()} {magenta('✉ Text')} from {cid}: {bold(p.get('text',''))}")
                case "sound":
                    print(f"\n{_ts()} {magenta('♪ Sound')} from {cid}: id={p.get('sound_id','?')}")
                case "honk":
                    print(f"\n{_ts()} {magenta('📯 Honk')} from {cid}")
                case "ping":
                    print(f"\n{_ts()} {dim('Ping')} from {cid}  (auto-ponged)")
                case "pong":
                    ms = p.get("latency_ms", "?")
                    colour = green if isinstance(ms, int) and ms < 100 else yellow
                    print(f"\n{_ts()} {dim('Pong')} from {cid}  latency={colour(str(ms) + ' ms')}")

        case "nearbyList":
            cars = p.get("cars", [])
            if not cars:
                print(f"\n{_ts()} {dim('Nearby: (none yet – try scan first)')}")
            else:
                print(f"\n{_ts()} {bold(f'Nearby cars ({len(cars)}):')}")
                for car in cars:
                    print(
                        f"  {cyan(car.get('car_id','?'))}"
                        f"  plate={bold(car.get('plate','?'))}"
                        f"  color={car.get('color','?')}"
                        f"  model={car.get('model','?')}"
                        f"  owner={car.get('owner','?')}"
                    )

        case "error":
            print(f"\n{_ts()} {red('✗ Error:')} {p.get('message','unknown')}")

        case _:
            print(f"\n{_ts()} {dim(f'[{t}]')} {json.dumps(p)}")


# ── Command parser ────────────────────────────────────────────────────────────

HELP_TEXT = """
Commands:
  info                        Show own car info
  setinfo key=val [key=val]   Update metadata  e.g. setinfo plate=ABC-1 color=Red
  scan                        Start scanning for nearby cars (periodic beacons)
  beacon                      Send a one-shot beacon
  nearby                      List discovered cars
  connect <car_id>            Connect to a discovered car (hex string)
  accept  <car_id>            Accept an incoming connection request
  reject  <car_id>            Reject an incoming connection request
  disconnect                  Disconnect from current car
  text    <message>           Send text message to connected car
  sound   <0-255>             Send sound event to connected car
  honk                        Send honk to connected car
  ping                        Send ping (reply shows round-trip latency)
  help                        Show this help
  quit / exit / Ctrl-C        Exit
"""


def parse_command(line: str) -> Optional[dict]:
    """Parse a CLI line into a WebSocket event dict, or None to skip."""
    parts = line.strip().split(None, 1)
    if not parts:
        return None
    cmd = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    match cmd:
        case "help":
            print(HELP_TEXT)
            return None

        case "info" | "getinfo":
            return {"type": "getInfo", "payload": {}}

        case "setinfo":
            payload: dict = {}
            for token in rest.split():
                if "=" in token:
                    k, _, v = token.partition("=")
                    k = k.strip().lower()
                    if k in ("color", "plate", "model", "owner"):
                        payload[k] = v.strip()
            if not payload:
                print(red("setinfo needs at least one key=value  (color/plate/model/owner)"))
                return None
            return {"type": "changeInfo", "payload": payload}

        case "scan":
            return {"type": "scan", "payload": {}}

        case "beacon":
            return {"type": "beacon", "payload": {}}

        case "nearby":
            return {"type": "getNearby", "payload": {}}

        case "connect":
            car_id = rest.strip()
            if not car_id:
                print(red("Usage: connect <car_id>"))
                return None
            return {"type": "connect", "payload": {"car_id": car_id}}

        case "accept":
            car_id = rest.strip()
            if not car_id:
                print(red("Usage: accept <car_id>"))
                return None
            return {"type": "acceptConnection", "payload": {"car_id": car_id}}

        case "reject":
            car_id = rest.strip()
            if not car_id:
                print(red("Usage: reject <car_id>"))
                return None
            return {"type": "rejectConnection", "payload": {"car_id": car_id}}

        case "disconnect":
            return {"type": "disconnect", "payload": {}}

        case "text":
            if not rest:
                print(red("Usage: text <message>"))
                return None
            if len(rest) > 26:
                print(yellow(f"Warning: message truncated to 26 chars → '{rest[:26]}'"))
            return {"type": "sendText", "payload": {"text": rest[:26]}}

        case "sound":
            try:
                sid = int(rest.strip())
                if not 0 <= sid <= 255:
                    raise ValueError
            except ValueError:
                print(red("Usage: sound <0-255>"))
                return None
            return {"type": "sendSound", "payload": {"sound_id": sid}}

        case "honk":
            return {"type": "sendHonk", "payload": {}}

        case "ping":
            return {"type": "sendPing", "payload": {}}

        case "quit" | "exit":
            raise SystemExit(0)

        case _:
            print(red(f"Unknown command '{cmd}'.  Type help for a list."))
            return None


# ── Async tasks ───────────────────────────────────────────────────────────────

async def receive_loop(ws: ClientConnection) -> None:
    """Continuously print events arriving from the server."""
    async for raw in ws:
        try:
            event = json.loads(raw)
            print_event(event)
            _reprint_prompt()
        except json.JSONDecodeError:
            print(red(f"[bad JSON] {raw}"))


def _reprint_prompt() -> None:
    """Re-draw the input prompt after an event arrives mid-line."""
    print(f"\n{dim('rf24')} {bold('›')} ", end="", flush=True)


async def input_loop(ws: ClientConnection) -> None:
    """Read commands from stdin and send them to the server."""
    loop = asyncio.get_event_loop()
    while True:
        try:
            line = await loop.run_in_executor(
                None, lambda: input(f"{dim('rf24')} {bold('›')} ")
            )
        except EOFError:
            break

        try:
            event = parse_command(line)
        except SystemExit:
            break

        if event:
            await ws.send(json.dumps(event))

    await ws.close()


# ── Entry point ───────────────────────────────────────────────────────────────

async def run(host: str, port: int) -> None:
    url = f"ws://{host}:{port}/ws"
    print(f"{bold('RF24 Car Testkit')}  connecting to {cyan(url)} …")

    try:
        async with websockets.connect(url) as ws:
            print(green("Connected.") + "  Type " + bold("help") + " for commands.\n")
            receive_task = asyncio.create_task(receive_loop(ws))
            input_task   = asyncio.create_task(input_loop(ws))

            done, pending = await asyncio.wait(
                [receive_task, input_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

    except OSError as exc:
        print(red(f"\nCannot connect to {url}: {exc}"))
        print(dim("Is the server running?  (python server.py)"))
        sys.exit(1)
    except KeyboardInterrupt:
        pass

    print(f"\n{dim('Bye.')}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RF24 Car Communication CLI Testkit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--host", default="localhost",
        help="Server hostname or IP  (default: localhost)",
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="Server port  (default: 8000)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run(args.host, args.port))
    except KeyboardInterrupt:
        print(f"\n{dim('Interrupted.')}")


if __name__ == "__main__":
    main()
