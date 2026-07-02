import asyncio
import base64
import json
import logging
import os
import time
from typing import Callable, Dict, Optional

from crypto.hashing import Hasher
from network.bandwidth_estimator import BandwidthEstimator
from network.connection_manager import (
    ConnectionManager, MSG_TYPE_DATA, MSG_TYPE_DATA_ACK,
    MSG_TYPE_FILE_META, MSG_TYPE_FILE_CHUNK, MSG_TYPE_FILE_ACK,
    MSG_TYPE_FILE_REQUEST, MSG_TYPE_FILE_RESPONSE, SecureConnection
)
from storage.database import DatabaseManager
from storage.models import ChunkState, Peer, Transfer, TransferHistory
from transfer.chunk_manager import ChunkManager
from transfer.compressor import Compressor
from transfer.resumable import ResumableTransfer
from transfer.scheduler import TransferScheduler
from utils.constants import (
    CHUNK_SIZE_AVERAGE, COMPRESSION_LEVELS,
    TRANSFER_DIRECTION_RECEIVE, TRANSFER_DIRECTION_SEND,
    TRANSFER_STATE_CANCELLED, TRANSFER_STATE_COMPLETED, TRANSFER_STATE_FAILED,
    TRANSFER_STATE_IN_PROGRESS, TRANSFER_STATE_PAUSED, TRANSFER_STATE_PENDING
)
from utils.helpers import create_id, format_speed, get_timestamp

logger = logging.getLogger(__name__)


