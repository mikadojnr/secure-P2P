#!/usr/bin/env python3
"""
Secure Peer-to-Peer File Sharing Desktop Application
with End-to-End Encryption for Low-Bandwidth Networks

Copyright (c) 2026 Research Project
License: Academic Use Only
"""

import sys
import os
import logging
from typing import Optional

from utils.config import ConfigManager
from utils.constants import APP_NAME, APP_VERSION


def setup_environment() -> None:
    """Configure runtime environment."""
    from utils.constants import DB_DIR, LOG_DIR
    os.makedirs(DB_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)


def main() -> int:
    """Application entry point."""
    setup_environment()

    config: ConfigManager = ConfigManager()

    logging.getLogger().setLevel(
        getattr(logging, config.log_level.upper(), logging.DEBUG)
    )

    from storage.logger import AppLogger
    logger: AppLogger = AppLogger()
    logger.info(f"{APP_NAME} v{APP_VERSION} initializing...")
    logger.info(f"Python: {sys.version}")
    logger.info(f"Platform: {sys.platform}")

    try:
        from gui.main_window import run_gui
        run_gui(config)
        return 0
    except ImportError as e:
        logger.critical(f"Failed to import GUI dependencies: {e}")
        print(f"Error: {e}")
        print("Please install required packages: pip install -r requirements.txt")
        return 1
    except Exception as e:
        logger.critical(f"Application error: {e}", exc_info=True)
        print(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
