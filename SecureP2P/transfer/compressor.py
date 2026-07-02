import logging
from typing import Optional

import pyzstd

from utils.constants import COMPRESSION_BALANCED, COMPRESSION_FAST, COMPRESSION_MAXIMUM, COMPRESSION_LEVELS

logger = logging.getLogger(__name__)


class Compressor:
    """Zstandard compression with dynamic level selection."""

    def __init__(self, default_level: int = COMPRESSION_BALANCED) -> None:
        self._default_level: int = default_level
        self._total_original: int = 0
        self._total_compressed: int = 0

    def compress(self, data: bytes, level: Optional[int] = None) -> bytes:
        compression_level: int = level if level is not None else self._default_level
        try:
            compressed: bytes = pyzstd.compress(data, compression_level)
            self._total_original += len(data)
            self._total_compressed += len(compressed)
            return compressed
        except Exception as e:
            logger.error(f"Compression failed: {e}")
            return data

    def decompress(self, data: bytes) -> bytes:
        try:
            return pyzstd.decompress(data)
        except Exception as e:
            logger.error(f"Decompression failed: {e}")
            return data

    def get_ratio(self) -> float:
        if self._total_original <= 0:
            return 1.0
        return self._total_compressed / self._total_original

    def get_savings(self) -> float:
        ratio: float = self.get_ratio()
        return (1.0 - ratio) * 100.0

    def select_level(self, bandwidth_quality: str) -> int:
        level_map: dict = {
            "excellent": COMPRESSION_FAST,
            "good": COMPRESSION_BALANCED,
            "average": COMPRESSION_MAXIMUM,
            "poor": COMPRESSION_MAXIMUM
        }
        return level_map.get(bandwidth_quality, self._default_level)

    def reset_stats(self) -> None:
        self._total_original = 0
        self._total_compressed = 0

    @property
    def statistics(self) -> dict:
        return {
            "total_original": self._total_original,
            "total_compressed": self._total_compressed,
            "ratio": self.get_ratio(),
            "savings": self.get_savings()
        }

    def should_compress(self, data_size: int, bandwidth_quality: str) -> bool:
        if data_size < 256:
            return False
        if bandwidth_quality in ("poor", "average"):
            return True
        if bandwidth_quality == "good" and data_size > 4096:
            return True
        return False
