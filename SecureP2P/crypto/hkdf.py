from typing import Optional

from cryptography.hazmat.primitives.kdf.hkdf import HKDF, HKDFExpand
from cryptography.hazmat.primitives import hashes


class HKDFDeriver:
    """HKDF-based key derivation using SHA-256."""

    def __init__(self, algorithm: hashes.HashAlgorithm = hashes.SHA256()) -> None:
        self._algorithm: hashes.HashAlgorithm = algorithm

    def derive_key(self, input_key: bytes, salt: Optional[bytes] = None,
                   length: int = 32, context: bytes = b"",
                   info: Optional[bytes] = None) -> bytes:
        hkdf = HKDF(
            algorithm=self._algorithm,
            length=length,
            salt=salt,
            info=info or context,
        )
        return hkdf.derive(input_key)

    def expand(self, prk: bytes, length: int, context: bytes = b"") -> bytes:
        hkdf_expand = HKDFExpand(
            algorithm=self._algorithm,
            length=length,
            info=context,
        )
        return hkdf_expand.derive(prk)

    def extract(self, input_key: bytes, salt: Optional[bytes] = None) -> bytes:
        hkdf = HKDF(
            algorithm=self._algorithm,
            length=32,
            salt=salt,
            info=b"",
        )
        hkdf.derive(input_key)
        return hkdf._hkdf.expand(  # type: ignore
            hkdf._hkdf.extract(input_key, salt),  # type: ignore
            b"",
            32
        )

    def derive_multiple_keys(self, input_key: bytes, salt: Optional[bytes] = None,
                              count: int = 2, length: int = 32,
                              context: bytes = b"") -> list:
        keys: list = []
        for i in range(count):
            ctx: bytes = context + bytes([i])
            key: bytes = self.derive_key(input_key, salt, length, ctx)
            keys.append(key)
        return keys
