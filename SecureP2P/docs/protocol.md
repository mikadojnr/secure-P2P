# Protocol Specification

## Message Format

All messages use a 12-byte header:

```
Offset  Size  Field
0       4     Magic (0x53454350 = "SECP")
4       4     Message Type (uint32)
8       4     Payload Length (uint32)
12      N     Payload (encrypted after key exchange)
```

## Message Types

| Code | Name | Direction | Payload |
|------|------|-----------|---------|
| 0x01 | HELLO | Bidirectional | Peer ID, display name, public key |
| 0x02 | HELLO_ACK | Bidirectional | Acknowledgment |
| 0x03 | KEY_EXCHANGE | Bidirectional | Salt and status |
| 0x04 | KEY_EXCHANGE_ACK | Bidirectional | Salt |
| 0x05 | DATA | Bidirectional | JSON action |
| 0x06 | DATA_ACK | Bidirectional | JSON result |
| 0x07 | PING | Bidirectional | Timestamp |
| 0x08 | PONG | Bidirectional | Timestamp |
| 0x09 | FILE_META | Sender→Receiver | File metadata JSON |
| 0x0A | FILE_CHUNK | Sender→Receiver | Chunk data (base64) |
| 0x0B | FILE_ACK | Receiver→Sender | Chunk acknowledgment |
| 0x0C | FILE_REQUEST | Receiver→Sender | Accept/reject |
| 0x0D | FILE_RESPONSE | Sender→Receiver | Response status |
| 0x0E | DISCONNECT | Bidirectional | Reason |
| 0xFF | ERROR | Bidirectional | Error message |

## Key Exchange Protocol

```
Client                          Server
  |                               |
  |--- HELLO (pubkey, id) ------>|
  |<-- HELLO_ACK (pubkey, id) ---|
  |                               |
  |   Compute shared secret       |
  |   Generate random salt        |
  |                               |
  |--- KEY_EXCHANGE (salt) ------>|
  |<-- KEY_EXCHANGE_ACK (salt) ---|
  |                               |
  |   Derive session key          |
  |   All subsequent messages     |
  |   are AES-256-GCM encrypted   |
```

## Handshake Sequence

```
TCP Connection Establishment
  ↓
HELLO Exchange (plaintext)
  - Peer ID
  - Display Name
  - X25519 Public Key (32 bytes)
  ↓
Key Derivation (both sides)
  - Compute X25519 shared secret
  - HKDF-SHA256(salt, shared_secret) → 32-byte session key
  ↓
AES-256-GCM Session
  - All subsequent messages encrypted
  - Nonce: 8 random bytes + 4 byte counter
  - AAD used for chunk index binding
```

## File Transfer Protocol

```
Sender                          Receiver
  |                               |
  |--- FILE_META --------------->|
  |   {transfer_id, file_name,   |
  |    file_size, file_hash,      |
  |    chunk_size, compressed,    |
  |    compression_level,         |
  |    num_chunks}                |
  |                               |
  |<-- FILE_REQUEST -------------|
  |   {transfer_id, accepted,    |
  |    download_dir}              |
  |                               |
  |--- FILE_CHUNK (x N) -------->|
  |   {transfer_id, chunk_index,  |
  |    data (base64), hash}       |
  |                               |
  |<-- FILE_ACK -----------------|
  |   {transfer_id, chunk_index,  |
  |    status}                    |
  |                               |
  |--- DATA (complete) --------->|
  |<-- DATA_ACK -----------------|
```

## Chunk Size Adaptation

Bandwidth estimation drives chunk size selection:

```python
CHUNK_SIZES = {
    "poor":     32 * 1024,    # < 32 KB/s
    "average":  64 * 1024,    # 32-256 KB/s
    "good":     256 * 1024,   # 256 KB-1 MB/s
    "excellent": 512 * 1024,  # > 1 MB/s
}
```

## Compression Strategy

```python
COMPRESSION_LEVELS = {
    "fast":     1,    # Excellent bandwidth
    "balanced": 3,    # Good bandwidth
    "maximum":  10,   # Poor/average bandwidth
}
```
