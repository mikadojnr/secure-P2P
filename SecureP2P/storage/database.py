import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from storage.models import ChunkState, LogEntry, Peer, Setting, Transfer, TransferHistory
from utils.constants import DB_DIR, DB_NAME


class DatabaseManager:
    """Manages SQLite database operations with thread safety."""

    _instance: Optional["DatabaseManager"] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        os.makedirs(DB_DIR, exist_ok=True)
        self._db_path: str = os.path.join(DB_DIR, DB_NAME)
        self._local: threading.local = threading.local()
        self._initialized: bool = True
        self._create_tables()

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "connection") or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self._db_path, check_same_thread=False
            )
            self._local.connection.row_factory = sqlite3.Row
            self._local.connection.execute("PRAGMA journal_mode=WAL")
            self._local.connection.execute("PRAGMA foreign_keys=ON")
        return self._local.connection

    def _create_tables(self) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS peers (
                peer_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                host TEXT,
                port INTEGER DEFAULT 0,
                public_ip TEXT,
                public_port INTEGER DEFAULT 0,
                state TEXT DEFAULT 'disconnected',
                nat_type TEXT DEFAULT 'unknown',
                protocol_version INTEGER DEFAULT 1,
                public_key TEXT,
                session_key TEXT,
                connection_type TEXT DEFAULT 'lan',
                last_seen REAL DEFAULT 0,
                latency REAL DEFAULT 0,
                bandwidth INTEGER DEFAULT 0,
                is_favourite INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}',
                created_at REAL DEFAULT (strftime('%s','now')),
                updated_at REAL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS transfers (
                transfer_id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                file_path TEXT,
                file_size INTEGER DEFAULT 0,
                file_hash TEXT,
                chunk_size INTEGER DEFAULT 65536,
                compressed INTEGER DEFAULT 0,
                compression_level INTEGER DEFAULT 3,
                direction TEXT DEFAULT 'send',
                state TEXT DEFAULT 'pending',
                peer_id TEXT,
                peer_name TEXT,
                progress REAL DEFAULT 0,
                bytes_transferred INTEGER DEFAULT 0,
                bytes_total INTEGER DEFAULT 0,
                speed REAL DEFAULT 0,
                eta TEXT,
                error_message TEXT,
                started_at REAL,
                completed_at REAL,
                estimated_time REAL,
                created_at REAL DEFAULT (strftime('%s','now')),
                updated_at REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY (peer_id) REFERENCES peers(peer_id)
            );

            CREATE TABLE IF NOT EXISTS transfer_chunks (
                chunk_id TEXT PRIMARY KEY,
                transfer_id TEXT NOT NULL,
                chunk_index INTEGER DEFAULT 0,
                offset INTEGER DEFAULT 0,
                size INTEGER DEFAULT 0,
                compressed_size INTEGER DEFAULT 0,
                state TEXT DEFAULT 'pending',
                hash TEXT,
                retry_count INTEGER DEFAULT 0,
                ack_timeout REAL DEFAULT 0,
                FOREIGN KEY (transfer_id) REFERENCES transfers(transfer_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS transfer_history (
                transfer_id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                direction TEXT DEFAULT 'send',
                peer_id TEXT,
                peer_name TEXT,
                state TEXT DEFAULT 'completed',
                started_at REAL DEFAULT 0,
                completed_at REAL DEFAULT 0,
                duration REAL DEFAULT 0,
                avg_speed REAL DEFAULT 0,
                file_hash TEXT,
                error_message TEXT,
                created_at REAL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL DEFAULT (strftime('%s','now')),
                level TEXT DEFAULT 'INFO',
                module TEXT DEFAULT '',
                message TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_transfers_state ON transfers(state);
            CREATE INDEX IF NOT EXISTS idx_transfers_peer ON transfers(peer_id);
            CREATE INDEX IF NOT EXISTS idx_chunks_transfer ON transfer_chunks(transfer_id);
            CREATE INDEX IF NOT EXISTS idx_history_completed ON transfer_history(completed_at);
            CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);
        """)
        conn.commit()

    # Peer operations
    def save_peer(self, peer: Peer) -> None:
        conn = self._get_connection()
        conn.execute("""
            INSERT OR REPLACE INTO peers
            (peer_id, display_name, host, port, public_ip, public_port, state,
             nat_type, protocol_version, public_key, session_key, connection_type,
             last_seen, latency, bandwidth, is_favourite, metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
        """, (
            peer.peer_id, peer.display_name, peer.host, peer.port,
            peer.public_ip, peer.public_port, peer.state,
            peer.nat_type, peer.protocol_version,
            peer.public_key.hex() if peer.public_key else None,
            peer.session_key.hex() if peer.session_key else None,
            peer.connection_type, peer.last_seen,
            peer.latency, peer.bandwidth, int(peer.is_favourite),
            json.dumps(peer.metadata)
        ))
        conn.commit()

    def get_peer(self, peer_id: str) -> Optional[Peer]:
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM peers WHERE peer_id = ?", (peer_id,))
        row = cursor.fetchone()
        return self._row_to_peer(row) if row else None

    def get_all_peers(self) -> List[Peer]:
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM peers ORDER BY last_seen DESC")
        return [self._row_to_peer(row) for row in cursor.fetchall()]

    def delete_peer(self, peer_id: str) -> None:
        conn = self._get_connection()
        conn.execute("DELETE FROM peers WHERE peer_id = ?", (peer_id,))
        conn.commit()

    def update_peer_state(self, peer_id: str, state: str) -> None:
        conn = self._get_connection()
        conn.execute("""
            UPDATE peers SET state = ?, updated_at = strftime('%s','now')
            WHERE peer_id = ?
        """, (state, peer_id))
        conn.commit()

    @staticmethod
    def _row_to_peer(row: sqlite3.Row) -> Peer:
        return Peer(
            peer_id=row["peer_id"],
            display_name=row["display_name"],
            host=row["host"],
            port=row["port"],
            public_ip=row["public_ip"],
            public_port=row["public_port"],
            state=row["state"],
            nat_type=row["nat_type"],
            protocol_version=row["protocol_version"],
            public_key=bytes.fromhex(row["public_key"]) if row["public_key"] else None,
            session_key=bytes.fromhex(row["session_key"]) if row["session_key"] else None,
            connection_type=row["connection_type"],
            last_seen=row["last_seen"],
            latency=row["latency"],
            bandwidth=row["bandwidth"],
            is_favourite=bool(row["is_favourite"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {}
        )

    # Transfer operations
    def save_transfer(self, transfer: Transfer) -> None:
        conn = self._get_connection()
        conn.execute("""
            INSERT OR REPLACE INTO transfers
            (transfer_id, file_name, file_path, file_size, file_hash, chunk_size,
             compressed, compression_level, direction, state, peer_id, peer_name,
             progress, bytes_transferred, bytes_total, speed, eta, error_message,
             started_at, completed_at, estimated_time, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
        """, (
            transfer.transfer_id, transfer.file_name, transfer.file_path,
            transfer.file_size, transfer.file_hash, transfer.chunk_size,
            int(transfer.compressed), transfer.compression_level, transfer.direction,
            transfer.state, transfer.peer_id, transfer.peer_name,
            transfer.progress, transfer.bytes_transferred, transfer.bytes_total,
            transfer.speed, transfer.eta, transfer.error_message,
            transfer.started_at, transfer.completed_at, transfer.estimated_time
        ))
        conn.commit()

    def get_transfer(self, transfer_id: str) -> Optional[Transfer]:
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM transfers WHERE transfer_id = ?", (transfer_id,))
        row = cursor.fetchone()
        return self._row_to_transfer(row) if row else None

    def get_active_transfers(self) -> List[Transfer]:
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT * FROM transfers
            WHERE state IN ('pending', 'in_progress', 'paused')
            ORDER BY created_at DESC
        """)
        return [self._row_to_transfer(row) for row in cursor.fetchall()]

    def get_all_transfers(self) -> List[Transfer]:
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM transfers ORDER BY created_at DESC")
        return [self._row_to_transfer(row) for row in cursor.fetchall()]

    def update_transfer_state(self, transfer_id: str, state: str,
                               bytes_transferred: Optional[int] = None,
                               speed: Optional[float] = None,
                               error_message: Optional[str] = None) -> None:
        conn = self._get_connection()
        updates: List[str] = ["state = ?", "updated_at = strftime('%s','now')"]
        params: List[Any] = [state]
        if bytes_transferred is not None:
            updates.append("bytes_transferred = ?")
            params.append(bytes_transferred)
        if speed is not None:
            updates.append("speed = ?")
            params.append(speed)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        params.append(transfer_id)
        conn.execute(f"UPDATE transfers SET {', '.join(updates)} WHERE transfer_id = ?", params)
        conn.commit()

    def delete_transfer(self, transfer_id: str) -> None:
        conn = self._get_connection()
        conn.execute("DELETE FROM transfer_chunks WHERE transfer_id = ?", (transfer_id,))
        conn.execute("DELETE FROM transfers WHERE transfer_id = ?", (transfer_id,))
        conn.commit()

    @staticmethod
    def _row_to_transfer(row: sqlite3.Row) -> Transfer:
        transfer = Transfer(
            transfer_id=row["transfer_id"],
            file_name=row["file_name"],
            file_path=row["file_path"],
            file_size=row["file_size"],
            file_hash=row["file_hash"],
            chunk_size=row["chunk_size"],
            compressed=bool(row["compressed"]),
            compression_level=row["compression_level"],
            direction=row["direction"],
            state=row["state"],
            peer_id=row["peer_id"],
            peer_name=row["peer_name"],
            progress=row["progress"],
            bytes_transferred=row["bytes_transferred"],
            bytes_total=row["bytes_total"],
            speed=row["speed"],
            eta=row["eta"],
            error_message=row["error_message"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            estimated_time=row["estimated_time"]
        )
        return transfer

    # Chunk operations
    def save_chunks(self, chunks: List[ChunkState]) -> None:
        conn = self._get_connection()
        conn.executemany("""
            INSERT OR REPLACE INTO transfer_chunks
            (chunk_id, transfer_id, chunk_index, offset, size, compressed_size,
             state, hash, retry_count, ack_timeout)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [(
            c.chunk_id, c.transfer_id, c.index, c.offset, c.size,
            c.compressed_size, c.state, c.hash, c.retry_count, c.ack_timeout
        ) for c in chunks])
        conn.commit()

    def get_chunks(self, transfer_id: str) -> List[ChunkState]:
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM transfer_chunks WHERE transfer_id = ? ORDER BY chunk_index",
            (transfer_id,)
        )
        return [self._row_to_chunk(row) for row in cursor.fetchall()]

    def update_chunk_state(self, chunk_id: str, state: str,
                            retry_count: Optional[int] = None) -> None:
        conn = self._get_connection()
        updates: List[str] = ["state = ?"]
        params: List[Any] = [state]
        if retry_count is not None:
            updates.append("retry_count = ?")
            params.append(retry_count)
        params.append(chunk_id)
        conn.execute(f"UPDATE transfer_chunks SET {', '.join(updates)} WHERE chunk_id = ?", params)
        conn.commit()

    def delete_transfer_chunks(self, transfer_id: str) -> None:
        conn = self._get_connection()
        conn.execute("DELETE FROM transfer_chunks WHERE transfer_id = ?", (transfer_id,))
        conn.commit()

    @staticmethod
    def _row_to_chunk(row: sqlite3.Row) -> ChunkState:
        return ChunkState(
            chunk_id=row["chunk_id"],
            transfer_id=row["transfer_id"],
            index=row["chunk_index"],
            offset=row["offset"],
            size=row["size"],
            compressed_size=row["compressed_size"],
            state=row["state"],
            hash=row["hash"],
            retry_count=row["retry_count"],
            ack_timeout=row["ack_timeout"]
        )

    # History operations
    def add_to_history(self, history: TransferHistory) -> None:
        conn = self._get_connection()
        conn.execute("""
            INSERT OR REPLACE INTO transfer_history
            (transfer_id, file_name, file_size, direction, peer_id, peer_name,
             state, started_at, completed_at, duration, avg_speed, file_hash, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            history.transfer_id, history.file_name, history.file_size,
            history.direction, history.peer_id, history.peer_name,
            history.state, history.started_at, history.completed_at,
            history.duration, history.avg_speed, history.file_hash,
            history.error_message
        ))
        conn.commit()

    def get_history(self, limit: int = 100) -> List[TransferHistory]:
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM transfer_history ORDER BY completed_at DESC LIMIT ?",
            (limit,)
        )
        return [self._row_to_history(row) for row in cursor.fetchall()]

    @staticmethod
    def _row_to_history(row: sqlite3.Row) -> TransferHistory:
        return TransferHistory(
            transfer_id=row["transfer_id"],
            file_name=row["file_name"],
            file_size=row["file_size"],
            direction=row["direction"],
            peer_id=row["peer_id"],
            peer_name=row["peer_name"],
            state=row["state"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            duration=row["duration"],
            avg_speed=row["avg_speed"],
            file_hash=row["file_hash"],
            error_message=row["error_message"]
        )

    # Log operations
    def add_log(self, timestamp: float, level: str, module: str, message: str) -> None:
        conn = self._get_connection()
        conn.execute(
            "INSERT INTO logs (timestamp, level, module, message) VALUES (?, ?, ?, ?)",
            (timestamp, level, module, message)
        )
        conn.commit()

    def get_logs(self, limit: int = 500, level: Optional[str] = None) -> List[LogEntry]:
        conn = self._get_connection()
        if level:
            cursor = conn.execute(
                "SELECT * FROM logs WHERE level = ? ORDER BY log_id DESC LIMIT ?",
                (level, limit)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM logs ORDER BY log_id DESC LIMIT ?", (limit,)
            )
        return [self._row_to_log(row) for row in cursor.fetchall()]

    @staticmethod
    def _row_to_log(row: sqlite3.Row) -> LogEntry:
        return LogEntry(
            log_id=row["log_id"],
            timestamp=row["timestamp"],
            level=row["level"],
            module=row["module"],
            message=row["message"]
        )

    # Settings operations
    def get_setting(self, key: str, default: str = "") -> str:
        conn = self._get_connection()
        cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        conn = self._get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()

    def get_all_settings(self) -> List[Setting]:
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM settings")
        return [Setting(key=row["key"], value=row["value"]) for row in cursor.fetchall()]

    # Maintenance
    def cleanup_old_logs(self, days: int = 30) -> int:
        conn = self._get_connection()
        cutoff = time.time() - (days * 86400)
        cursor = conn.execute("DELETE FROM logs WHERE timestamp < ?", (cutoff,))
        conn.commit()
        return cursor.rowcount

    def cleanup_old_history(self, days: int = 90) -> int:
        conn = self._get_connection()
        cutoff = time.time() - (days * 86400)
        cursor = conn.execute(
            "DELETE FROM transfer_history WHERE completed_at < ?", (cutoff,)
        )
        conn.commit()
        return cursor.rowcount

    def close(self) -> None:
        if hasattr(self._local, "connection") and self._local.connection:
            self._local.connection.close()
            self._local.connection = None

    def __del__(self) -> None:
        self.close()
