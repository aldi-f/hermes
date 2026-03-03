import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

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
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self._config: Optional[Config] = None
        self._observer: Optional[Observer] = None
        self._reload_callback: Optional[Callable[[Config], None]] = None

    def load(self) -> Config:
        with open(self.config_path) as f:
            data = yaml.safe_load(f)
        expanded_data = _expand_env_vars(data) if data else {}
        config = Config(**expanded_data) if expanded_data else Config()
        self._config = config
        logger.info(f"Loaded config from {self.config_path}")
        return config

    @property
    def config(self) -> Config:
        if self._config is None:
            return self.load()
        return self._config

    def start_watching(self, on_reload: Callable[[Config], None]):
        self._reload_callback = on_reload

        class ConfigFileHandler(FileSystemEventHandler):
            def __init__(inner_self, loader: ConfigLoader):
                inner_self.loader = loader
                inner_self._reloading = False

            def on_modified(inner_self, event):
                if event.src_path == str(inner_self.loader.config_path):
                    inner_self._reload()

            def on_created(inner_self, event):
                if event.src_path == str(inner_self.loader.config_path):
                    inner_self._reload()

            def _reload(inner_self):
                import threading

                if inner_self._reloading:
                    return
                inner_self._reloading = True

                def do_reload():
                    try:
                        new_config = inner_self.loader.load()
                        if inner_self.loader._reload_callback:
                            inner_self.loader._reload_callback(new_config)
                    except Exception as e:
                        logger.error(f"Failed to reload config: {e}")
                    finally:
                        inner_self._reloading = False

                threading.Timer(1.0, do_reload).start()

        self._observer = Observer()
        self._observer.schedule(
            ConfigFileHandler(self),
            str(self.config_path.parent),
            recursive=False,
        )
        self._observer.start()
        logger.info(f"Started watching {self.config_path}")

    def stop_watching(self):
        if self._observer:
            self._observer.stop()
            self._observer.join()
            logger.info("Stopped watching config file")


_config_loader: Optional[ConfigLoader] = None


def init_config(
    config_path: str,
    enable_watch: bool = True,
    on_reload: Optional[Callable[[Config], None]] = None,
) -> Config:
    global _config_loader
    _config_loader = ConfigLoader(config_path)
    config = _config_loader.load()

    if enable_watch and on_reload:
        _config_loader.start_watching(on_reload)

    return config


def get_config() -> Config:
    if _config_loader is None:
        raise RuntimeError("Config not initialized")
    return _config_loader.config


def reload_config(new_config: Config):
    global _config_loader
    if _config_loader:
        _config_loader._config = new_config
