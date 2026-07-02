import hashlib
import os
import platform
import socket
import struct
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
from typing import Union as UnionType


def create_id() -> str:
    """Generate a unique identifier."""
    return str(uuid.uuid4().hex)


def get_timestamp() -> float:
    """Get current Unix timestamp."""
    return time.time()


def format_bytes(size: UnionType[int, float]) -> str:
    """Format bytes to human-readable string."""
    if size == 0:
        return "0 B"
    units: List[str] = ["B", "KB", "MB", "GB", "TB"]
    i: int = 0
    f_size: float = float(size)
    while f_size >= 1024 and i < len(units) - 1:
        f_size /= 1024.0
        i += 1
    return f"{f_size:.2f} {units[i]}"


def format_duration(seconds: UnionType[int, float]) -> str:
    """Format seconds to human-readable duration."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    elif seconds < 86400:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    else:
        return f"{seconds // 86400}d {(seconds % 86400) // 3600}h"


def format_speed(bytes_per_sec: UnionType[int, float]) -> str:
    """Format transfer speed."""
    return f"{format_bytes(bytes_per_sec)}/s"


def get_local_ip() -> str:
    """Get primary local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip: str = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_mac_address() -> str:
    """Get MAC address of the primary interface."""
    try:
        mac: str = hex(uuid.getnode())[2:]
        return ":".join(mac[i:i+2] for i in range(0, len(mac), 2))
    except Exception:
        return "00:00:00:00:00:00"


def get_platform_info() -> Dict[str, str]:
    """Get detailed platform information."""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "hostname": socket.gethostname(),
        "python": platform.python_version()
    }


def get_python_version() -> str:
    """Get Python version string."""
    return sys.version


def ensure_dir(path: UnionType[str, Path]) -> str:
    """Ensure a directory exists."""
    os.makedirs(path, exist_ok=True)
    return str(path)


def safe_filename(filename: str) -> str:
    """Sanitize a filename to be safe for filesystem."""
    invalid_chars: str = '<>:"/\\|?*\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f'
    safe: str = "".join(c if c not in invalid_chars else "_" for c in filename)
    safe = safe.strip(". ")
    if not safe:
        safe = "unnamed_file"
    return safe


def sanitize_path(path: UnionType[str, Path]) -> str:
    """Sanitize a filesystem path."""
    return str(Path(path).resolve())


def get_file_hash(filepath: UnionType[str, Path], algorithm: str = "sha256") -> str:
    """Compute file hash using specified algorithm."""
    hash_func = hashlib.new(algorithm)
    with open(filepath, "rb") as f:
        while True:
            chunk: bytes = f.read(65536)
            if not chunk:
                break
            hash_func.update(chunk)
    return hash_func.hexdigest()


def generate_nonce(size: int = 12) -> bytes:
    """Generate a cryptographic nonce."""
    return os.urandom(size)


def split_nonce_message(data: bytes, nonce_size: int = 12) -> Tuple[bytes, bytes]:
    """Split concatenated nonce and message."""
    if len(data) < nonce_size:
        raise ValueError(f"Data too short: {len(data)} < {nonce_size}")
    return data[:nonce_size], data[nonce_size:]


def is_port_available(port: int, host: str = "0.0.0.0") -> bool:
    """Check if a TCP port is available."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.close()
        return True
    except OSError:
        return False


def get_system_uptime() -> float:
    """Get system uptime in seconds (cross-platform)."""
    if platform.system() == "Windows":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        tick_count: int = kernel32.GetTickCount64()
        return tick_count / 1000.0
    else:
        try:
            with open("/proc/uptime", "r") as f:
                return float(f.readline().split()[0])
        except Exception:
            return 0.0


def get_process_memory() -> int:
    """Get current process memory usage in bytes."""
    import psutil
    process = psutil.Process(os.getpid())
    return process.memory_info().rss


def bytes_to_hex(data: bytes) -> str:
    """Convert bytes to hex string."""
    return data.hex()


def hex_to_bytes(hex_str: str) -> bytes:
    """Convert hex string to bytes."""
    return bytes.fromhex(hex_str)


def chunk_data(data: UnionType[bytes, bytearray], chunk_size: int) -> Iterator[bytes]:
    """Split data into chunks of specified size."""
    for i in range(0, len(data), chunk_size):
        yield data[i:i + chunk_size]


def merge_chunks(chunks: List[bytes]) -> bytes:
    """Merge chunks back into original data."""
    return b"".join(chunks)


def estimate_time(total_bytes: int, transferred_bytes: int,
                  elapsed_seconds: float) -> float:
    """Estimate remaining time in seconds."""
    if transferred_bytes <= 0 or elapsed_seconds <= 0:
        return 0.0
    speed: float = transferred_bytes / elapsed_seconds
    if speed <= 0:
        return 0.0
    remaining: int = total_bytes - transferred_bytes
    return remaining / speed


def calculate_eta(total_bytes: int, transferred_bytes: int,
                  elapsed_seconds: float) -> Optional[str]:
    """Calculate ETA as a formatted string."""
    remaining: float = estimate_time(total_bytes, transferred_bytes, elapsed_seconds)
    if remaining <= 0:
        return None
    return format_duration(remaining)
