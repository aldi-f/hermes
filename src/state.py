import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.models import Alert, AlertState, Config
from src.fingerprint import get_fingerprint
from src.persistence.redis_manager import RedisConnectionManager

logger = logging.getLogger(__name__)


@dataclass
class QueuedAlert:
    alert: Alert
    group_name: str
    fingerprint: str
    queued_at: float = field(default_factory=time.time)


class AlertReplayQueue:
    def __init__(self, max_size: int = 1000):
        self._queue: deque[QueuedAlert] = deque(maxlen=max_size)
        self._lock = asyncio.Lock()

    async def enqueue(self, alert: Alert, group_name: str, fingerprint: str) -> bool:
        async with self._lock:
            if len(self._queue) >= self._queue.maxlen:
                logger.warning("Replay queue full, dropping oldest alert")
                self._queue.popleft()
            self._queue.append(QueuedAlert(alert, group_name, fingerprint))
            return True

    async def dequeue(self) -> Optional[QueuedAlert]:
        async with self._lock:
            if self._queue:
                return self._queue.popleft()
            return None

    async def size(self) -> int:
        async with self._lock:
            return len(self._queue)

    async def clear(self):
        async with self._lock:
            self._queue.clear()


class StateManager:
    def __init__(
        self,
        config: Config,
        redis_manager: Optional[RedisConnectionManager] = None,
    ):
        self._config = config
        self._redis = redis_manager
        self._replay_queue = AlertReplayQueue(max_size=config.settings.replay_queue_size)
        self._replay_task: Optional[asyncio.Task] = None
        self._running = False
        self._local_cache: Dict[str, AlertState] = {}
        self._local_lock = asyncio.Lock()

    async def start(self):
        self._running = True
        if self._redis:
            self._replay_task = asyncio.create_task(self._replay_loop())
        logger.info("StateManager started")

    async def stop(self):
        self._running = False
        if self._replay_task:
            self._replay_task.cancel()
            try:
                await self._replay_task
            except asyncio.CancelledError:
                pass
        logger.info("StateManager stopped")

    async def _replay_loop(self):
        while self._running:
            try:
                await asyncio.sleep(5)
                if not self._redis:
                    continue

                if self._redis.circuit_breaker.is_open:
                    continue

                queued = await self._replay_queue.dequeue()
                if queued:
                    success = await self._process_queued_alert(queued)
                    if not success:
                        await self._replay_queue.enqueue(
                            queued.alert, queued.group_name, queued.fingerprint
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in replay loop: {e}")

    async def _process_queued_alert(self, queued: QueuedAlert) -> bool:
        try:
            if self._redis and await self._redis.circuit_breaker.can_execute():
                await self._set_redis_state(queued.fingerprint, queued.group_name, queued.alert)
            return True
        except Exception as e:
            logger.error(f"Failed to process queued alert: {e}")
            return False

    def _make_key(self, fingerprint: str, group_name: str) -> str:
        return f"hermes:alert:state:{group_name}:{fingerprint}"

    async def _get_state(self, fingerprint: str, group_name: str) -> Optional[AlertState]:
        key = self._make_key(fingerprint, group_name)

        if self._redis and await self._redis.circuit_breaker.can_execute():
            try:
                data = await self._redis.client.get(key)
                if data:
                    state_dict = json.loads(data)
                    return AlertState(**state_dict)
            except Exception as e:
                logger.error(f"Redis get failed: {e}")
                await self._redis.circuit_breaker.record_failure()

        async with self._local_lock:
            return self._local_cache.get(key)

    async def _set_state(self, state: AlertState):
        key = self._make_key(state.fingerprint, state.group_name)
        ttl = self._config.settings.deduplication_ttl

        async with self._local_lock:
            self._local_cache[key] = state

        if self._redis:
            if await self._redis.circuit_breaker.can_execute():
                try:
                    await self._redis.client.setex(
                        key, ttl, json.dumps(state.model_dump(mode="json"))
                    )
                    await self._redis.circuit_breaker.record_success()
                except Exception as e:
                    logger.error(f"Redis set failed: {e}")
                    await self._redis.circuit_breaker.record_failure()
            else:
                await self._replay_queue.enqueue(state.alert, state.group_name, state.fingerprint)

    async def _set_redis_state(
        self, fingerprint: str, group_name: str, alert: Alert, status: str = None
    ):
        state = AlertState(
            fingerprint=fingerprint,
            group_name=group_name,
            status=status or alert.status,
            last_seen=time.time(),
            alert=alert,
        )
        await self._set_state(state)

    async def should_send(
        self, alert: Alert, group_name: str, metrics: Optional[Any] = None
    ) -> bool:
        fingerprint = get_fingerprint(alert, self._config.settings.fingerprint_strategy, metrics)

        try:
            existing = await self._get_state(fingerprint, group_name)

            if alert.status == "firing":
                if existing is None:
                    state = AlertState(
                        fingerprint=fingerprint,
                        group_name=group_name,
                        status="firing",
                        last_seen=time.time(),
                        alert=alert,
                    )
                    await self._set_state(state)
                    return True

                if existing.status == "firing":
                    if metrics:
                        metrics.alerts_deduplicated.labels(group=group_name).inc()
                    return False

                existing.status = "firing"
                existing.last_seen = time.time()
                existing.alert = alert
                await self._set_state(existing)
                return True

            if alert.status == "resolved":
                if existing and existing.status == "firing":
                    existing.status = "resolved"
                    existing.last_seen = time.time()
                    existing.alert = alert
                    await self._set_state(existing)
                    return True
                return False

            return True

        except Exception as e:
            logger.error(f"Error in should_send: {e}")
            return True

    async def get_active_count(self, group_name: str) -> int:
        if self._redis and await self._redis.circuit_breaker.can_execute():
            try:
                pattern = f"hermes:alert:state:{group_name}:*"
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

    async def should_send_group(
        self, alerts: list[Alert], grouping_key: str, group_name: str, deduplication_window: int = 0
    ) -> bool:
        from src.fingerprint import get_fingerprint

        group_fingerprint = f"group:{grouping_key}"

        try:
            existing = await self._get_state(group_fingerprint, group_name)

            alert_fingerprints = [
                get_fingerprint(alert, self._config.settings.fingerprint_strategy, None)
                for alert in alerts
            ]
            sorted_fingerprints = sorted(alert_fingerprints)
            alert_status = alerts[0].status if alerts else "unknown"

            if existing is None:
                state = AlertState(
                    fingerprint=group_fingerprint,
                    group_name=group_name,
                    status=alert_status,
                    last_seen=time.time(),
                    alert=alerts[0] if alerts else None,
                    metadata={"alert_fingerprints": sorted_fingerprints},
                )
                await self._set_state(state)
                return True

            existing_fingerprints = getattr(existing, "metadata", {}).get("alert_fingerprints", [])

            if sorted_fingerprints != existing_fingerprints:
                state = AlertState(
                    fingerprint=group_fingerprint,
                    group_name=group_name,
                    status=alert_status,
                    last_seen=time.time(),
                    alert=alerts[0] if alerts else None,
                    metadata={"alert_fingerprints": sorted_fingerprints},
                )
                await self._set_state(state)
                return True

            if deduplication_window > 0:
                time_since_last = time.time() - existing.last_seen
                if time_since_last >= deduplication_window:
                    state = AlertState(
                        fingerprint=group_fingerprint,
                        group_name=group_name,
                        status=alert_status,
                        last_seen=time.time(),
                        alert=alerts[0] if alerts else None,
                        metadata={"alert_fingerprints": sorted_fingerprints},
                    )
                    await self._set_state(state)
                    return True

            existing.last_seen = time.time()
            existing.alert = alerts[0] if alerts else None
            await self._set_state(existing)
            return False

        except Exception as e:
            logger.error(f"Error in should_send_group: {e}")
            return True

    async def get_queue_size(self) -> int:
        return await self._replay_queue.size()

    def update_config(self, config: Config):
        self._config = config
        self._replay_queue._queue = deque(
            list(self._replay_queue._queue), maxlen=config.settings.replay_queue_size
        )
