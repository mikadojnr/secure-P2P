import time
from collections import deque
from typing import Deque, Optional, Tuple

from utils.constants import (
    BANDWIDTH_POOR, BANDWIDTH_AVERAGE, BANDWIDTH_GOOD, BANDWIDTH_EXCELLENT,
    CHUNK_SIZE_POOR, CHUNK_SIZE_AVERAGE, CHUNK_SIZE_GOOD, CHUNK_SIZE_EXCELLENT
)


class BandwidthEstimator:
    """Estimates network bandwidth using moving averages and RTT measurements."""

    def __init__(self, window_size: int = 10) -> None:
        self._window_size: int = window_size
        self._throughputs: Deque[float] = deque(maxlen=window_size)
        self._rtts: Deque[float] = deque(maxlen=window_size)
        self._losses: Deque[bool] = deque(maxlen=window_size)
        self._last_measure_time: float = time.time()
        self._last_bytes: int = 0
        self._current_bw: float = 0.0
        self._avg_rtt: float = 0.0
        self._loss_rate: float = 0.0
        self._peak_bw: float = 0.0

    def record_throughput(self, bytes_count: int) -> float:
        now: float = time.time()
        elapsed: float = now - self._last_measure_time
        if elapsed <= 0:
            return self._current_bw
        instant_bw: float = bytes_count / elapsed
        self._throughputs.append(instant_bw)
        self._current_bw = sum(self._throughputs) / max(len(self._throughputs), 1)
        if instant_bw > self._peak_bw:
            self._peak_bw = instant_bw
        self._last_measure_time = now
        self._last_bytes = bytes_count
        return self._current_bw

    def record_rtt(self, rtt: float) -> None:
        self._rtts.append(rtt)
        self._avg_rtt = sum(self._rtts) / max(len(self._rtts), 1)

    def record_packet_loss(self, lost: bool) -> None:
        self._losses.append(lost)
        if len(self._losses) > 0:
            self._loss_rate = sum(1 for l in self._losses if l) / len(self._losses)

    def record_transfer(self, bytes_count: int, elapsed: float) -> None:
        if elapsed <= 0:
            return
        instant_bw: float = bytes_count / elapsed
        self._throughputs.append(instant_bw)
        self._current_bw = sum(self._throughputs) / max(len(self._throughputs), 1)

    @property
    def bandwidth(self) -> float:
        return self._current_bw

    @property
    def avg_rtt(self) -> float:
        return self._avg_rtt

    @property
    def loss_rate(self) -> float:
        return self._loss_rate

    @property
    def peak_bandwidth(self) -> float:
        return self._peak_bw

    def get_quality(self) -> str:
        bw: float = self._current_bw
        if bw >= BANDWIDTH_EXCELLENT:
            return "excellent"
        elif bw >= BANDWIDTH_GOOD:
            return "good"
        elif bw >= BANDWIDTH_AVERAGE:
            return "average"
        else:
            return "poor"

    def get_recommended_chunk_size(self) -> int:
        quality: str = self.get_quality()
        sizes: dict = {
            "poor": CHUNK_SIZE_POOR,
            "average": CHUNK_SIZE_AVERAGE,
            "good": CHUNK_SIZE_GOOD,
            "excellent": CHUNK_SIZE_EXCELLENT
        }
        return sizes.get(quality, CHUNK_SIZE_AVERAGE)

    def get_recommended_compression(self) -> str:
        quality: str = self.get_quality()
        if quality == "excellent":
            return "fast"
        elif quality == "good":
            return "balanced"
        else:
            return "maximum"

    def get_estimated_capacity(self) -> float:
        effective_bw: float = self._current_bw * (1.0 - self._loss_rate)
        return max(effective_bw, 0)

    def should_throttle(self) -> bool:
        return self._loss_rate > 0.05

    def reset(self) -> None:
        self._throughputs.clear()
        self._rtts.clear()
        self._losses.clear()
        self._current_bw = 0.0
        self._avg_rtt = 0.0
        self._loss_rate = 0.0
        self._peak_bw = 0.0

    def get_statistics(self) -> dict:
        return {
            "bandwidth": self._current_bw,
            "avg_rtt": self._avg_rtt,
            "loss_rate": self._loss_rate,
            "peak_bw": self._peak_bw,
            "quality": self.get_quality(),
            "recommended_chunk": self.get_recommended_chunk_size(),
            "recommended_compression": self.get_recommended_compression()
        }
