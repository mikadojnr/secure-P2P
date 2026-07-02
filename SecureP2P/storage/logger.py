import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

from utils.constants import LOG_DIR, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT


class AppLogger:
    """Centralized application logger with file and console handlers."""

    _instance: Optional["AppLogger"] = None

    def __new__(cls) -> "AppLogger":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._log_dir: str = LOG_DIR
        os.makedirs(self._log_dir, exist_ok=True)
        self._logger: logging.Logger = logging.getLogger("SecureP2P")
        self._logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.DEBUG))
        self._logger.handlers.clear()
        self._setup_file_handler()
        self._setup_console_handler()
        self._initialized: bool = True

    def _setup_file_handler(self) -> None:
        log_file: str = os.path.join(self._log_dir, "securep2p.log")
        handler = RotatingFileHandler(
            log_file,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8"
        )
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        self._logger.addHandler(handler)

    def _setup_console_handler(self) -> None:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        self._logger.addHandler(handler)

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    def debug(self, msg: str, *args, **kwargs) -> None:
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        self._logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs) -> None:
        self._logger.critical(msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs) -> None:
        self._logger.exception(msg, *args, **kwargs)

    def get_log_path(self) -> str:
        return os.path.join(self._log_dir, "securep2p.log")

    def get_recent_logs(self, lines: int = 100) -> list:
        log_file = self.get_log_path()
        if not os.path.exists(log_file):
            return []
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                all_lines: list = f.readlines()
            return all_lines[-lines:]
        except Exception:
            return []
