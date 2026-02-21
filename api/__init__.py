from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()

API_SECRET = "super_secret_key"

class SettingsUpdate(BaseModel):
    guild_id: int
    settings: dict

fake_storage = {}

def check_auth(auth):
    if auth != f"Bearer {API_SECRET}":
        raise HTTPException(status_code=403)

@app.post("/settings/update")
async def update_settings(data: SettingsUpdate, authorization: str = Header(None)):
    check_auth(authorization)

    fake_storage[data.guild_id] = data.settings

    return {"success": True}

@app.get("/settings/{guild_id}")
async def get_settings(guild_id: int, authorization: str = Header(None)):
    check_auth(authorization)

    settings = fake_storage.get(guild_id)
    return {"settings": settings}