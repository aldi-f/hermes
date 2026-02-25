import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from src.config import init_config, reload_config
from src.models import Config, FingerprintStrategy, WebhookPayload
from src.state import StateManager
from src.webhooks import AlertProcessor
from src.metrics import init_metrics
from src.persistence.redis_manager import RedisConnectionManager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

_config: Optional[Config] = None
_state_manager: Optional[StateManager] = None
_processor: Optional[AlertProcessor] = None
_metrics = None
_redis_manager: Optional[RedisConnectionManager] = None
_shutdown_event: Optional[asyncio.Event] = None


def _on_config_reload(new_config: Config):
    global _config, _processor, _state_manager
    if _processor:
        _processor.update_config(new_config)
    reload_config(new_config)
    _config = new_config
    if _metrics:
        _metrics.config_reload_success.inc()
    logger.info("Config reloaded successfully")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _state_manager, _processor, _metrics, _redis_manager, _shutdown_event

    _shutdown_event = asyncio.Event()
    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    enable_watch = os.environ.get("ENABLE_WATCH", "true").lower() == "true"

    _metrics = init_metrics()
    _config = init_config(config_path, enable_watch, _on_config_reload)

    redis_url = _config.settings.redis_url or os.environ.get("REDIS_URL")
    if redis_url:
        _redis_manager = RedisConnectionManager(
            redis_url=redis_url,
            failure_threshold=_config.settings.redis_failure_threshold,
            recovery_timeout=_config.settings.redis_recovery_timeout,
        )
        connected = await _redis_manager.connect()
        if connected:
            _metrics.redis_connected.set(1)
        else:
            _metrics.redis_connected.set(0)
            logger.warning("Redis connection failed, using fallback mode")

    _state_manager = StateManager(
        config=_config,
        redis_manager=_redis_manager,
    )
    await _state_manager.start()

    _processor = AlertProcessor(_config, _state_manager)

    _metrics.fingerprint_strategy.set(
        {
            FingerprintStrategy.AUTO: 0,
            FingerprintStrategy.ALERTMANAGER: 1,
            FingerprintStrategy.CUSTOM: 2,
        }[_config.settings.fingerprint_strategy]
    )

    logger.info("Hermes started successfully")

    yield

    logger.info("Shutting down Hermes...")

    if _state_manager:
        await _state_manager.stop()

    if _redis_manager:
        await _redis_manager.disconnect()

    logger.info("Hermes stopped")


app = FastAPI(
    title="Hermes",
    description="Alertmanager routing and distribution system",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    redis_healthy = False
    if _redis_manager:
        redis_healthy = await _redis_manager.is_healthy()

    return {
        "status": "ok",
        "config_loaded": _config is not None,
        "redis": "connected"
        if redis_healthy
        else "disconnected"
        if _redis_manager
        else "not_configured",
        "queue_size": await _state_manager.get_queue_size() if _state_manager else 0,
    }


@app.get("/ready")
async def ready():
    if _config is None:
        return JSONResponse(
            status_code=503, content={"status": "not ready", "reason": "config not loaded"}
        )
    if _state_manager is None:
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "reason": "state manager not initialized"},
        )
    return {"status": "ready"}


@app.post("/webhook")
async def webhook(request: Request):
    try:
        body = await request.json()
        payload = WebhookPayload(**body)
    except Exception as e:
        logger.error(f"Failed to parse webhook: {e}")
        return JSONResponse(status_code=400, content={"error": "Invalid payload"})

    results = await _processor.process_webhook(payload, _metrics)
    return {"status": "ok", "results": results}


@app.get("/destinations")
async def list_destinations():
    if not _config:
        return {"destinations": []}
    return {"destinations": [{"name": d.name, "type": d.type} for d in _config.destinations]}


@app.get("/destinations/{name}/health")
async def destination_health(name: str):
    if not _config:
        return JSONResponse(status_code=404, content={"error": "Config not loaded"})

    dest = next((d for d in _config.destinations if d.name == name), None)
    if not dest:
        return JSONResponse(status_code=404, content={"error": "Destination not found"})

    return {"name": name, "type": dest.type, "status": "configured"}


@app.get("/state")
async def get_state():
    if not _state_manager:
        return {"error": "State manager not initialized"}

    return {
        "queue_size": await _state_manager.get_queue_size(),
    }


metrics_app = make_asgi_app(registry=_metrics.registry if _metrics else None)
app.mount("/metrics", metrics_app)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
