# System Architecture

## Five-Layer Architecture

### 1. Presentation Layer (GUI/)
```
main_window.py    - Main application window, status bar, menus
transfer_window.py - Transfer detail dialogs
settings.py       - Configuration dialog
widgets.py        - Reusable widgets (PeerList, TransferList, BandwidthGraph, etc.)
```

### 2. Application Layer (transfer/)
```
chunk_manager.py  - File chunking, tracking, reassembly
compressor.py     - Zstandard compression with adaptive levels
resumable.py      - Transfer state persistence and recovery
scheduler.py      - Queue management with priority scheduling
```

### 3. Security Layer (crypto/)
```
key_exchange.py   - X25519 ECDH with PFS
aes_engine.py     - AES-256-GCM authenticated encryption
hkdf.py           - HKDF-SHA256 key derivation
hashing.py        - SHA-256 integrity verification
```

### 4. Network Layer (network/)
```
peer_discovery.py     - mDNS + multicast peer discovery
stun_client.py        - STUN NAT type detection
turn_client.py        - TURN relay fallback
connection_manager.py - TCP connections, encryption handshake, routing
transfer_controller.py - File transfer orchestration over encrypted channels
bandwidth_estimator.py - Real-time bandwidth measurement
```

### 5. Data Layer (storage/)
```
database.py  - SQLite with thread-safe connection management
models.py    - Data classes for Peer, Transfer, ChunkState, etc.
logger.py    - Rotating file handler + console logging
```

## Data Flow

```
Sender                                          Receiver
  |                                               |
  |--[1] Peer Discovery (mDNS/UDP)-------------->|
  |<--[1] Peer Discovery Response----------------|
  |                                               |
  |--[2] TCP Connection (asyncio)--------------->|
  |<--[2] TCP Connection Accept------------------|
  |                                               |
  |--[3] X25519 Key Exchange-------------------->|
  |<--[3] X25519 Key Exchange--------------------|
  |--[4] HKDF Session Key Derivation             |
  |<--[4] HKDF Session Key Derivation            |
  |                                               |
  |--[5] File Metadata (encrypted)-------------->|
  |<--[5] File Accept/Reject (encrypted)---------|
  |                                               |
  |--[6] For each chunk:                         |
  |  Compress (Zstandard)                        |
  |  Encrypt (AES-256-GCM)                      |
  |  Send chunk (encrypted)--------------------->|
  |<-- Chunk ACK (encrypted)--------------------|
  |                                               |
  |--[7] File Complete-------------------------->|
  |<--[7] Transfer Complete----------------------|
```

## Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                        MainWindow                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │PeerList  │ │FileDrop  │ │Transfer  │ │BandwidthGraph │  │
│  │Widget    │ │Widget    │ │ListWidget│ │               │  │
│  └────┬─────┘ └──────────┘ └────┬──────┘ └───────────────┘  │
│       │                         │                           │
│       ▼                         ▼                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Connection Manager                       │   │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────────┐   │   │
│  │  │PeerDisc. │ │STUNClient│ │TURNClient          │   │   │
│  │  └──────────┘ └──────────┘ └────────────────────┘   │   │
│  │  ┌──────────────────────────────────────────────┐   │   │
│  │  │         TransferController                   │   │   │
│  │  │  ┌──────────┐ ┌──────────┐ ┌────────────┐   │   │   │
│  │  │  │ChunkMgr  │ │Compressor│ │Scheduler   │   │   │   │
│  │  │  └──────────┘ └──────────┘ └────────────┘   │   │   │
│  │  └──────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│       │                         │                           │
│       ▼                         ▼                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Security Layer                           │   │
│  │  KeyExchange → HKDF → AESCipher → Hasher              │   │
│  └──────────────────────────────────────────────────────┘   │
│       │                                                     │
│       ▼                                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Data Layer (SQLite)                      │   │
│  │  DBManager → Peers/Transfers/History/Logs/Settings    │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```
