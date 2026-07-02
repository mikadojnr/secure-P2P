import os
from typing import Optional, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey

from crypto.hkdf import HKDFDeriver
from utils.constants import KEY_SIZE, SALT_SIZE


class KeyExchange:
    """X25519 key exchange with Perfect Forward Secrecy."""

    def __init__(self) -> None:
        self._private_key: X25519PrivateKey = X25519PrivateKey.generate()
        self._public_key: X25519PublicKey = self._private_key.public_key()
        self._shared_secret: Optional[bytes] = None
        self._session_key: Optional[bytes] = None
        self._salt: Optional[bytes] = None
        self._hkdf: HKDFDeriver = HKDFDeriver()

    @property
    def public_bytes(self) -> bytes:
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )

    @property
    def private_bytes(self) -> bytes:
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )

    @property
    def session_key(self) -> Optional[bytes]:
        return self._session_key

    @property
    def salt(self) -> Optional[bytes]:
        return self._salt

    def generate_salt(self) -> bytes:
        self._salt = os.urandom(SALT_SIZE)
        return self._salt

    def compute_shared_secret(self, peer_public_bytes: bytes) -> bytes:
        peer_public_key: X25519PublicKey = X25519PublicKey.from_public_bytes(peer_public_bytes)
        self._shared_secret = self._private_key.exchange(peer_public_key)
        return self._shared_secret

    def derive_session_key(self, salt: Optional[bytes] = None) -> bytes:
        if self._shared_secret is None:
            raise ValueError("Shared secret not computed. Call compute_shared_secret first.")
        if salt is not None:
            self._salt = salt
        if self._salt is None:
            self.generate_salt()
        self._session_key = self._hkdf.derive_key(
            self._shared_secret,
            salt=self._salt,
            length=KEY_SIZE,
            context=b"securep2p-session-key"
        )
        return self._session_key

    def perform_key_exchange(self, peer_public_bytes: bytes,
                              peer_salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        shared_secret: bytes = self.compute_shared_secret(peer_public_bytes)
        if peer_salt:
            self._salt = peer_salt
        else:
            self.generate_salt()
        session_key: bytes = self.derive_session_key()
        return session_key, self._salt if self._salt else b""

    def serialize_public_key(self) -> bytes:
        return self.public_bytes

    @staticmethod
    def deserialize_public_key(data: bytes) -> X25519PublicKey:
        return X25519PublicKey.from_public_bytes(data)

    def generate_ephemeral_key(self) -> Tuple[bytes, bytes]:
        new_exchange: "KeyExchange" = KeyExchange()
        return new_exchange.public_bytes, new_exchange.private_bytes

    def rotate_keys(self) -> None:
        self._private_key = X25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        self._shared_secret = None
        self._session_key = None
        self._salt = None

    def __repr__(self) -> str:
        return f"KeyExchange(session_key={'set' if self._session_key else 'not set'})"
