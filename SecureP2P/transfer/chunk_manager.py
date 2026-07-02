import logging
import os
import threading
from typing import Dict, List, Optional

from storage.database import DatabaseManager
from storage.models import ChunkState, Transfer
from utils.constants import (
    CHUNK_STATE_ACKED, CHUNK_STATE_FAILED, CHUNK_STATE_PENDING, CHUNK_STATE_SENT,
    TRANSFER_STATE_PENDING, TRANSFER_DIRECTION_SEND, TRANSFER_DIRECTION_RECEIVE
)
from utils.helpers import create_id, get_file_hash

logger = logging.getLogger(__name__)


class ChunkManager:
    """Manages file chunking, tracking, and reassembly."""

    def __init__(self) -> None:
        self._chunks: Dict[str, List[ChunkState]] = {}
        self._chunk_data: Dict[str, Dict[int, bytes]] = {}
        self._temp_files: Dict[str, str] = {}
        self._lock: threading.Lock = threading.Lock()
        self._db: DatabaseManager = DatabaseManager()

    def init_send(self, transfer_id: str, file_path: str, chunk_size: int) -> List[ChunkState]:
        file_size: int = os.path.getsize(file_path)
        num_chunks: int = (file_size + chunk_size - 1) // chunk_size
        chunks: List[ChunkState] = []
        self._ensure_parent_transfer(transfer_id, os.path.basename(file_path), file_size,
                                      chunk_size, TRANSFER_DIRECTION_SEND)
        with self._lock:
            for i in range(num_chunks):
                offset: int = i * chunk_size
                size: int = min(chunk_size, file_size - offset)
                chunk = ChunkState(
                    chunk_id=create_id(),
                    transfer_id=transfer_id,
                    index=i,
                    offset=offset,
                    size=size,
                    state=CHUNK_STATE_PENDING
                )
                chunks.append(chunk)
            self._chunks[transfer_id] = chunks
            self._temp_files[transfer_id] = file_path
        self._db.save_chunks(chunks)
        logger.debug(f"Initialized send for {transfer_id}: {num_chunks} chunks of {chunk_size}")
        return chunks

    def init_receive(self, transfer_id: str, file_size: int, chunk_size: int) -> List[ChunkState]:
        num_chunks: int = (file_size + chunk_size - 1) // chunk_size
        chunks: List[ChunkState] = []
        self._ensure_parent_transfer(transfer_id, "pending_file", file_size,
                                      chunk_size, TRANSFER_DIRECTION_RECEIVE)
        with self._lock:
            for i in range(num_chunks):
                offset: int = i * chunk_size
                size: int = min(chunk_size, file_size - offset)
                chunk = ChunkState(
                    chunk_id=create_id(),
                    transfer_id=transfer_id,
                    index=i,
                    offset=offset,
                    size=size,
                    state=CHUNK_STATE_PENDING
                )
                chunks.append(chunk)
            self._chunks[transfer_id] = chunks
            self._chunk_data[transfer_id] = {}
        self._db.save_chunks(chunks)
        logger.debug(f"Initialized receive for {transfer_id}: {num_chunks} chunks")
        return chunks

    def _ensure_parent_transfer(self, transfer_id: str, file_name: str,
                                 file_size: int, chunk_size: int,
                                 direction: str) -> None:
        existing = self._db.get_transfer(transfer_id)
        if existing is None:
            transfer = Transfer(
                transfer_id=transfer_id,
                file_name=file_name,
                file_size=file_size,
                chunk_size=chunk_size,
                direction=direction,
                state=TRANSFER_STATE_PENDING,
                bytes_total=file_size
            )
            self._db.save_transfer(transfer)

    def get_next_pending_chunk(self, transfer_id: str) -> Optional[ChunkState]:
        chunks: Optional[List[ChunkState]] = self._chunks.get(transfer_id)
        if not chunks:
            return None
        for chunk in chunks:
            if chunk.state == CHUNK_STATE_PENDING:
                chunk.state = CHUNK_STATE_SENT
                return chunk
            if chunk.state == CHUNK_STATE_FAILED:
                if chunk.retry_count < 5:
                    chunk.state = CHUNK_STATE_SENT
                    chunk.retry_count += 1
                    return chunk
        return None

    def read_chunk_data(self, transfer_id: str, chunk_index: int) -> bytes:
        file_path: Optional[str] = self._temp_files.get(transfer_id)
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found for transfer {transfer_id}")
        chunks: Optional[List[ChunkState]] = self._chunks.get(transfer_id)
        if not chunks or chunk_index >= len(chunks):
            raise IndexError(f"Chunk index {chunk_index} out of range")
        chunk: ChunkState = chunks[chunk_index]
        with open(file_path, "rb") as f:
            f.seek(chunk.offset)
            return f.read(chunk.size)

    def receive_chunk(self, transfer_id: str, chunk_index: int, data: bytes) -> None:
        with self._lock:
            if transfer_id not in self._chunk_data:
                self._chunk_data[transfer_id] = {}
            self._chunk_data[transfer_id][chunk_index] = data
            chunks: Optional[List[ChunkState]] = self._chunks.get(transfer_id)
            if chunks and chunk_index < len(chunks):
                chunks[chunk_index].state = CHUNK_STATE_ACKED
                self._db.update_chunk_state(chunks[chunk_index].chunk_id, CHUNK_STATE_ACKED)

    def ack_chunk(self, transfer_id: str, chunk_index: int) -> None:
        chunks: Optional[List[ChunkState]] = self._chunks.get(transfer_id)
        if chunks and chunk_index < len(chunks):
            chunks[chunk_index].state = CHUNK_STATE_ACKED
            self._db.update_chunk_state(chunks[chunk_index].chunk_id, CHUNK_STATE_ACKED)

    def mark_chunk_failed(self, transfer_id: str, chunk_index: int) -> None:
        chunks: Optional[List[ChunkState]] = self._chunks.get(transfer_id)
        if chunks and chunk_index < len(chunks):
            chunks[chunk_index].state = CHUNK_STATE_FAILED
            chunks[chunk_index].retry_count += 1
            self._db.update_chunk_state(
                chunks[chunk_index].chunk_id,
                CHUNK_STATE_FAILED,
                retry_count=chunks[chunk_index].retry_count
            )

    def assemble_file(self, transfer_id: str, output_path: str) -> bool:
        chunk_data: Optional[Dict[int, bytes]] = self._chunk_data.get(transfer_id)
        if not chunk_data:
            logger.error(f"No chunk data for {transfer_id}")
            return False
        chunks: Optional[List[ChunkState]] = self._chunks.get(transfer_id)
        if not chunks:
            logger.error(f"No chunk metadata for {transfer_id}")
            return False
        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "wb") as f:
                for i in range(len(chunks)):
                    data: Optional[bytes] = chunk_data.get(i)
                    if data is None:
                        logger.error(f"Missing chunk {i} for {transfer_id}")
                        return False
                    f.write(data)
            logger.info(f"File assembled: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to assemble file {output_path}: {e}")
            return False

    def get_chunk_progress(self, transfer_id: str) -> tuple:
        chunks: Optional[List[ChunkState]] = self._chunks.get(transfer_id)
        if not chunks:
            return 0, 0
        total: int = len(chunks)
        acked: int = sum(1 for c in chunks if c.state == CHUNK_STATE_ACKED)
        failed: int = sum(1 for c in chunks if c.state == CHUNK_STATE_FAILED)
        return acked, total, failed

    def get_pending_chunks(self, transfer_id: str) -> List[int]:
        chunks: Optional[List[ChunkState]] = self._chunks.get(transfer_id)
        if not chunks:
            return []
        return [c.index for c in chunks if c.state in (CHUNK_STATE_PENDING, CHUNK_STATE_FAILED)]

    def get_chunks_for_transfer(self, transfer_id: str) -> List[ChunkState]:
        return list(self._chunks.get(transfer_id, []))

    def cleanup(self, transfer_id: str) -> None:
        with self._lock:
            self._chunks.pop(transfer_id, None)
            self._chunk_data.pop(transfer_id, None)
            self._temp_files.pop(transfer_id, None)
        self._db.delete_transfer_chunks(transfer_id)