class TransferController:
    """Controls file transfers between peers."""

    def __init__(self, connection_manager: ConnectionManager,
                 peer_id: str, display_name: str) -> None:
        self._cm: ConnectionManager = connection_manager
        self._peer_id: str = peer_id
        self._display_name: str = display_name
        self._db: DatabaseManager = DatabaseManager()
        self._chunk_manager: ChunkManager = ChunkManager()
        self._compressor: Compressor = Compressor()
        self._scheduler: TransferScheduler = TransferScheduler()
        self._active_transfers: Dict[str, Transfer] = {}
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._running: bool = False
        self._on_transfer_update: Optional[Callable] = None
        self._on_transfer_complete: Optional[Callable] = None
        self._on_incoming_request: Optional[Callable] = None
        self._register_handlers()

    def set_update_callback(self, callback: Optional[Callable] = None) -> None:
        self._on_transfer_update = callback

    def set_complete_callback(self, callback: Optional[Callable] = None) -> None:
        self._on_transfer_complete = callback

    def set_incoming_callback(self, callback: Optional[Callable] = None) -> None:
        self._on_incoming_request = callback

    def _register_handlers(self) -> None:
        self._cm.register_handler(MSG_TYPE_FILE_META, self._handle_file_meta)
        self._cm.register_handler(MSG_TYPE_FILE_CHUNK, self._handle_file_chunk)
        self._cm.register_handler(MSG_TYPE_FILE_ACK, self._handle_file_ack)
        self._cm.register_handler(MSG_TYPE_FILE_REQUEST, self._handle_file_request)
        self._cm.register_handler(MSG_TYPE_FILE_RESPONSE, self._handle_file_response)
        self._cm.register_handler(MSG_TYPE_DATA, self._handle_data)
        self._cm.register_handler(MSG_TYPE_DATA_ACK, self._handle_data_ack)

    async def _handle_data(self, conn: SecureConnection, payload: bytes) -> None:
        data: dict = json.loads(payload.decode())
        transfer_id: str = data.get("transfer_id", "")
        action: str = data.get("action", "")
        if transfer_id in self._active_transfers:
            transfer: Transfer = self._active_transfers[transfer_id]
            if action == "pause":
                transfer.state = TRANSFER_STATE_PAUSED
                self._db.update_transfer_state(transfer_id, TRANSFER_STATE_PAUSED)
                self._notify_update(transfer)
            elif action == "resume":
                transfer.state = TRANSFER_STATE_IN_PROGRESS
                self._db.update_transfer_state(transfer_id, TRANSFER_STATE_IN_PROGRESS)
                self._notify_update(transfer)
            elif action == "cancel":
                transfer.state = TRANSFER_STATE_CANCELLED
                self._db.update_transfer_state(transfer_id, TRANSFER_STATE_CANCELLED)
                self._notify_update(transfer)
                self._cleanup_transfer(transfer_id)

    async def _handle_data_ack(self, conn: SecureConnection, payload: bytes) -> None:
        data: dict = json.loads(payload.decode())
        transfer_id: str = data.get("transfer_id", "")
        action: str = data.get("action", "")
        success: bool = data.get("success", False)
        if transfer_id in self._pending_requests:
            future: asyncio.Future = self._pending_requests[transfer_id]
            if not future.done():
                future.set_result({"action": action, "success": success})

    async def _handle_file_meta(self, conn: SecureConnection, payload: bytes) -> None:
        try:
            meta: dict = json.loads(payload.decode())
            transfer_id: str = meta.get("transfer_id", create_id())
            file_name: str = meta.get("file_name", "unknown")
            file_size: int = meta.get("file_size", 0)
            file_hash: str = meta.get("file_hash", "")
            chunk_size: int = meta.get("chunk_size", CHUNK_SIZE_AVERAGE)
            compressed: bool = meta.get("compressed", False)
            compression_level: int = meta.get("compression_level", 3)
            num_chunks: int = meta.get("num_chunks", 0)
            transfer = Transfer(
                transfer_id=transfer_id,
                file_name=file_name,
                file_path="",
                file_size=file_size,
                file_hash=file_hash,
                chunk_size=chunk_size,
                compressed=compressed,
                compression_level=compression_level,
                direction=TRANSFER_DIRECTION_RECEIVE,
                state=TRANSFER_STATE_PENDING,
                peer_id=conn.peer.peer_id,
                peer_name=conn.peer.display_name,
                bytes_total=file_size,
                started_at=get_timestamp()
            )
            self._active_transfers[transfer_id] = transfer
            self._db.save_transfer(transfer)
            if self._on_incoming_request:
                self._on_incoming_request(transfer)
            logger.info(f"File meta received: {file_name} ({file_size} bytes) from {conn.peer.display_name}")
        except Exception as e:
            logger.error(f"Error handling file meta: {e}")

    async def _handle_file_chunk(self, conn: SecureConnection, payload: bytes) -> None:
        try:
            data: dict = json.loads(payload.decode())
            transfer_id: str = data.get("transfer_id", "")
            chunk_index: int = data.get("chunk_index", 0)
            chunk_data_b64: str = data.get("data", "")
            chunk_hash: str = data.get("hash", "")
            chunk_bytes: bytes = base64.b64decode(chunk_data_b64)
            transfer: Optional[Transfer] = self._active_transfers.get(transfer_id)
            if not transfer:
                logger.warning(f"No active transfer {transfer_id}")
                return
            if not Hasher.verify_hash(chunk_bytes, chunk_hash):
                logger.warning(f"Chunk {chunk_index} hash mismatch for {transfer.file_name}")
                ack: dict = {
                    "transfer_id": transfer_id,
                    "chunk_index": chunk_index,
                    "status": "fail",
                    "reason": "hash_mismatch"
                }
                await conn.send_message(MSG_TYPE_FILE_ACK, json.dumps(ack).encode())
                return
            self._chunk_manager.receive_chunk(transfer_id, chunk_index, chunk_bytes)
            transfer.bytes_transferred += len(chunk_bytes)
            transfer.progress = (transfer.bytes_transferred / transfer.bytes_total * 100) if transfer.bytes_total > 0 else 0
            conn.bandwidth_estimator.record_throughput(len(chunk_bytes))
            transfer.speed = conn.bandwidth_estimator.bandwidth
            self._db.update_transfer_state(
                transfer_id, TRANSFER_STATE_IN_PROGRESS,
                bytes_transferred=transfer.bytes_transferred,
                speed=transfer.speed
            )
            ack = {
                "transfer_id": transfer_id,
                "chunk_index": chunk_index,
                "status": "ok"
            }
            await conn.send_message(MSG_TYPE_FILE_ACK, json.dumps(ack).encode())
            self._notify_update(transfer)
            acked, total, _ = self._chunk_manager.get_chunk_progress(transfer_id)
            if acked >= total:
                output_path: str = transfer.file_path or os.path.join(
                    os.path.expanduser("~"), "Downloads", transfer.file_name
                )
                if self._chunk_manager.assemble_file(transfer_id, output_path):
                    transfer.state = TRANSFER_STATE_COMPLETED
                    transfer.completed_at = get_timestamp()
                    self._db.update_transfer_state(
                        transfer_id, TRANSFER_STATE_COMPLETED
                    )
                    self._add_to_history(transfer)
                    self._notify_update(transfer)
                    logger.info(f"Transfer completed: {transfer.file_name}")
                    if self._on_transfer_complete:
                        self._on_transfer_complete(transfer)
        except Exception as e:
            logger.error(f"Error handling file chunk: {e}")

    async def _handle_file_ack(self, conn: SecureConnection, payload: bytes) -> None:
        try:
            data: dict = json.loads(payload.decode())
            transfer_id: str = data.get("transfer_id", "")
            chunk_index: int = data.get("chunk_index", 0)
            status: str = data.get("status", "fail")
            transfer: Optional[Transfer] = self._active_transfers.get(transfer_id)
            if not transfer:
                return
            if status == "ok":
                self._chunk_manager.ack_chunk(transfer_id, chunk_index)
            else:
                self._chunk_manager.mark_chunk_failed(transfer_id, chunk_index)
                logger.debug(f"Chunk {chunk_index} failed for {transfer.file_name}: {data.get('reason', 'unknown')}")
            self._notify_update(transfer)
        except Exception as e:
            logger.error(f"Error handling file ack: {e}")

    async def _handle_file_request(self, conn: SecureConnection, payload: bytes) -> None:
        try:
            data: dict = json.loads(payload.decode())
            transfer_id: str = data.get("transfer_id", "")
            accepted: bool = data.get("accepted", False)
            transfer: Optional[Transfer] = self._active_transfers.get(transfer_id)
            if not transfer:
                logger.warning(f"No transfer found for request: {transfer_id}")
                return
            if accepted:
                transfer.state = TRANSFER_STATE_IN_PROGRESS
                self._db.save_transfer(transfer)
                self._notify_update(transfer)
                asyncio.create_task(self._send_file_chunks(transfer, conn))
            else:
                transfer.state = TRANSFER_STATE_CANCELLED
                self._db.update_transfer_state(transfer_id, TRANSFER_STATE_CANCELLED)
                self._notify_update(transfer)
        except Exception as e:
            logger.error(f"Error handling file request: {e}")

    async def _handle_file_response(self, conn: SecureConnection, payload: bytes) -> None:
        try:
            data: dict = json.loads(payload.decode())
            transfer_id: str = data.get("transfer_id", "")
            accepted: bool = data.get("accepted", False)
            transfer: Optional[Transfer] = self._active_transfers.get(transfer_id)
            if not transfer:
                return
            if accepted:
                transfer.state = TRANSFER_STATE_IN_PROGRESS
                self._db.save_transfer(transfer)
                asyncio.create_task(self._send_file_chunks(transfer, conn))
            else:
                transfer.state = TRANSFER_STATE_CANCELLED
                self._db.update_transfer_state(transfer_id, TRANSFER_STATE_CANCELLED)
                self._notify_update(transfer)
        except Exception as e:
            logger.error(f"Error handling file response: {e}")

    async def send_file(self, peer_id: str, file_path: str,
                         chunk_size: Optional[int] = None,
                         compressed: bool = True,
                         compression_level: Optional[int] = None) -> Optional[str]:
        conn: Optional[SecureConnection] = self._cm.get_connection(peer_id)
        if not conn or not conn.authenticated:
            logger.warning(f"Not authenticated with peer {peer_id}")
            return None
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None
        transfer_id: str = create_id()
        file_name: str = os.path.basename(file_path)
        file_size: int = os.path.getsize(file_path)
        file_hash: str = Hasher.hash_file(file_path)
        cs: int = chunk_size or conn.bandwidth_estimator.get_recommended_chunk_size()
        cl: int = compression_level or 3
        if compressed:
            cl = COMPRESSION_LEVELS.get(conn.bandwidth_estimator.get_recommended_compression(), 3)
        num_chunks: int = (file_size + cs - 1) // cs
        transfer = Transfer(
            transfer_id=transfer_id,
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            file_hash=file_hash,
            chunk_size=cs,
            compressed=compressed,
            compression_level=cl,
            direction=TRANSFER_DIRECTION_SEND,
            state=TRANSFER_STATE_PENDING,
            peer_id=peer_id,
            peer_name=conn.peer.display_name,
            bytes_total=file_size,
            started_at=get_timestamp()
        )
        self._active_transfers[transfer_id] = transfer
        self._db.save_transfer(transfer)
        meta: dict = {
            "transfer_id": transfer_id,
            "file_name": file_name,
            "file_size": file_size,
            "file_hash": file_hash,
            "chunk_size": cs,
            "compressed": compressed,
            "compression_level": cl,
            "num_chunks": num_chunks
        }
        await conn.send_message(MSG_TYPE_FILE_META, json.dumps(meta).encode())
        logger.info(f"Sent file meta for {file_name} to {conn.peer.display_name}")
        self._notify_update(transfer)
        return transfer_id

    async def _send_file_chunks(self, transfer: Transfer,
                                 conn: SecureConnection) -> None:
        try:
            transfer.state = TRANSFER_STATE_IN_PROGRESS
            self._chunk_manager.init_send(transfer.transfer_id, transfer.file_path,
                                           transfer.chunk_size)
            while True:
                if transfer.state == TRANSFER_STATE_CANCELLED:
                    break
                if transfer.state == TRANSFER_STATE_PAUSED:
                    await asyncio.sleep(1)
                    continue
                chunk = self._chunk_manager.get_next_pending_chunk(transfer.transfer_id)
                if chunk is None:
                    break
                chunk_bytes: bytes = self._chunk_manager.read_chunk_data(
                    transfer.transfer_id, chunk.index
                )
                if transfer.compressed:
                    chunk_bytes = self._compressor.compress(
                        chunk_bytes, transfer.compression_level
                    )
                chunk_data: dict = {
                    "transfer_id": transfer.transfer_id,
                    "chunk_index": chunk.index,
                    "data": base64.b64encode(chunk_bytes).decode(),
                    "hash": Hasher.hash_chunk(chunk_bytes)
                }
                await conn.send_message(
                    MSG_TYPE_FILE_CHUNK, json.dumps(chunk_data).encode()
                )
                chunk.state = "sent"
                transfer.bytes_transferred += chunk.size
                transfer.progress = (transfer.bytes_transferred / transfer.bytes_total * 100) if transfer.bytes_total > 0 else 0
                conn.bandwidth_estimator.record_throughput(len(chunk_bytes))
                transfer.speed = conn.bandwidth_estimator.bandwidth
                self._db.update_transfer_state(
                    transfer.transfer_id, TRANSFER_STATE_IN_PROGRESS,
                    bytes_transferred=transfer.bytes_transferred,
                    speed=transfer.speed
                )
                self._notify_update(transfer)
                await asyncio.sleep(0.01)
            if transfer.state != TRANSFER_STATE_CANCELLED:
                transfer.state = TRANSFER_STATE_COMPLETED
                transfer.completed_at = get_timestamp()
                self._db.update_transfer_state(transfer.transfer_id, TRANSFER_STATE_COMPLETED)
                self._add_to_history(transfer)
                self._notify_update(transfer)
                logger.info(f"Transfer completed: {transfer.file_name}")
                if self._on_transfer_complete:
                    self._on_transfer_complete(transfer)
        except Exception as e:
            logger.error(f"Error sending chunks for {transfer.file_name}: {e}")
            transfer.state = TRANSFER_STATE_FAILED
            transfer.error_message = str(e)
            self._db.update_transfer_state(transfer.transfer_id, TRANSFER_STATE_FAILED,
                                           error_message=str(e))
            self._notify_update(transfer)

    async def accept_transfer(self, transfer_id: str, download_dir: str) -> None:
        transfer: Optional[Transfer] = self._active_transfers.get(transfer_id)
        if not transfer:
            logger.warning(f"Transfer {transfer_id} not found")
            return
        conn: Optional[SecureConnection] = self._cm.get_connection(transfer.peer_id)
        if not conn:
            logger.warning(f"No connection to peer {transfer.peer_id}")
            return
        transfer.file_path = os.path.join(download_dir, transfer.file_name)
        os.makedirs(download_dir, exist_ok=True)
        self._chunk_manager.init_receive(transfer_id, transfer.file_size, transfer.chunk_size)
        response: dict = {
            "transfer_id": transfer_id,
            "accepted": True,
            "download_dir": download_dir
        }
        await conn.send_message(MSG_TYPE_FILE_REQUEST, json.dumps(response).encode())

    async def reject_transfer(self, transfer_id: str) -> None:
        transfer: Optional[Transfer] = self._active_transfers.get(transfer_id)
        if not transfer:
            return
        conn: Optional[SecureConnection] = self._cm.get_connection(transfer.peer_id)
        if conn:
            response: dict = {"transfer_id": transfer_id, "accepted": False}
            await conn.send_message(MSG_TYPE_FILE_REQUEST, json.dumps(response).encode())
        transfer.state = TRANSFER_STATE_CANCELLED
        self._db.update_transfer_state(transfer_id, TRANSFER_STATE_CANCELLED)
        self._cleanup_transfer(transfer_id)

    async def pause_transfer(self, transfer_id: str) -> None:
        transfer: Optional[Transfer] = self._active_transfers.get(transfer_id)
        if not transfer:
            return
        transfer.state = TRANSFER_STATE_PAUSED
        self._db.update_transfer_state(transfer_id, TRANSFER_STATE_PAUSED)
        conn: Optional[SecureConnection] = self._cm.get_connection(transfer.peer_id)
        if conn:
            data: dict = {"transfer_id": transfer_id, "action": "pause"}
            await conn.send_message(MSG_TYPE_DATA, json.dumps(data).encode())
        self._notify_update(transfer)

    async def resume_transfer(self, transfer_id: str) -> None:
        transfer: Optional[Transfer] = self._active_transfers.get(transfer_id)
        if not transfer:
            return
        transfer.state = TRANSFER_STATE_IN_PROGRESS
        self._db.update_transfer_state(transfer_id, TRANSFER_STATE_IN_PROGRESS)
        conn: Optional[SecureConnection] = self._cm.get_connection(transfer.peer_id)
        if conn:
            data: dict = {"transfer_id": transfer_id, "action": "resume"}
            await conn.send_message(MSG_TYPE_DATA, json.dumps(data).encode())
        if transfer.direction == TRANSFER_DIRECTION_SEND:
            asyncio.create_task(self._send_file_chunks(transfer, conn))
        self._notify_update(transfer)

    async def cancel_transfer(self, transfer_id: str) -> None:
        transfer: Optional[Transfer] = self._active_transfers.get(transfer_id)
        if not transfer:
            return
        transfer.state = TRANSFER_STATE_CANCELLED
        self._db.update_transfer_state(transfer_id, TRANSFER_STATE_CANCELLED)
        conn: Optional[SecureConnection] = self._cm.get_connection(transfer.peer_id)
        if conn:
            data: dict = {"transfer_id": transfer_id, "action": "cancel"}
            await conn.send_message(MSG_TYPE_DATA, json.dumps(data).encode())
        self._cleanup_transfer(transfer_id)
        self._notify_update(transfer)

    def _cleanup_transfer(self, transfer_id: str) -> None:
        self._active_transfers.pop(transfer_id, None)
        self._chunk_manager.cleanup(transfer_id)

    def _add_to_history(self, transfer: Transfer) -> None:
        duration: float = 0.0
        if transfer.started_at and transfer.completed_at:
            duration = transfer.completed_at - transfer.started_at
        avg_speed: float = 0.0
        if duration > 0:
            avg_speed = transfer.bytes_total / duration
        history: TransferHistory = TransferHistory(
            transfer_id=transfer.transfer_id,
            file_name=transfer.file_name,
            file_size=transfer.file_size,
            direction=transfer.direction,
            peer_id=transfer.peer_id,
            peer_name=transfer.peer_name,
            state=transfer.state,
            started_at=transfer.started_at or 0,
            completed_at=transfer.completed_at or 0,
            duration=duration,
            avg_speed=avg_speed,
            file_hash=transfer.file_hash,
            error_message=transfer.error_message
        )
        self._db.add_to_history(history)

    def get_active_transfer(self, transfer_id: str) -> Optional[Transfer]:
        return self._active_transfers.get(transfer_id)

    def get_all_active_transfers(self) -> Dict[str, Transfer]:
        return dict(self._active_transfers)

    def get_transfer_stats(self, transfer_id: str) -> Optional[dict]:
        transfer: Optional[Transfer] = self._active_transfers.get(transfer_id)
        if not transfer:
            return None
        return {
            "transfer_id": transfer.transfer_id,
            "file_name": transfer.file_name,
            "file_size": transfer.file_size,
            "transferred": transfer.bytes_transferred,
            "progress": transfer.progress,
            "speed": transfer.speed,
            "state": transfer.state,
            "direction": transfer.direction,
            "peer": transfer.peer_name,
            "eta": transfer.eta
        }

    def _notify_update(self, transfer: Transfer) -> None:
        if self._on_transfer_update:
            try:
                self._on_transfer_update(transfer)
            except Exception as e:
                logger.debug(f"Update callback error: {e}")

    async def start(self) -> None:
        self._running = True
        logger.info("Transfer controller started")

    async def stop(self) -> None:
        self._running = False
        for transfer_id in list(self._active_transfers.keys()):
            await self.cancel_transfer(transfer_id)
        logger.info("Transfer controller stopped")
