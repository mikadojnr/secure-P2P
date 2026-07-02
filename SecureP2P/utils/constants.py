import os

# Application Meta
APP_NAME: str = "SecureP2P"
APP_VERSION: str = "1.0.0"
APP_AUTHOR: str = "Research Project"

# Chunk Sizes (bytes)
CHUNK_SIZE_POOR: int = 32 * 1024       # 32 KB
CHUNK_SIZE_AVERAGE: int = 64 * 1024    # 64 KB
CHUNK_SIZE_GOOD: int = 256 * 1024      # 256 KB
CHUNK_SIZE_EXCELLENT: int = 512 * 1024 # 512 KB
CHUNK_SIZES: dict = {
    "poor": CHUNK_SIZE_POOR,
    "average": CHUNK_SIZE_AVERAGE,
    "good": CHUNK_SIZE_GOOD,
    "excellent": CHUNK_SIZE_EXCELLENT
}

# Compression Levels (Zstandard)
COMPRESSION_FAST: int = 1
COMPRESSION_BALANCED: int = 3
COMPRESSION_MAXIMUM: int = 10
COMPRESSION_LEVELS: dict = {
    "fast": COMPRESSION_FAST,
    "balanced": COMPRESSION_BALANCED,
    "maximum": COMPRESSION_MAXIMUM
}

# Bandwidth Thresholds (bytes/sec)
BANDWIDTH_POOR: int = 32 * 1024        # 32 KB/s
BANDWIDTH_AVERAGE: int = 64 * 1024     # 64 KB/s
BANDWIDTH_GOOD: int = 256 * 1024       # 256 KB/s
BANDWIDTH_EXCELLENT: int = 1024 * 1024 # 1 MB/s

# Protocol Constants
PROTOCOL_MAGIC: bytes = b"SECP2P"
PROTOCOL_VERSION: int = 1
PEER_DISCOVERY_PORT: int = 53333
PEER_DISCOVERY_INTERVAL: float = 5.0

# STUN / TURN
STUN_SERVERS: list = [
    "stun.l.google.com:19302",
    "stun1.l.google.com:19302",
    "stun2.l.google.com:19302"
]
TURN_SERVERS: list = []

# Database
DB_NAME: str = "securep2p.db"
DB_DIR: str = os.path.join(os.path.expanduser("~"), ".securep2p")

# Logging
LOG_DIR: str = os.path.join(DB_DIR, "logs")
LOG_LEVEL: str = "DEBUG"
LOG_MAX_BYTES: int = 5 * 1024 * 1024  # 5MB
LOG_BACKUP_COUNT: int = 5

# Network
BUFFER_SIZE: int = 65536
SOCKET_TIMEOUT: float = 30.0
RECONNECT_INTERVAL: float = 3.0
PING_INTERVAL: float = 10.0
MAX_RETRANSMITS: int = 5
ACK_TIMEOUT: float = 5.0
CONNECTION_TIMEOUT: float = 30.0
MAX_CONNECT_RETRIES: int = 3
CONNECT_BACKOFF_BASE: float = 2.0

# Crypto
NONCE_SIZE: int = 12
TAG_SIZE: int = 16
KEY_SIZE: int = 32
SALT_SIZE: int = 32

# Chunk States
CHUNK_STATE_PENDING: str = "pending"
CHUNK_STATE_SENT: str = "sent"
CHUNK_STATE_ACKED: str = "acked"
CHUNK_STATE_FAILED: str = "failed"

# Transfer States
TRANSFER_STATE_PENDING: str = "pending"
TRANSFER_STATE_IN_PROGRESS: str = "in_progress"
TRANSFER_STATE_PAUSED: str = "paused"
TRANSFER_STATE_COMPLETED: str = "completed"
TRANSFER_STATE_FAILED: str = "failed"
TRANSFER_STATE_CANCELLED: str = "cancelled"

# Transfer Direction
TRANSFER_DIRECTION_SEND: str = "send"
TRANSFER_DIRECTION_RECEIVE: str = "receive"

# Peer States
PEER_STATE_DISCONNECTED: str = "disconnected"
PEER_STATE_CONNECTING: str = "connecting"
PEER_STATE_CONNECTED: str = "connected"
PEER_STATE_AUTHENTICATING: str = "authenticating"
PEER_STATE_AUTHENTICATED: str = "authenticated"

# NAT Types
NAT_TYPE_UNKNOWN: str = "unknown"
NAT_TYPE_OPEN: str = "open"
NAT_TYPE_MODERATE: str = "moderate"
NAT_TYPE_STRICT: str = "strict"
NAT_TYPE_SYMMETRIC: str = "symmetric"
NAT_TYPE_CONE: str = "cone"

# Theme
THEME_DARK: str = "dark"
THEME_LIGHT: str = "light"

# Limits
MAX_FILE_SIZE: int = 10 * 1024 * 1024 * 1024  # 10 GB
MAX_QUEUE_SIZE: int = 100
MAX_PEERS: int = 50
MAX_TRANSFERS: int = 10

# Default Settings
DEFAULT_DOWNLOAD_DIR: str = os.path.join(os.path.expanduser("~"), "Downloads", "SecureP2P")
DEFAULT_CHUNK_SIZE: int = CHUNK_SIZE_AVERAGE
DEFAULT_COMPRESSION: str = "balanced"
DEFAULT_MAX_BANDWIDTH: int = 0  # 0 = unlimited
DEFAULT_AUTO_RECONNECT: bool = True
DEFAULT_PEER_TIMEOUT: float = 60.0
DEFAULT_DARK_MODE: bool = True
