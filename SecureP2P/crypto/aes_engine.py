import os
from typing import Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from utils.constants import KEY_SIZE, NONCE_SIZE, TAG_SIZE


class AESCipher:
    """AES-256-GCM encryption and decryption with authenticated encryption."""

    def __init__(self, key: bytes) -> None:
        if len(key) != KEY_SIZE:
            raise ValueError(f"Key must be {KEY_SIZE} bytes, got {len(key)}")
        self._key: bytes = key
        self._aesgcm: AESGCM = AESGCM(key)
        self._nonce_counter: int = 0

    @staticmethod
    def generate_key() -> bytes:
        return AESGCM.generate_key(bit_length=256)

    def encrypt(self, plaintext: bytes, associated_data: Optional[bytes] = None) -> bytes:
        nonce: bytes = self._generate_nonce()
        ciphertext: bytes = self._aesgcm.encrypt(nonce, plaintext, associated_data)
        return nonce + ciphertext

    def decrypt(self, ciphertext: bytes, associated_data: Optional[bytes] = None) -> bytes:
        if len(ciphertext) < NONCE_SIZE + TAG_SIZE:
            raise ValueError(f"Ciphertext too short: {len(ciphertext)} bytes")
        nonce: bytes = ciphertext[:NONCE_SIZE]
        ct: bytes = ciphertext[NONCE_SIZE:]
        return self._aesgcm.decrypt(nonce, ct, associated_data)

    def encrypt_with_aad(self, plaintext: bytes, aad: bytes) -> Tuple[bytes, bytes]:
        nonce: bytes = self._generate_nonce()
        ciphertext: bytes = self._aesgcm.encrypt(nonce, plaintext, aad)
        return nonce, ciphertext

    def decrypt_with_aad(self, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
        return self._aesgcm.decrypt(nonce, ciphertext, aad)

    def _generate_nonce(self) -> bytes:
        self._nonce_counter += 1
        counter_bytes: bytes = self._nonce_counter.to_bytes(4, "big")
        random_bytes: bytes = os.urandom(NONCE_SIZE - 4)
        return random_bytes[:8] + counter_bytes

    def encrypt_message(self, plaintext: bytes) -> bytes:
        return self.encrypt(plaintext)

    def decrypt_message(self, ciphertext: bytes) -> bytes:
        return self.decrypt(ciphertext)

    def encrypt_file_chunk(self, chunk_data: bytes, chunk_index: int) -> bytes:
        aad: bytes = str(chunk_index).encode()
        return self.encrypt(chunk_data, aad)

    def decrypt_file_chunk(self, encrypted_data: bytes, chunk_index: int) -> bytes:
        aad: bytes = str(chunk_index).encode()
        return self.decrypt(encrypted_data, aad)


class AESEngine:
    """High-level AES encryption engine managing multiple cipher instances."""

    def __init__(self) -> None:
        self._ciphers: dict = {}

    def create_cipher(self, key_id: str, key: bytes) -> AESCipher:
        cipher: AESCipher = AESCipher(key)
        self._ciphers[key_id] = cipher
        return cipher

    def get_cipher(self, key_id: str) -> Optional[AESCipher]:
        return self._ciphers.get(key_id)

    def remove_cipher(self, key_id: str) -> None:
        self._ciphers.pop(key_id, None)

    def clear(self) -> None:
        self._ciphers.clear()
