import asyncio
import re
import time

import httpx

from database import Database


async def ping_host(host: str) -> tuple[str, float | None]:
    """ICMP ping — returns (status, latency_ms)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", "3", host,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=6)
        except asyncio.TimeoutError:
            proc.kill()
            return "timeout", None

        if proc.returncode == 0:
            match = re.search(r"time[=<]([\d.]+)\s*ms", stdout.decode())
            latency = float(match.group(1)) if match else None
            return "up", latency
        return "down", None
    except Exception:
        return "error", None


async def check_http(url: str) -> tuple[str, float | None]:
    """HTTP/HTTPS check — returns (status, latency_ms)."""
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    try:
        async with httpx.AsyncClient(
            timeout=10, follow_redirects=True, verify=False
        ) as client:
            t0 = time.monotonic()
            resp = await client.get(url)
            latency = round((time.monotonic() - t0) * 1000, 2)
            status = "up" if resp.status_code < 400 else "down"
            return status, latency
    except httpx.TimeoutException:
        return "timeout", None
    except Exception:
        return "down", None


class MonitorScheduler:
    def __init__(self, db: Database, interval: int = 30):
        self.db = db
        self.interval = interval

    async def _check(self, host: dict):
        if host["type"] == "http":
            status, latency = await check_http(host["host"])
        else:
            status, latency = await ping_host(host["host"])
        await self.db.record_check(host["id"], status, latency)

    async def check_host_by_id(self, host_id: int):
        for host in await self.db.get_hosts():
            if host["id"] == host_id:
                await self._check(host)
                return

    async def run(self):
        while True:
            hosts = await self.db.get_hosts()
            if hosts:
                await asyncio.gather(*[self._check(h) for h in hosts], return_exceptions=True)
            await asyncio.sleep(self.interval)
