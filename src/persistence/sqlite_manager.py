import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import aiosqlite

from src.models import AlertState

logger = logging.getLogger(__name__)


class SQLiteManager:
    def __init__(self, db_path: str = "/data/hermes.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        await self._create_tables()
        logger.info(f"Connected to SQLite: {self.db_path}")

    async def disconnect(self):
        if self._db:
            await self._db.close()
            self._db = None
        logger.info("Disconnected from SQLite")

    async def _create_tables(self):
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS alert_states (
                key TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                group_name TEXT NOT NULL,
                status TEXT NOT NULL,
                last_seen REAL NOT NULL,
                alert_json TEXT,
                created_at REAL DEFAULT (strftime('%s', 'now')),
                updated_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_alert_states_group
            ON alert_states(group_name)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_alert_states_last_seen
            ON alert_states(last_seen)
        """)
        await self._db.commit()

    def _make_key(self, fingerprint: str, group_name: str) -> str:
        return f"{group_name}:{fingerprint}"

    async def get_state(self, fingerprint: str, group_name: str) -> Optional[AlertState]:
        key = self._make_key(fingerprint, group_name)
        async with self._lock:
            cursor = await self._db.execute(
                "SELECT fingerprint, group_name, status, last_seen, alert_json FROM alert_states WHERE key = ?",
                (key,),
            )
            row = await cursor.fetchone()
            if row:
                from src.models import Alert
                alert = None
                if row[4]:
                    try:
                        alert = Alert(**json.loads(row[4]))
                    except Exception:
                        pass
                return AlertState(
                    fingerprint=row[0],
                    group_name=row[1],
                    status=row[2],
                    last_seen=row[3],
                    alert=alert,
                )
            return None

    async def set_state(self, state: AlertState):
        key = self._make_key(state.fingerprint, state.group_name)
        alert_json = json.dumps(state.alert.model_dump()) if state.alert else None
        async with self._lock:
            await self._db.execute(
                """
                INSERT INTO alert_states (key, fingerprint, group_name, status, last_seen, alert_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, strftime('%s', 'now'))
                ON CONFLICT(key) DO UPDATE SET
                    status = excluded.status,
                    last_seen = excluded.last_seen,
                    alert_json = excluded.alert_json,
                    updated_at = strftime('%s', 'now')
                """,
                (key, state.fingerprint, state.group_name, state.status, state.last_seen, alert_json),
            )
            await self._db.commit()

    async def delete_state(self, fingerprint: str, group_name: str):
        key = self._make_key(fingerprint, group_name)
        async with self._lock:
            await self._db.execute("DELETE FROM alert_states WHERE key = ?", (key,))
            await self._db.commit()

    async def get_active_count(self, group_name: str) -> int:
        async with self._lock:
            cursor = await self._db.execute(
                "SELECT COUNT(*) FROM alert_states WHERE group_name = ? AND status = 'firing'",
                (group_name,),
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def cleanup_expired(self, ttl_seconds: int):
        import time
        cutoff = time.time() - ttl_seconds
        async with self._lock:
            cursor = await self._db.execute(
                "DELETE FROM alert_states WHERE last_seen < ?",
                (cutoff,),
            )
            deleted = cursor.rowcount
            await self._db.commit()
            if deleted > 0:
                logger.debug(f"Cleaned up {deleted} expired states from SQLite")
            return deleted

    async def get_all_states(self, group_name: Optional[str] = None) -> list[AlertState]:
        async with self._lock:
            if group_name:
                cursor = await self._db.execute(
                    "SELECT fingerprint, group_name, status, last_seen, alert_json FROM alert_states WHERE group_name = ?",
                    (group_name,),
                )
            else:
                cursor = await self._db.execute(
                    "SELECT fingerprint, group_name, status, last_seen, alert_json FROM alert_states"
                )
            rows = await cursor.fetchall()
            states = []
            for row in rows:
                from src.models import Alert
                alert = None
                if row[4]:
                    try:
                        alert = Alert(**json.loads(row[4]))
                    except Exception:
                        pass
                states.append(
                    AlertState(
                        fingerprint=row[0],
                        group_name=row[1],
                        status=row[2],
                        last_seen=row[3],
                        alert=alert,
                    )
                )
            return states
