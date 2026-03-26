import asyncio
import json
import logging
import time
from typing import Dict, Optional

from src.models import Alert, AlertState, Config
from src.fingerprint import get_fingerprint
from src.persistence.redis_manager import RedisConnectionManager

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(
        self,
        config: Config,
        redis_manager: Optional[RedisConnectionManager] = None,
    ):
        self._config = config
        self._redis = redis_manager
        self._local_cache: Dict[str, AlertState] = {}
        self._local_lock = asyncio.Lock()
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("StateManager started")

    async def stop(self):
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("StateManager stopped")

    async def _cleanup_loop(self):
        while self._running:
            try:
                await asyncio.sleep(60)
                ttl = self._config.settings.deduplication_ttl
                if ttl <= 0:
                    continue

                async with self._local_lock:
                    now = time.time()
                    expired = [k for k, v in self._local_cache.items() if now - v.last_seen > ttl]
                    for key in expired:
                        del self._local_cache[key]

                    if expired:
                        logger.debug(f"Cleaned up {len(expired)} expired entries")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    def _make_key(self, fingerprint: str, group_name: str) -> str:
        return f"hermes:alert:{group_name}:{fingerprint}"

    async def _get_state(self, fingerprint: str, group_name: str) -> Optional[AlertState]:
        key = self._make_key(fingerprint, group_name)
        ttl = self._config.settings.deduplication_ttl

        if self._redis:
            try:
                data = await self._redis.client.get(key)
                if data:
                    return AlertState(**json.loads(data))
            except Exception as e:
                logger.error(f"Redis get failed: {e}")

        async with self._local_lock:
            state = self._local_cache.get(key)
            if state:
                if ttl > 0 and time.time() - state.last_seen > ttl:
                    del self._local_cache[key]
                    return None
            return state

    async def _set_state(self, fingerprint: str, group_name: str):
        key = self._make_key(fingerprint, group_name)
        ttl = self._config.settings.deduplication_ttl

        state = AlertState(
            fingerprint=fingerprint,
            group_name=group_name,
            status="firing",
            last_seen=time.time(),
        )

        async with self._local_lock:
            self._local_cache[key] = state

        if self._redis and ttl > 0:
            try:
                await self._redis.client.setex(key, ttl, json.dumps(state.model_dump(mode="json")))
            except Exception as e:
                logger.error(f"Redis set failed: {e}")

    async def _delete_state(self, fingerprint: str, group_name: str):
        key = self._make_key(fingerprint, group_name)

        async with self._local_lock:
            self._local_cache.pop(key, None)

        if self._redis:
            try:
                await self._redis.client.delete(key)
            except Exception as e:
                logger.error(f"Redis delete failed: {e}")

    async def should_send(self, alert: Alert, group_name: str) -> bool:
        ttl = self._config.settings.deduplication_ttl

        if ttl <= 0:
            return True

        fingerprint = get_fingerprint(alert, self._config.settings.fingerprint_strategy)

        try:
            existing = await self._get_state(fingerprint, group_name)

            if alert.status == "firing":
                if existing is None:
                    await self._set_state(fingerprint, group_name)
                    return True
                return False

            if alert.status == "resolved":
                if existing is not None:
                    await self._delete_state(fingerprint, group_name)
                    return True
                return False

            return True

        except Exception as e:
            logger.error(f"Error in should_send: {e}")
            return True

    async def get_active_count(self, group_name: str) -> int:
        if self._redis:
            try:
                pattern = f"hermes:alert:{group_name}:*"
                keys = []
                async for key in self._redis.client.scan_iter(match=pattern, count=100):
                    keys.append(key)
                return len(keys)
            except Exception as e:
                logger.error(f"Redis scan failed: {e}")

        async with self._local_lock:
            return sum(
                1
                for s in self._local_cache.values()
                if s.group_name == group_name and s.status == "firing"
            )

    async def get_queue_size(self) -> int:
        if self._redis:
            try:
                keys = []
                async for key in self._redis.client.scan_iter(match="hermes:alert:*", count=100):
                    keys.append(key)
                return len(keys)
            except Exception as e:
                logger.error(f"Redis scan failed: {e}")

        async with self._local_lock:
            return len(self._local_cache)

    def update_config(self, config: Config):
        self._config = config
