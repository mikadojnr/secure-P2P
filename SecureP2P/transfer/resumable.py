import json
import logging
import os
import time
from typing import Dict, List, Optional, Tuple

from storage.database import DatabaseManager
from storage.models import ChunkState, Transfer
from utils.constants import (
    CHUNK_STATE_ACKED, CHUNK_STATE_FAILED, CHUNK_STATE_PENDING,
    DB_DIR, TRANSFER_STATE_IN_PROGRESS, TRANSFER_STATE_PAUSED
)

logger = logging.getLogger(__name__)


class ResumableTransfer:
    """Manages transfer resume state persistence and recovery."""

    def __init__(self) -> None:
        self._db: DatabaseManager = DatabaseManager()
        self._resume_dir: str = os.path.join(DB_DIR, "resume")
        os.makedirs(self._resume_dir, exist_ok=True)

    def save_state(self, transfer: Transfer, chunks: List[ChunkState]) -> None:
        state_file: str = self._get_state_file(transfer.transfer_id)
        state: dict = {
            "transfer_id": transfer.transfer_id,
            "file_name": transfer.file_name,
            "file_path": transfer.file_path,
            "file_size": transfer.file_size,
            "file_hash": transfer.file_hash,
            "chunk_size": transfer.chunk_size,
            "compressed": transfer.compressed,
            "compression_level": transfer.compression_level,
            "direction": transfer.direction,
            "peer_id": transfer.peer_id,
            "peer_name": transfer.peer_name,
            "bytes_transferred": transfer.bytes_transferred,
            "saved_at": time.time(),
            "chunks": [
                {
                    "index": c.index,
                    "offset": c.offset,
                    "size": c.size,
                    "state": c.state,
                    "hash": c.hash
                }
                for c in chunks
            ]
        }
        try:
            with open(state_file, "w") as f:
                json.dump(state, f, indent=2)
            self._db.save_transfer(transfer)
            logger.debug(f"Saved resume state for {transfer.file_name}")
        except Exception as e:
            logger.error(f"Failed to save resume state: {e}")

    def load_state(self, transfer_id: str) -> Optional[Tuple[Transfer, List[ChunkState]]]:
        state_file: str = self._get_state_file(transfer_id)
        if not os.path.exists(state_file):
            db_transfer: Optional[Transfer] = self._db.get_transfer(transfer_id)
            if db_transfer:
                db_chunks: List[ChunkState] = self._db.get_chunks(transfer_id)
                if db_chunks:
                    return db_transfer, db_chunks
            return None
        try:
            with open(state_file, "r") as f:
                state: dict = json.load(f)
            transfer = Transfer(
                transfer_id=state["transfer_id"],
                file_name=state["file_name"],
                file_path=state["file_path"],
                file_size=state["file_size"],
                file_hash=state.get("file_hash", ""),
                chunk_size=state["chunk_size"],
                compressed=state.get("compressed", False),
                compression_level=state.get("compression_level", 3),
                direction=state["direction"],
                state=TRANSFER_STATE_PAUSED,
                peer_id=state.get("peer_id", ""),
                peer_name=state.get("peer_name", ""),
                bytes_transferred=state.get("bytes_transferred", 0),
                bytes_total=state["file_size"]
            )
            chunks: List[ChunkState] = [
                ChunkState(
                    chunk_id=f"{transfer_id}_{c['index']}",
                    transfer_id=transfer_id,
                    index=c["index"],
                    offset=c["offset"],
                    size=c["size"],
                    state=c["state"],
                    hash=c.get("hash", "")
                )
                for c in state["chunks"]
            ]
            return transfer, chunks
        except Exception as e:
            logger.error(f"Failed to load resume state: {e}")
            return None

    def get_resume_info(self, transfer_id: str) -> Optional[Dict]:
        state = self.load_state(transfer_id)
        if not state:
            return None
        transfer, chunks = state
        acked: int = sum(1 for c in chunks if c.state == CHUNK_STATE_ACKED)
        failed: int = sum(1 for c in chunks if c.state == CHUNK_STATE_FAILED)
        pending: int = sum(1 for c in chunks if c.state == CHUNK_STATE_PENDING)
        total: int = len(chunks)
        return {
            "transfer_id": transfer_id,
            "file_name": transfer.file_name,
            "file_size": transfer.file_size,
            "transferred": transfer.bytes_transferred,
            "progress": (transfer.bytes_transferred / transfer.file_size * 100) if transfer.file_size > 0 else 0,
            "direction": transfer.direction,
            "peer_name": transfer.peer_name,
            "total_chunks": total,
            "acked_chunks": acked,
            "failed_chunks": failed,
            "pending_chunks": pending,
            "can_resume": total > 0 and (acked + pending) > 0
        }

    def get_resumable_transfers(self) -> List[Dict]:
        transfers: List[Transfer] = self._db.get_active_transfers()
        resumable: List[Dict] = []
        for t in transfers:
            if t.state == TRANSFER_STATE_PAUSED:
                info: Optional[Dict] = self.get_resume_info(t.transfer_id)
                if info:
                    resumable.append(info)
        return resumable

    def delete_state(self, transfer_id: str) -> None:
        state_file: str = self._get_state_file(transfer_id)
        try:
            if os.path.exists(state_file):
                os.remove(state_file)
        except Exception as e:
            logger.error(f"Failed to delete resume state: {e}")

    def _get_state_file(self, transfer_id: str) -> str:
        return os.path.join(self._resume_dir, f"{transfer_id}.json")

    def cleanup_old_states(self, max_age_days: int = 7) -> int:
        removed: int = 0
        now: float = time.time()
        max_age: float = max_age_days * 86400
        try:
            for filename in os.listdir(self._resume_dir):
                if filename.endswith(".json"):
                    filepath: str = os.path.join(self._resume_dir, filename)
                    age: float = now - os.path.getmtime(filepath)
                    if age > max_age:
                        os.remove(filepath)
                        removed += 1
        except Exception as e:
            logger.error(f"Failed to cleanup old states: {e}")
        return removed
