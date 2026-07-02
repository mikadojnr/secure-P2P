# SecureP2P - Secure Peer-to-Peer File Sharing

**Secure Peer-to-Peer File Sharing Desktop Application with End-to-End Encryption for Low-Bandwidth Networks**

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Presentation Layer (PyQt6 GUI)             │
│  Peer List | File Browser | Transfers | Stats | Logs | Dark │
├─────────────────────────────────────────────────────────────┤
│                   Application Layer                          │
│  Transfer Scheduler | Queue Manager | Retry | Resume Logic   │
├─────────────────────────────────────────────────────────────┤
│                   Security Layer                             │
│  X25519 | HKDF-SHA256 | AES-256-GCM | SHA-256 | PFS         │
├─────────────────────────────────────────────────────────────┤
│                   Network Layer                              │
│  asyncio TCP | mDNS | STUN/TURN | Health Monitor | Reconnect │
├─────────────────────────────────────────────────────────────┤
│                   Data Layer (SQLite)                        │
│  Peers | Transfers | History | Logs | Settings | Resume      │
└─────────────────────────────────────────────────────────────┘
```

## Features

- **End-to-End Encryption**: X25519 key exchange + HKDF-SHA256 + AES-256-GCM
- **Perfect Forward Secrecy**: Ephemeral keys per session
- **Adaptive Compression**: Zstandard with dynamic level selection
- **Resumable Transfers**: Resume interrupted transfers from last checkpoint
- **Bandwidth Optimization**: Automatic chunk size and compression adaptation
- **NAT Traversal**: STUN hole punching with TURN relay fallback
- **Peer Discovery**: mDNS (Zeroconf) and multicast LAN discovery
- **Integrity Verification**: SHA-256 per chunk and per file
- **Modern GUI**: PyQt6 with dark theme, drag-and-drop, real-time stats
- **No Central Server**: Fully peer-to-peer architecture

## Requirements

- **OS**: Windows 10, Windows 11
- **Python**: 3.11 or higher
- **RAM**: < 300 MB
- **Network**: LAN, WAN, WiFi, Ethernet

## Installation

### 1. Clone or Download

```bash
git clone <repository-url>
cd SecureP2P
```

### 2. Create Virtual Environment

```bash
python -m venv venv
venv\Scripts\activate    # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run Application

```bash
python app.py
```

## Build Standalone EXE

### Using PyInstaller

```bash
pip install pyinstaller
pyinstaller build.spec
```

The executable will be in `dist/SecureP2P/`.

### One-File Portable Version

```bash
pyinstaller --onefile --windowed --name SecureP2P_Portable app.py
```

## Usage Guide

### 1. Starting the Application

Run `python app.py` to launch the GUI. The application automatically:
- Starts the peer discovery service
- Begins listening for incoming connections
- Initializes the SQLite database

### 2. Discovering Peers

- **Automatic**: Peers on the same LAN are discovered via mDNS/multicast
- **Manual**: Go to `Network > Connect to Peer...` (Ctrl+D) to add by IP:Port

### 3. Connecting to a Peer

- Select a peer from the peer list
- Click **Connect**
- A secure encrypted session is established automatically

### 4. Sending Files

- Drag and drop files onto the file drop zone, or
- Go to `File > Send File...` (Ctrl+O)
- Select the destination peer
- The transfer begins with adaptive chunking and compression

### 5. Receiving Files

- When a peer sends a file, a dialog appears
- Click **Yes** to accept or **No** to reject
- Accepted files are saved to the download directory

### 6. Managing Transfers

| Action | Description |
|--------|-------------|
| **Pause** | Temporarily stop a transfer |
| **Resume** | Continue a paused transfer |
| **Cancel** | Cancel and remove a transfer |
| **Retry** | Retry a failed transfer |

### 7. Settings

Access via `File > Settings...` (Ctrl+,):

| Setting | Options |
|---------|---------|
| Download Directory | Custom download location |
| Dark Mode | On/Off |
| Compression Mode | Fast / Balanced / Maximum |
| Chunk Size | Auto-adaptive or manual |
| Max Bandwidth | Limit transfer speed |
| Auto Reconnect | Automatically reconnect on disconnect |
| Peer Timeout | Connection timeout in seconds |

## Security Details

### Cryptographic Protocol

1. **Key Exchange**: X25519 ECDH
2. **Key Derivation**: HKDF-SHA256 with random salt
3. **Encryption**: AES-256-GCM (authenticated encryption)
4. **Integrity**: SHA-256 per chunk and per file
5. **Perfect Forward Secrecy**: New ephemeral keys per session

### Security Properties

- **MITM Protection**: Mutual authentication via key exchange
- **Replay Protection**: Unique nonces per message
- **Nonce Reuse Prevention**: Counter + random combined nonce
- **Tamper Detection**: GCM authentication tag on every message
- **Forward Secrecy**: Compromised long-term key cannot decrypt past sessions

