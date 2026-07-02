import hashlib
import hmac
from typing import Optional


class Hasher:
    """SHA-256 hashing utility for integrity verification."""

    @staticmethod
    def hash_data(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def hash_file(filepath: str, chunk_size: int = 65536) -> str:
        sha256: hashlib._Hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            while True:
                chunk: bytes = f.read(chunk_size)
                if not chunk:
                    break
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def hash_chunk(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def verify_hash(data: bytes, expected_hash: str) -> bool:
        actual: str = hashlib.sha256(data).hexdigest()
        return hmac.compare_digest(actual, expected_hash)

    @staticmethod
    def verify_file_hash(filepath: str, expected_hash: str,
                          chunk_size: int = 65536) -> bool:
        actual: str = Hasher.hash_file(filepath, chunk_size)
        return hmac.compare_digest(actual, expected_hash)

    @staticmethod
    def double_hash(data: bytes) -> str:
        first: bytes = hashlib.sha256(data).digest()
        return hashlib.sha256(first).hexdigest()

    @staticmethod
    def hmac_sha256(key: bytes, message: bytes) -> bytes:
        return hmac.new(key, message, hashlib.sha256).digest()

    @staticmethod
    def verify_hmac(key: bytes, message: bytes, mac: bytes) -> bool:
        expected: bytes = Hasher.hmac_sha256(key, message)
        return hmac.compare_digest(expected, mac)

    @staticmethod
    def hash_iterative(data: bytes, iterations: int = 1000) -> str:
        result: bytes = data
        for _ in range(iterations):
            result = hashlib.sha256(result).digest()
        return result.hex()
