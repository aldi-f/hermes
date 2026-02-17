import asyncio
import logging
from typing import Optional

import redis.asyncio as aioredis

from src.persistence.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class RedisConnectionManager:
    def __init__(
        self,
        redis_url: str,
        max_connections: int = 50,
        failure_threshold: int = 3,
        recovery_timeout: int = 60,
    ):
        self.redis_url = redis_url
        self.max_connections = max_connections
        self._pool: Optional[aioredis.ConnectionPool] = None
        self._client: Optional[aioredis.Redis] = None
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

    async def connect(self) -> bool:
        try:
            self._pool = aioredis.ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.max_connections,
                decode_responses=True,
                socket_keepalive=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            self._client = aioredis.Redis(connection_pool=self._pool)
            await self._client.ping()
            await self.circuit_breaker.record_success()
            logger.info(f"Connected to Redis: {self.redis_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            await self.circuit_breaker.record_failure()
            return False

    async def disconnect(self):
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._pool:
            await self._pool.aclose()
            self._pool = None
        logger.info("Disconnected from Redis")

    @property
    def client(self) -> aioredis.Redis:
        if not self._client:
            raise RuntimeError("Redis not connected")
        return self._client

    async def is_healthy(self) -> bool:
        if not self._client:
            return False
        try:
            await self._client.ping()
            return True
        except Exception:
            return False

    async def execute_with_fallback(self, operation: callable, fallback: callable = None):
        if not await self.circuit_breaker.can_execute():
            if fallback:
                return await fallback()
            raise RuntimeError("Circuit breaker is open")

        try:
            result = await operation(self.client)
            await self.circuit_breaker.record_success()
            return result
        except Exception as e:
            await self.circuit_breaker.record_failure()
            logger.error(f"Redis operation failed: {e}")
            if fallback:
                return await fallback()
            raise

    async def reconnect(self) -> bool:
        await self.disconnect()
        return await self.connect()
