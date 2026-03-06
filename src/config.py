import asyncio
import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from src.models import Config

logger = logging.getLogger(__name__)


def _expand_env_vars(data: Any) -> Any:
    """Recursively expand ${VAR_NAME} patterns in strings.

    Raises ValueError if referenced environment variable doesn't exist.
    """
    if isinstance(data, str):
        pattern = r"\$\{([^}]+)\}"
        matches = re.findall(pattern, data)
        if not matches:
            return data

        result = data
        for var_name in matches:
            if var_name not in os.environ:
                raise ValueError(
                    f"Environment variable '{var_name}' not found (required by config)"
                )
            result = result.replace(f"${{{var_name}}}", os.environ[var_name])
        return result

    elif isinstance(data, dict):
        return {k: _expand_env_vars(v) for k, v in data.items()}

    elif isinstance(data, list):
        return [_expand_env_vars(item) for item in data]

    return data


class ConfigLoader:
    def __init__(self, config_path: str, checksum_interval: int = 30):
        self.config_path = Path(config_path)
        self._config: Optional[Config] = None
        self._checksum_interval = checksum_interval
        self._reload_callback: Optional[Callable[[Config], None]] = None
        self._last_checksum: Optional[str] = None
        self._reload_task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None

    def load(self) -> Config:
        with open(self.config_path) as f:
            data = yaml.safe_load(f)
        expanded_data = _expand_env_vars(data) if data else {}
        config = Config(**expanded_data) if expanded_data else Config()
        self._config = config
        logger.info(f"Loaded config from {self.config_path}")
        return config

    def _compute_checksum(self) -> str:
        """Compute SHA-256 checksum of the config file."""
        with open(self.config_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    @property
    def config(self) -> Config:
        if self._config is None:
            return self.load()
        return self._config

    async def start_periodic_check(self, on_reload: Callable[[Config], None]):
        self._reload_callback = on_reload
        self._stop_event = asyncio.Event()
        self._last_checksum = self._compute_checksum()

        async def _periodic_check():
            while not self._stop_event.is_set():
                try:
                    await asyncio.sleep(self._checksum_interval)
                    if self._stop_event.is_set():
                        break

                    current_checksum = self._compute_checksum()
                    if current_checksum != self._last_checksum:
                        logger.info("Config file changed, reloading...")
                        try:
                            new_config = self.load()
                            if self._reload_callback:
                                self._reload_callback(new_config)
                            self._last_checksum = current_checksum
                        except Exception as e:
                            logger.error(f"Failed to reload config: {e}")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in periodic config check: {e}")

        self._reload_task = asyncio.create_task(_periodic_check())
        logger.info(f"Started periodic config reload check (interval: {self._checksum_interval}s)")

    async def stop_periodic_check(self):
        if self._stop_event:
            self._stop_event.set()
        if self._reload_task:
            self._reload_task.cancel()
            try:
                await self._reload_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped periodic config reload check")


_config_loader: Optional[ConfigLoader] = None


def init_config(
    config_path: str,
    checksum_interval: int = 30,
    on_reload: Optional[Callable[[Config], None]] = None,
) -> Config:
    global _config_loader
    _config_loader = ConfigLoader(config_path, checksum_interval)
    config = _config_loader.load()
    return config


async def start_config_reload(on_reload: Callable[[Config], None]):
    global _config_loader
    if _config_loader and on_reload:
        await _config_loader.start_periodic_check(on_reload)


async def stop_config_reload():
    global _config_loader
    if _config_loader:
        await _config_loader.stop_periodic_check()


def get_config() -> Config:
    if _config_loader is None:
        raise RuntimeError("Config not initialized")
    return _config_loader.config


def reload_config(new_config: Config):
    global _config_loader
    if _config_loader:
        _config_loader._config = new_config
