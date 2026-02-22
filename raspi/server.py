import asyncio

import pydantic
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

import firebase

app = FastAPI()
app.mount("/web", StaticFiles(directory=".", html=True), name="static")


class User(pydantic.BaseModel):
    name: str


@app.post("/users/")
async def create_user(data: User):
    return firebase.push("users", {"name": data.name})


@app.get("/users/")
async def get_users():
    return firebase.get("users")


@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await websocket.accept()
    try:
        counter = 0
        while True:
            await asyncio.sleep(1)  # interval
            counter += 1
            await websocket.send_text(f"{username} message #{counter}")

    except WebSocketDisconnect:
        print(f"{username} disconnected")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
