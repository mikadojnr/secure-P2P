"""Tests for utility modules."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.helpers import (
    create_id, format_bytes, format_duration, format_speed,
    get_local_ip, safe_filename, get_file_hash, generate_nonce,
    split_nonce_message, is_port_available, bytes_to_hex, hex_to_bytes,
    chunk_data, merge_chunks, estimate_time, calculate_eta, ensure_dir
)
from utils.config import ConfigManager


class TestHelpers(unittest.TestCase):
    """Test utility helper functions."""

    def test_create_id(self):
        id1 = create_id()
        id2 = create_id()
        self.assertEqual(len(id1), 32)
        self.assertNotEqual(id1, id2)

    def test_format_bytes(self):
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(1023), "1023.00 B")
        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(1048576), "1.00 MB")
        self.assertEqual(format_bytes(1073741824), "1.00 GB")

    def test_format_duration(self):
        self.assertEqual(format_duration(30), "30s")
        self.assertEqual(format_duration(90), "1m 30s")
        self.assertEqual(format_duration(3661), "1h 1m")

    def test_format_speed(self):
        result = format_speed(1024)
        self.assertEqual(result, "1.00 KB/s")

    def test_get_local_ip(self):
        ip = get_local_ip()
        self.assertTrue(ip.count(".") == 3)

    def test_safe_filename(self):
        self.assertEqual(safe_filename("normal.txt"), "normal.txt")
        self.assertNotIn("/", safe_filename("file/with/slashes.txt"))
        self.assertNotIn("\x00", safe_filename("bad\x00file.txt"))
        self.assertNotEqual(safe_filename(""), "")

    def test_generate_nonce(self):
        nonce = generate_nonce(12)
        self.assertEqual(len(nonce), 12)
        nonce2 = generate_nonce(12)
        self.assertNotEqual(nonce, nonce2)

    def test_split_nonce_message(self):
        nonce = b"123456789012"
        msg = b"hello world"
        combined = nonce + msg
        extracted_nonce, extracted_msg = split_nonce_message(combined, 12)
        self.assertEqual(nonce, extracted_nonce)
        self.assertEqual(msg, extracted_msg)

    def test_split_nonce_message_too_short(self):
        with self.assertRaises(ValueError):
            split_nonce_message(b"short", 12)

    def test_bytes_hex_conversion(self):
        data = b"test data \x00\xff"
        hex_str = bytes_to_hex(data)
        restored = hex_to_bytes(hex_str)
        self.assertEqual(data, restored)

    def test_chunk_and_merge(self):
        data = b"x" * 10000
        chunks = list(chunk_data(data, 1024))
        self.assertEqual(len(chunks), 10)
        merged = merge_chunks(chunks)
        self.assertEqual(data, merged)

    def test_estimate_time(self):
        eta = estimate_time(1000, 500, 10)
        self.assertAlmostEqual(eta, 10.0)

    def test_calculate_eta(self):
        eta = calculate_eta(1000, 500, 10)
        self.assertIsNotNone(eta)

    def test_ensure_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = os.path.join(tmpdir, "new", "dir")
            path = ensure_dir(new_dir)
            self.assertTrue(os.path.exists(new_dir))
            self.assertEqual(path, new_dir)

    def test_is_port_available(self):
        available = is_port_available(59999)
        self.assertIsInstance(available, bool)


class TestConfigManager(unittest.TestCase):
    """Test configuration management."""

    def setUp(self):
        self.config = ConfigManager()

    def test_default_values(self):
        self.assertIsNotNone(self.config.download_dir)
        self.assertIsNotNone(self.config.chunk_size)
        self.assertIsNotNone(self.config.compression)
        self.assertIsInstance(self.config.dark_mode, bool)

    def test_set_and_get(self):
        self.config.set("test_key", "test_value")
        self.assertEqual(self.config.get("test_key"), "test_value")

    def test_download_dir_property(self):
        original = self.config.download_dir
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                self.config.download_dir = tmpdir
                self.assertEqual(self.config.download_dir, tmpdir)
        finally:
            self.config.download_dir = original

    def test_get_all(self):
        all_settings = self.config.get_all()
        self.assertIn("download_dir", all_settings)
        self.assertIn("dark_mode", all_settings)


if __name__ == "__main__":
    unittest.main()
