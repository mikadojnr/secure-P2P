"""Integration tests for the SecureP2P application."""
import asyncio
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from crypto.key_exchange import KeyExchange
from crypto.aes_engine import AESCipher
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class TestEndToEndEncryption(unittest.TestCase):
    """End-to-end encryption integration test."""

    def test_full_key_exchange_and_encryption(self):
        alice = KeyExchange()
        bob = KeyExchange()

        alice_salt = alice.generate_salt()
        alice_secret = alice.compute_shared_secret(bob.public_bytes)
        bob_secret = bob.compute_shared_secret(alice.public_bytes)
        self.assertEqual(alice_secret, bob_secret)

        alice_key = alice.derive_session_key(alice_salt)
        bob_key = bob.derive_session_key(alice_salt)
        self.assertEqual(alice_key, bob_key)

        alice_cipher = AESCipher(alice_key)
        bob_cipher = AESCipher(bob_key)

        message = b"Secret file content for transfer"
        encrypted = alice_cipher.encrypt(message)
        decrypted = bob_cipher.decrypt(encrypted)
        self.assertEqual(message, decrypted)

    def test_perfect_forward_secrecy(self):
        alice1 = KeyExchange()
        bob1 = KeyExchange()
        alice1.generate_salt()
        alice1.compute_shared_secret(bob1.public_bytes)
        bob1.compute_shared_secret(alice1.public_bytes)
        key1 = alice1.derive_session_key()

        alice2 = KeyExchange()
        bob2 = KeyExchange()
        alice2.generate_salt()
        alice2.compute_shared_secret(bob2.public_bytes)
        bob2.compute_shared_secret(alice2.public_bytes)
        key2 = alice2.derive_session_key()

        self.assertNotEqual(key1, key2)

    def test_large_file_encryption(self):
        key = AESGCM.generate_key(bit_length=256)
        aesgcm = AESGCM(key)
        large_data = os.urandom(10 * 1024 * 1024)  # 10 MB
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, large_data, None)
        pt = aesgcm.decrypt(nonce, ct, None)
        self.assertEqual(large_data, pt)
        overhead = len(ct) - len(large_data)
        self.assertLess(overhead / len(large_data), 0.0001)


class TestCompressionAndEncryption(unittest.TestCase):
    """Test compression before encryption workflow."""

    def test_compress_then_encrypt(self):
        import pyzstd
        from crypto.hashing import Hasher

        data = b"A" * 100000 + b"B" * 100000 + b"C" * 100000
        original_hash = Hasher.hash_data(data)
        compressed = pyzstd.compress(data, 3)
        self.assertLess(len(compressed), len(data))
        key = AESGCM.generate_key(bit_length=256)
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        encrypted = aesgcm.encrypt(nonce, compressed, None)
        decrypted = aesgcm.decrypt(nonce, encrypted, None)
        decompressed = pyzstd.decompress(decrypted)
        self.assertEqual(Hasher.hash_data(decompressed), original_hash)


class TestChunkAndReassemble(unittest.TestCase):
    """Test chunk and reassemble workflow."""

    def test_chunk_reassemble_integrity(self):
        data = os.urandom(100000)
        chunk_size = 16384
        chunks = []
        for i in range(0, len(data), chunk_size):
            chunks.append(data[i:i + chunk_size])
        reassembled = b"".join(chunks)
        self.assertEqual(data, reassembled)

    def test_chunk_hash_verification(self):
        from crypto.hashing import Hasher
        chunk = b"test chunk data"
        h = Hasher.hash_chunk(chunk)
        self.assertTrue(Hasher.verify_hash(chunk, h))


class TestNetworkProtocol(unittest.TestCase):
    """Test protocol message format."""

    def test_message_header_format(self):
        import struct
        magic = b"SECP"
        msg_type = 1
        length = 100
        header = struct.pack("!4sII", magic, msg_type, length)
        self.assertEqual(len(header), 12)
        unpacked = struct.unpack("!4sII", header)
        self.assertEqual(unpacked[0], magic)
        self.assertEqual(unpacked[1], msg_type)
        self.assertEqual(unpacked[2], length)


class TestBandwidthAdaptation(unittest.TestCase):
    """Test bandwidth adaptation logic."""

    def test_adaptive_chunk_size_selection(self):
        from network.bandwidth_estimator import BandwidthEstimator
        estimator = BandwidthEstimator()
        test_cases = [
            (10000, 32 * 1024),
            (50000, 32 * 1024),
            (70000, 64 * 1024),
            (300000, 256 * 1024),
            (2000000, 512 * 1024),
        ]
        for bw, expected_chunk in test_cases:
            estimator._current_bw = bw
            chunk = estimator.get_recommended_chunk_size()
            self.assertEqual(chunk, expected_chunk,
                f"BW={bw}: expected {expected_chunk}, got {chunk}")

    def test_adaptive_compression_selection(self):
        from network.bandwidth_estimator import BandwidthEstimator
        estimator = BandwidthEstimator()
        estimator._current_bw = 10000
        self.assertEqual(estimator.get_recommended_compression(), "maximum")
        estimator._current_bw = 300000
        self.assertEqual(estimator.get_recommended_compression(), "balanced")
        estimator._current_bw = 2000000
        self.assertEqual(estimator.get_recommended_compression(), "fast")


if __name__ == "__main__":
    unittest.main()
