import aiosqlite
from datetime import datetime, timedelta

DB_PATH = "/data/netmon.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS hosts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT    NOT NULL,
    host      TEXT    NOT NULL,
    type      TEXT    NOT NULL DEFAULT 'ping',
    enabled   INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS checks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id    INTEGER NOT NULL,
    timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP,
    status     TEXT    NOT NULL,
    latency_ms REAL,
    FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_checks_host_time ON checks(host_id, timestamp DESC);
"""


class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()

    # --- hosts ---

    async def get_hosts(self) -> list[dict]:
        async with self._db.execute(
            "SELECT id, name, host, type FROM hosts WHERE enabled = 1 ORDER BY name"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def host_exists(self, host: str) -> bool:
        async with self._db.execute(
            "SELECT 1 FROM hosts WHERE host = ? AND enabled = 1", (host,)
        ) as cur:
            return await cur.fetchone() is not None

    async def add_host(self, name: str, host: str, type_: str) -> int:
        async with self._db.execute(
            "INSERT INTO hosts (name, host, type) VALUES (?, ?, ?)",
            (name, host, type_),
        ) as cur:
            await self._db.commit()
            return cur.lastrowid

    async def update_host(self, host_id: int, name: str, host: str, type_: str):
        await self._db.execute(
            "UPDATE hosts SET name = ?, host = ?, type = ? WHERE id = ?",
            (name, host, type_, host_id),
        )
        await self._db.commit()

    async def delete_host(self, host_id: int):
        await self._db.execute("DELETE FROM checks WHERE host_id = ?", (host_id,))
        await self._db.execute("DELETE FROM hosts WHERE id = ?", (host_id,))
        await self._db.commit()

    # --- checks ---

    async def record_check(self, host_id: int, status: str, latency_ms: float | None):
        await self._db.execute(
            "INSERT INTO checks (host_id, status, latency_ms) VALUES (?, ?, ?)",
            (host_id, status, latency_ms),
        )
        cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        await self._db.execute(
            "DELETE FROM checks WHERE host_id = ? AND timestamp < ?",
            (host_id, cutoff),
        )
        await self._db.commit()

    async def get_hosts_with_status(self) -> list[dict]:
        query = """
            SELECT
                h.id, h.name, h.host, h.type,
                c.status      AS last_status,
                c.latency_ms  AS last_latency,
                c.timestamp   AS last_check,
                (SELECT ROUND(AVG(latency_ms), 2)
                   FROM checks
                  WHERE host_id = h.id
                    AND timestamp > datetime('now', '-1 hour')
                    AND status = 'up')                          AS avg_latency,
                (SELECT ROUND(MIN(latency_ms), 2)
                   FROM checks
                  WHERE host_id = h.id
                    AND timestamp > datetime('now', '-1 hour')
                    AND status = 'up')                          AS min_latency,
                (SELECT ROUND(MAX(latency_ms), 2)
                   FROM checks
                  WHERE host_id = h.id
                    AND timestamp > datetime('now', '-1 hour')
                    AND status = 'up')                          AS max_latency,
                (SELECT COUNT(*)
                   FROM checks
                  WHERE host_id = h.id
                    AND timestamp > datetime('now', '-1 hour')) AS total_checks,
                (SELECT COUNT(*)
                   FROM checks
                  WHERE host_id = h.id
                    AND timestamp > datetime('now', '-1 hour')
                    AND status != 'up')                         AS failed_checks
            FROM hosts h
            LEFT JOIN checks c ON c.id = (
                SELECT id FROM checks WHERE host_id = h.id ORDER BY timestamp DESC LIMIT 1
            )
            WHERE h.enabled = 1
            ORDER BY h.name
        """
        async with self._db.execute(query) as cur:
            rows = await cur.fetchall()

        result = []
        for row in rows:
            d = dict(row)
            total = d.get("total_checks") or 0
            failed = d.get("failed_checks") or 0
            d["uptime_pct"] = round(((total - failed) / total * 100) if total > 0 else 100, 1)
            result.append(d)
        return result

    async def get_history(self, host_id: int, limit: int = 60) -> list[dict]:
        async with self._db.execute(
            """SELECT timestamp, status, latency_ms
               FROM checks
              WHERE host_id = ?
              ORDER BY timestamp DESC
              LIMIT ?""",
            (host_id, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]
