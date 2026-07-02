import asyncio
import heapq
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from utils.constants import MAX_QUEUE_SIZE, MAX_TRANSFERS

logger = logging.getLogger(__name__)


@dataclass(order=True)
class TransferJob:
    """Represents a scheduled transfer job with priority."""
    priority: int = field(compare=True)
    timestamp: float = field(compare=True)
    transfer_id: str = field(compare=False)
    peer_id: str = field(compare=False)
    file_name: str = field(compare=False)
    file_size: int = field(compare=False)
    callback: Optional[Callable] = field(compare=False, default=None)


class TransferScheduler:
    """Schedules and manages transfer queue with priority handling."""

    def __init__(self) -> None:
        self._queue: List[TransferJob] = []
        self._active: Dict[str, TransferJob] = {}
        self._running: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()
        self._on_job_start: Optional[Callable] = None
        self._on_job_complete: Optional[Callable] = None

    def set_callbacks(self, on_start: Optional[Callable] = None,
                       on_complete: Optional[Callable] = None) -> None:
        self._on_job_start = on_start
        self._on_job_complete = on_complete

    async def add_job(self, transfer_id: str, peer_id: str, file_name: str,
                       file_size: int, priority: int = 0,
                       callback: Optional[Callable] = None) -> bool:
        async with self._lock:
            if len(self._queue) + len(self._active) >= MAX_QUEUE_SIZE:
                logger.warning(f"Queue full, cannot add {file_name}")
                return False
            job: TransferJob = TransferJob(
                priority=priority,
                timestamp=time.time(),
                transfer_id=transfer_id,
                peer_id=peer_id,
                file_name=file_name,
                file_size=file_size,
                callback=callback
            )
            heapq.heappush(self._queue, job)
            logger.info(f"Added job to queue: {file_name} (priority {priority})")
            return True

    async def process_queue(self) -> None:
        while self._running:
            async with self._lock:
                if len(self._active) >= MAX_TRANSFERS:
                    await asyncio.sleep(1)
                    continue
                if not self._queue:
                    await asyncio.sleep(1)
                    continue
                job: TransferJob = heapq.heappop(self._queue)
                if job.transfer_id not in self._active:
                    self._active[job.transfer_id] = job
                    logger.info(f"Starting job: {job.file_name}")
                    if self._on_job_start:
                        try:
                            await self._on_job_start(job)
                        except Exception as e:
                            logger.error(f"Job start callback failed: {e}")
            await asyncio.sleep(0.5)

    async def complete_job(self, transfer_id: str) -> None:
        async with self._lock:
            job: Optional[TransferJob] = self._active.pop(transfer_id, None)
            if job and job.callback:
                try:
                    await job.callback(job)
                except Exception as e:
                    logger.error(f"Job completion callback failed: {e}")
            if self._on_job_complete:
                try:
                    await self._on_job_complete(job)
                except Exception as e:
                    logger.error(f"Job complete callback failed: {e}")

    async def remove_job(self, transfer_id: str) -> bool:
        async with self._lock:
            if transfer_id in self._active:
                self._active.pop(transfer_id)
                return True
            for i, job in enumerate(self._queue):
                if job.transfer_id == transfer_id:
                    self._queue.pop(i)
                    heapq.heapify(self._queue)
                    return True
        return False

    def get_queue_size(self) -> int:
        return len(self._queue)

    def get_active_count(self) -> int:
        return len(self._active)

    def get_queue(self) -> List[TransferJob]:
        return sorted(self._queue)

    def get_active_jobs(self) -> Dict[str, TransferJob]:
        return dict(self._active)

    def is_queued(self, transfer_id: str) -> bool:
        return any(j.transfer_id == transfer_id for j in self._queue)

    def is_active(self, transfer_id: str) -> bool:
        return transfer_id in self._active

    async def clear_queue(self) -> None:
        async with self._lock:
            self._queue.clear()

    async def start(self) -> None:
        self._running = True
        asyncio.create_task(self.process_queue())
        logger.info("Transfer scheduler started")

    async def stop(self) -> None:
        self._running = False
        async with self._lock:
            self._queue.clear()
            self._active.clear()
        logger.info("Transfer scheduler stopped")
