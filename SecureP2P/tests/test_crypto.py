"""Tests for cryptography modules."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from crypto.key_exchange import KeyExchange
from crypto.aes_engine import AESCipher, AESEngine
from crypto.hkdf import HKDFDeriver
from crypto.hashing import Hasher


class TestKeyExchange(unittest.TestCase):
    """Test X25519 key exchange."""

    def test_generate_keypair(self):
        ke = KeyExchange()
        self.assertEqual(len(ke.public_bytes), 32)
        self.assertEqual(len(ke.private_bytes), 32)

    def test_shared_secret(self):
        alice = KeyExchange()
        bob = KeyExchange()
        alice_secret = alice.compute_shared_secret(bob.public_bytes)
        bob_secret = bob.compute_shared_secret(alice.public_bytes)
        self.assertEqual(alice_secret, bob_secret)

    def test_session_key_derivation(self):
        alice = KeyExchange()
        bob = KeyExchange()
        alice_salt = alice.generate_salt()
        alice.compute_shared_secret(bob.public_bytes)
        bob.compute_shared_secret(alice.public_bytes)
        alice_key = alice.derive_session_key(alice_salt)
        bob_key = bob.derive_session_key(alice_salt)
        self.assertEqual(alice_key, bob_key)
        self.assertEqual(len(alice_key), 32)

    def test_perfect_forward_secrecy(self):
        alice = KeyExchange()
        bob = KeyExchange()
        key1, salt1 = alice.perform_key_exchange(bob.public_bytes)
        alice.rotate_keys()
        bob.rotate_keys()
        key2, salt2 = alice.perform_key_exchange(bob.public_bytes)
        self.assertNotEqual(key1, key2)

    def test_serialization(self):
        ke = KeyExchange()
        pub_bytes = ke.serialize_public_key()
        restored = KeyExchange.deserialize_public_key(pub_bytes)
        self.assertIsNotNone(restored)


class TestAESCipher(unittest.TestCase):
    """Test AES-256-GCM encryption."""

    def setUp(self):
        self.key = AESCipher.generate_key()
        self.cipher = AESCipher(self.key)

    def test_key_size(self):
        self.assertEqual(len(self.key), 32)

    def test_encrypt_decrypt(self):
        plaintext = b"Hello SecureP2P World!"
        ciphertext = self.cipher.encrypt(plaintext)
        self.assertNotEqual(plaintext, ciphertext)
        decrypted = self.cipher.decrypt(ciphertext)
        self.assertEqual(plaintext, decrypted)

    def test_empty_data(self):
        plaintext = b""
        ciphertext = self.cipher.encrypt(plaintext)
        decrypted = self.cipher.decrypt(ciphertext)
        self.assertEqual(plaintext, decrypted)

    def test_large_data(self):
        plaintext = os.urandom(1024 * 1024)  # 1 MB
        ciphertext = self.cipher.encrypt(plaintext)
        decrypted = self.cipher.decrypt(ciphertext)
        self.assertEqual(plaintext, decrypted)

    def test_authenticated_encryption(self):
        plaintext = b"test data"
        aad = b"additional data"
        nonce, ct = self.cipher.encrypt_with_aad(plaintext, aad)
        decrypted = self.cipher.decrypt_with_aad(nonce, ct, aad)
        self.assertEqual(plaintext, decrypted)

    def test_tampered_ciphertext(self):
        plaintext = b"important data"
        ciphertext = self.cipher.encrypt(plaintext)
        tampered = bytearray(ciphertext)
        tampered[15] ^= 0x01
        with self.assertRaises(Exception):
            self.cipher.decrypt(bytes(tampered))

    def test_wrong_key(self):
        plaintext = b"secret message"
        ciphertext = self.cipher.encrypt(plaintext)
        wrong_cipher = AESCipher(AESCipher.generate_key())
        with self.assertRaises(Exception):
            wrong_cipher.decrypt(ciphertext)

    def test_file_chunk_encryption(self):
        chunk = b"file chunk data" * 100
        ct = self.cipher.encrypt_file_chunk(chunk, 42)
        decrypted = self.cipher.decrypt_file_chunk(ct, 42)
        self.assertEqual(chunk, decrypted)

    def test_wrong_chunk_index(self):
        chunk = b"chunk data"
        ct = self.cipher.encrypt_file_chunk(chunk, 1)
        with self.assertRaises(Exception):
            self.cipher.decrypt_file_chunk(ct, 2)

    def test_nonce_uniqueness(self):
        plaintext = b"test"
        ct1 = self.cipher.encrypt(plaintext)
        ct2 = self.cipher.encrypt(plaintext)
        self.assertNotEqual(ct1[:12], ct2[:12])


class TestAESEngine(unittest.TestCase):
    """Test AES engine management."""

    def setUp(self):
        self.engine = AESEngine()

    def test_create_and_get_cipher(self):
        key = AESCipher.generate_key()
        cipher = self.engine.create_cipher("session1", key)
        self.assertIsNotNone(cipher)
        retrieved = self.engine.get_cipher("session1")
        self.assertIs(cipher, retrieved)

    def test_remove_cipher(self):
        key = AESCipher.generate_key()
        self.engine.create_cipher("session1", key)
        self.engine.remove_cipher("session1")
        self.assertIsNone(self.engine.get_cipher("session1"))

    def test_clear(self):
        key = AESCipher.generate_key()
        self.engine.create_cipher("s1", key)
        self.engine.create_cipher("s2", key)
        self.engine.clear()
        self.assertIsNone(self.engine.get_cipher("s1"))
        self.assertIsNone(self.engine.get_cipher("s2"))


class TestHKDF(unittest.TestCase):
    """Test HKDF key derivation."""

    def setUp(self):
        self.hkdf = HKDFDeriver()

    def test_key_derivation(self):
        ikm = os.urandom(32)
        key = self.hkdf.derive_key(ikm, length=32)
        self.assertEqual(len(key), 32)

    def test_deterministic(self):
        ikm = os.urandom(32)
        salt = os.urandom(16)
        key1 = self.hkdf.derive_key(ikm, salt, 32)
        key2 = self.hkdf.derive_key(ikm, salt, 32)
        self.assertEqual(key1, key2)

    def test_different_salt(self):
        ikm = os.urandom(32)
        key1 = self.hkdf.derive_key(ikm, b"salt1", 32)
        key2 = self.hkdf.derive_key(ikm, b"salt2", 32)
        self.assertNotEqual(key1, key2)

    def test_multiple_keys(self):
        ikm = os.urandom(32)
        keys = self.hkdf.derive_multiple_keys(ikm, count=3, length=32)
        self.assertEqual(len(keys), 3)
        self.assertNotEqual(keys[0], keys[1])
        self.assertNotEqual(keys[1], keys[2])


class TestHasher(unittest.TestCase):
    """Test SHA-256 hashing."""

    def test_hash_data(self):
        data = b"test data"
        h = Hasher.hash_data(data)
        self.assertEqual(len(h), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in h))

    def test_hash_consistency(self):
        data = b"consistent"
        self.assertEqual(Hasher.hash_data(data), Hasher.hash_data(data))

    def test_verify_hash(self):
        data = b"verify me"
        h = Hasher.hash_data(data)
        self.assertTrue(Hasher.verify_hash(data, h))

    def test_verify_wrong_hash(self):
        data = b"correct"
        wrong = "0000000000000000000000000000000000000000000000000000000000000000"
        self.assertFalse(Hasher.verify_hash(data, wrong))

    def test_file_hash(self):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"file content for hash")
            f.flush()
            fname = f.name
        try:
            h = Hasher.hash_file(fname)
            self.assertEqual(len(h), 64)
        finally:
            os.unlink(fname)

    def test_double_hash(self):
        data = b"double hash"
        h = Hasher.double_hash(data)
        self.assertEqual(len(h), 64)

    def test_hmac(self):
        key = b"secret key"
        msg = b"message"
        mac = Hasher.hmac_sha256(key, msg)
        self.assertEqual(len(mac), 32)
        self.assertTrue(Hasher.verify_hmac(key, msg, mac))
        self.assertFalse(Hasher.verify_hmac(key, b"wrong", mac))


if __name__ == "__main__":
    unittest.main()
