import pydantic
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import firebase

app = FastAPI()
app.mount("/web", StaticFiles(directory=".", html=True), name="static")


class User(pydantic.BaseModel):
    name: str


@app.post("/users/")
async def create_user(data: User):
    print("Creating user:", data.name)
    return firebase.push("users", {"name": data.name})


@app.get("/users/")
async def get_users():
    return firebase.get("users")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