## Network Details

### Port Usage

| Port | Protocol | Purpose |
|------|----------|---------|
| 53333 | UDP | Peer discovery (multicast) |
| Dynamic | TCP | Secure data transfer |

### NAT Traversal

1. STUN queries determine public IP and port
2. NAT type is detected (Open/Cone/Symmetric)
3. UDP hole punching attempts direct connection
4. TURN relay used as fallback for symmetric NATs

### Bandwidth Adaptation

| Network Quality | Chunk Size | Compression |
|----------------|------------|-------------|
| Poor (<32 KB/s) | 32 KB | Maximum |
| Average (32-256 KB/s) | 64 KB | Maximum |
| Good (256 KB-1 MB/s) | 256 KB | Balanced |
| Excellent (>1 MB/s) | 512 KB | Fast |

## Project Structure

```
SecureP2P/
  app.py                    # Entry point
  requirements.txt          # Dependencies
  build.spec               # PyInstaller spec
  README.md                # This file

  gui/                     # Presentation Layer
    main_window.py          # Main window with all components
    transfer_window.py      # Transfer detail dialogs
    settings.py             # Configuration dialog
    widgets.py              # Reusable GUI widgets

  network/                 # Network Layer
    peer_discovery.py       # mDNS and multicast discovery
    stun_client.py          # STUN NAT traversal
    turn_client.py          # TURN relay fallback
    connection_manager.py   # TCP connection management
    transfer_controller.py  # File transfer orchestration
    bandwidth_estimator.py  # Bandwidth measurement

  crypto/                  # Security Layer
    key_exchange.py         # X25519 key agreement
    aes_engine.py           # AES-256-GCM encryption
    hkdf.py                 # Key derivation
    hashing.py              # SHA-256 integrity

  transfer/                # Application Layer
    chunk_manager.py        # File chunking and reassembly
    compressor.py           # Zstandard compression
    resumable.py            # Transfer resume logic
    scheduler.py            # Transfer queue scheduling

  storage/                 # Data Layer
    database.py             # SQLite database manager
    models.py               # Data models
    logger.py               # File and console logging

  utils/                   # Utilities
    config.py               # Configuration manager
    constants.py            # Application constants
    helpers.py              # Utility functions

  tests/                   # Test Suite
    test_crypto.py          # Cryptography tests
    test_network.py         # Network tests
    test_transfer.py        # Transfer tests
    test_storage.py         # Database tests
    test_utils.py           # Utility tests
    test_integration.py     # Integration tests

  docs/                    # Documentation
```

## Running Tests

```bash
# Run all tests
python -m pytest tests/

# Run specific test files
python -m pytest tests/test_crypto.py -v
python -m pytest tests/test_network.py -v
python -m pytest tests/test_transfer.py -v
python -m pytest tests/test_storage.py -v
python -m pytest tests/test_utils.py -v
python -m pytest tests/test_integration.py -v

# Run with coverage
pip install pytest-cov
python -m pytest tests/ --cov=. --cov-report=html
```

## Performance Characteristics

| Metric | Target |
|--------|--------|
| Encryption Overhead | < 12% |
| CPU Usage | < 35% |
| RAM Usage | < 300 MB |
| Resume Success | 100% |
| Packet Loss Tolerance | 5% |
| Max Latency | 300 ms |
| Bandwidth Range | 256 Kbps - 1 Mbps |
| Max File Size | 10 GB |

## Wireshark Verification

To verify the encrypted nature of the protocol:

1. Install Wireshark
2. Start capturing on the network interface
3. Filter for `tcp.port == <your-port>` or `udp.port == 53333`
4. Observe:
   - Discovery packets contain only peer metadata (plaintext)
   - All data packets after key exchange are AES-GCM encrypted
   - No file content is visible in plaintext
   - Protocol magic "SECP" is visible but payload is encrypted

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Peers not discovered | Check firewall rules, ensure UDP port 53333 is open |
| Connection fails | Verify peer IP and port, check NAT type |
| Slow transfers | Adjust compression settings, check bandwidth limit |
| Transfer fails | Check disk space, verify file permissions |
| Application crashes | Check logs in `~/.securep2p/logs/` |

## Log Files

Logs are stored at:
```
%USERPROFILE%\.securep2p\logs\securep2p.log
```

## Database

Database location:
```
%USERPROFILE%\.securep2p\securep2p.db
```

## License

Academic Use - Research Project

## Citation

If you use this software in research, please cite:

```
Secure Peer-to-Peer File Sharing Desktop Application with
End-to-End Encryption for Low-Bandwidth Networks (2026)
```

## Acknowledgments

- Python Cryptography Library
- PyQt6 Framework
- ZeroConf (python-zeroconf)
- PyZstd (Python bindings for Zstandard)
