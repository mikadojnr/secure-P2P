from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Peer:
    """Represents a peer in the P2P network."""
    peer_id: str = ""
    display_name: str = ""
    host: str = ""
    port: int = 0
    public_ip: str = ""
    public_port: int = 0
    state: str = "disconnected"
    nat_type: str = "unknown"
    protocol_version: int = 1
    public_key: Optional[bytes] = None
    session_key: Optional[bytes] = None
    connection_type: str = "lan"
    last_seen: float = 0.0
    latency: float = 0.0
    bandwidth: int = 0
    is_favourite: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "peer_id": self.peer_id,
            "display_name": self.display_name,
            "host": self.host,
            "port": self.port,
            "public_ip": self.public_ip,
            "public_port": self.public_port,
            "state": self.state,
            "nat_type": self.nat_type,
            "protocol_version": self.protocol_version,
            "public_key": self.public_key.hex() if self.public_key else None,
            "session_key": self.session_key.hex() if self.session_key else None,
            "connection_type": self.connection_type,
            "last_seen": self.last_seen,
            "latency": self.latency,
            "bandwidth": self.bandwidth,
            "is_favourite": self.is_favourite,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Peer":
        public_key = bytes.fromhex(data["public_key"]) if data.get("public_key") else None
        session_key = bytes.fromhex(data["session_key"]) if data.get("session_key") else None
        return cls(
            peer_id=data.get("peer_id", ""),
            display_name=data.get("display_name", ""),
            host=data.get("host", ""),
            port=data.get("port", 0),
            public_ip=data.get("public_ip", ""),
            public_port=data.get("public_port", 0),
            state=data.get("state", "disconnected"),
            nat_type=data.get("nat_type", "unknown"),
            protocol_version=data.get("protocol_version", 1),
            public_key=public_key,
            session_key=session_key,
            connection_type=data.get("connection_type", "lan"),
            last_seen=data.get("last_seen", 0.0),
            latency=data.get("latency", 0.0),
            bandwidth=data.get("bandwidth", 0),
            is_favourite=data.get("is_favourite", False),
            metadata=data.get("metadata", {})
        )


@dataclass
class ChunkState:
    """Represents state of a single chunk in a transfer."""
    chunk_id: str = ""
    transfer_id: str = ""
    index: int = 0
    offset: int = 0
    size: int = 0
    compressed_size: int = 0
    state: str = "pending"
    hash: str = ""
    retry_count: int = 0
    ack_timeout: float = 0.0


@dataclass
class Transfer:
    """Represents an active or queued file transfer."""
    transfer_id: str = ""
    file_name: str = ""
    file_path: str = ""
    file_size: int = 0
    file_hash: str = ""
    chunk_size: int = 65536
    compressed: bool = False
    compression_level: int = 3
    direction: str = "send"
    state: str = "pending"
    peer_id: Optional[str] = None
    peer_name: str = ""
    progress: float = 0.0
    bytes_transferred: int = 0
    bytes_total: int = 0
    speed: float = 0.0
    eta: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    estimated_time: Optional[float] = None
    chunks: List[ChunkState] = field(default_factory=list)


@dataclass
class TransferHistory:
    """Represents completed transfer history entry."""
    transfer_id: str = ""
    file_name: str = ""
    file_size: int = 0
    direction: str = "send"
    peer_id: str = ""
    peer_name: str = ""
    state: str = "completed"
    started_at: float = 0.0
    completed_at: float = 0.0
    duration: float = 0.0
    avg_speed: float = 0.0
    file_hash: str = ""
    error_message: Optional[str] = None


@dataclass
class LogEntry:
    """Represents a log entry stored in the database."""
    log_id: int = 0
    timestamp: float = 0.0
    level: str = "INFO"
    module: str = ""
    message: str = ""


@dataclass
class Setting:
    """Represents a key-value setting."""
    key: str = ""
    value: str = ""
