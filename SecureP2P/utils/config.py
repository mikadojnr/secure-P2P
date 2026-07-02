import json
import os
from typing import Any, Dict, Optional

from utils.constants import (
    DB_DIR, DEFAULT_DOWNLOAD_DIR, DEFAULT_CHUNK_SIZE,
    DEFAULT_COMPRESSION, DEFAULT_MAX_BANDWIDTH, DEFAULT_AUTO_RECONNECT,
    DEFAULT_PEER_TIMEOUT, DEFAULT_DARK_MODE, CHUNK_SIZES, COMPRESSION_LEVELS
)


class ConfigManager:
    """Manages application configuration with JSON persistence."""

    _instance: Optional["ConfigManager"] = None

    def __new__(cls) -> "ConfigManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._config_path: str = os.path.join(DB_DIR, "config.json")
        self._config: Dict[str, Any] = self._load_defaults()
        self._initialized: bool = True
        os.makedirs(DB_DIR, exist_ok=True)
        self.load()

    def _load_defaults(self) -> Dict[str, Any]:
        return {
            "download_dir": DEFAULT_DOWNLOAD_DIR,
            "chunk_size": DEFAULT_CHUNK_SIZE,
            "compression": DEFAULT_COMPRESSION,
            "max_bandwidth": DEFAULT_MAX_BANDWIDTH,
            "auto_reconnect": DEFAULT_AUTO_RECONNECT,
            "peer_timeout": DEFAULT_PEER_TIMEOUT,
            "connect_timeout": 30.0,
            "max_connect_retries": 3,
            "dark_mode": DEFAULT_DARK_MODE,
            "database_path": os.path.join(DB_DIR, "securep2p.db"),
            "log_level": "DEBUG",
            "max_peers": 50,
            "max_transfers": 10,
            "stun_servers": [
                "stun.l.google.com:19302",
                "stun1.l.google.com:19302",
                "stun2.l.google.com:19302"
            ],
            "turn_servers": [],
            "saved_peers": [],
            "window_geometry": None,
            "window_state": None
        }

    def load(self) -> None:
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, "r") as f:
                    loaded: Dict = json.load(f)
                defaults = self._load_defaults()
                defaults.update(loaded)
                self._config = defaults
        except (json.JSONDecodeError, OSError) as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to load config: {e}")

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
            with open(self._config_path, "w") as f:
                json.dump(self._config, f, indent=2)
        except OSError as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to save config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._config[key] = value
        self.save()

    def get_all(self) -> Dict[str, Any]:
        return dict(self._config)

    def reset_to_defaults(self) -> None:
        self._config = self._load_defaults()
        self.save()

    @property
    def download_dir(self) -> str:
        path = self._config.get("download_dir", DEFAULT_DOWNLOAD_DIR)
        os.makedirs(path, exist_ok=True)
        return path

    @download_dir.setter
    def download_dir(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)
        self.set("download_dir", path)

    @property
    def chunk_size(self) -> int:
        return self._config.get("chunk_size", DEFAULT_CHUNK_SIZE)

    @chunk_size.setter
    def chunk_size(self, size: int) -> None:
        self.set("chunk_size", size)

    @property
    def compression(self) -> str:
        return self._config.get("compression", DEFAULT_COMPRESSION)

    @compression.setter
    def compression(self, level: str) -> None:
        if level in COMPRESSION_LEVELS:
            self.set("compression", level)

    @property
    def max_bandwidth(self) -> int:
        return self._config.get("max_bandwidth", DEFAULT_MAX_BANDWIDTH)

    @max_bandwidth.setter
    def max_bandwidth(self, bw: int) -> None:
        self.set("max_bandwidth", bw)

    @property
    def auto_reconnect(self) -> bool:
        return self._config.get("auto_reconnect", DEFAULT_AUTO_RECONNECT)

    @auto_reconnect.setter
    def auto_reconnect(self, enabled: bool) -> None:
        self.set("auto_reconnect", enabled)

    @property
    def peer_timeout(self) -> float:
        return float(self._config.get("peer_timeout", DEFAULT_PEER_TIMEOUT))

    @peer_timeout.setter
    def peer_timeout(self, timeout: float) -> None:
        self.set("peer_timeout", timeout)

    @property
    def dark_mode(self) -> bool:
        return self._config.get("dark_mode", DEFAULT_DARK_MODE)

    @dark_mode.setter
    def dark_mode(self, enabled: bool) -> None:
        self.set("dark_mode", enabled)

    @property
    def database_path(self) -> str:
        return self._config.get("database_path", os.path.join(DB_DIR, "securep2p.db"))

    @database_path.setter
    def database_path(self, path: str) -> None:
        self.set("database_path", path)

    @property
    def log_level(self) -> str:
        return self._config.get("log_level", "DEBUG")

    @log_level.setter
    def log_level(self, level: str) -> None:
        self.set("log_level", level)

    @property
    def connect_timeout(self) -> float:
        return float(self._config.get("connect_timeout", 30.0))

    @connect_timeout.setter
    def connect_timeout(self, timeout: float) -> None:
        self.set("connect_timeout", timeout)

    @property
    def max_connect_retries(self) -> int:
        return int(self._config.get("max_connect_retries", 3))

    @max_connect_retries.setter
    def max_connect_retries(self, retries: int) -> None:
        self.set("max_connect_retries", retries)
