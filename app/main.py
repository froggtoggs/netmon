import asyncio
import os
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from database import Database
from monitor import MonitorScheduler

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))
CONFIG_PATH = "/config/hosts.yml"

db = Database()
scheduler: MonitorScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler
    await db.init()
    await _load_config()
    scheduler = MonitorScheduler(db, interval=CHECK_INTERVAL)
    task = asyncio.create_task(scheduler.run())
    yield
    task.cancel()
    await db.close()


app = FastAPI(title="NetMon", lifespan=lifespan)


async def _load_config():
    if not os.path.exists(CONFIG_PATH):
        return
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}
    for entry in config.get("hosts", []):
        host = entry.get("host", "").strip()
        name = entry.get("name", host)
        type_ = entry.get("type", "ping")
        group = entry.get("group", "")
        if host and not await db.host_exists(host):
            await db.add_host(name, host, type_, group)


# ── API ──────────────────────────────────────────────────────────────────────

class HostIn(BaseModel):
    name: str
    host: str
    type: str = "ping"
    group: str = ""


class ReorderItem(BaseModel):
    id: int
    group: str = ""
    sort_order: int


@app.get("/api/hosts")
async def list_hosts():
    return await db.get_hosts_with_status()


@app.post("/api/hosts", status_code=201)
async def create_host(body: HostIn):
    host_id = await db.add_host(body.name, body.host.strip(), body.type, body.group)
    if scheduler:
        asyncio.create_task(scheduler.check_host_by_id(host_id))
    return {"id": host_id}


@app.put("/api/hosts/{host_id}")
async def update_host(host_id: int, body: HostIn):
    await db.update_host(host_id, body.name, body.host.strip(), body.type, body.group)
    if scheduler:
        asyncio.create_task(scheduler.check_host_by_id(host_id))
    return {"ok": True}


@app.patch("/api/hosts/reorder")
async def reorder_hosts(body: list[ReorderItem]):
    await db.reorder_hosts([item.model_dump() for item in body])
    return {"ok": True}


@app.delete("/api/hosts/{host_id}")
async def remove_host(host_id: int):
    await db.delete_host(host_id)
    return {"ok": True}


@app.get("/api/hosts/{host_id}/history")
async def host_history(host_id: int, limit: int = 60):
    return await db.get_history(host_id, limit)


@app.get("/health")
async def health():
    return {"ok": True}


# ── Frontend ──────────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse("static/index.html")
