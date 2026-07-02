"""Tests for storage modules."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from storage.database import DatabaseManager
from storage.models import Peer, Transfer, ChunkState, TransferHistory


class TestDatabase(unittest.TestCase):
    """Test database operations."""

    @classmethod
    def setUpClass(cls):
        os.environ["SECUREP2P_DB_DIR"] = tempfile.mkdtemp()

    def setUp(self):
        self.db = DatabaseManager()

    def test_save_and_get_peer(self):
        peer = Peer(
            peer_id="test_peer_1",
            display_name="TestPeer",
            host="192.168.1.100",
            port=53333,
            state="disconnected"
        )
        self.db.save_peer(peer)
        loaded = self.db.get_peer("test_peer_1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.display_name, "TestPeer")
        self.assertEqual(loaded.host, "192.168.1.100")

    def test_get_all_peers(self):
        peer1 = Peer(peer_id="p1", display_name="Peer1", host="10.0.0.1", port=53333)
        peer2 = Peer(peer_id="p2", display_name="Peer2", host="10.0.0.2", port=53333)
        self.db.save_peer(peer1)
        self.db.save_peer(peer2)
        peers = self.db.get_all_peers()
        self.assertGreaterEqual(len(peers), 2)

    def test_delete_peer(self):
        peer = Peer(peer_id="delete_me", display_name="DeleteMe", host="1.2.3.4", port=53333)
        self.db.save_peer(peer)
        self.db.delete_peer("delete_me")
        self.assertIsNone(self.db.get_peer("delete_me"))

    def test_save_and_get_transfer(self):
        peer = Peer(peer_id="peer1", display_name="Peer1", host="10.0.0.1", port=53333)
        self.db.save_peer(peer)
        transfer = Transfer(
            transfer_id="trans_1",
            file_name="test.bin",
            file_size=1024,
            direction="send",
            state="pending",
            peer_id="peer1",
            peer_name="Peer1",
            bytes_total=1024
        )
        self.db.save_transfer(transfer)
        loaded = self.db.get_transfer("trans_1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.file_name, "test.bin")
        self.assertEqual(loaded.file_size, 1024)

    def test_save_chunks(self):
        peer = Peer(peer_id="chunk_peer", display_name="ChunkPeer", host="10.0.0.1", port=53333)
        self.db.save_peer(peer)
        transfer = Transfer(
            transfer_id="trans_1", file_name="chunk_test.bin", file_size=1024,
            direction="send", state="pending", peer_id="chunk_peer",
            peer_name="ChunkPeer", bytes_total=1024
        )
        self.db.save_transfer(transfer)
        chunks = [
            ChunkState(chunk_id="c1", transfer_id="trans_1", index=0,
                       offset=0, size=512, state="pending"),
            ChunkState(chunk_id="c2", transfer_id="trans_1", index=1,
                       offset=512, size=512, state="acked"),
        ]
        self.db.save_chunks(chunks)
        loaded = self.db.get_chunks("trans_1")
        self.assertEqual(len(loaded), 2)

    def test_transfer_history(self):
        history = TransferHistory(
            transfer_id="hist_1",
            file_name="old.bin",
            file_size=2048,
            direction="receive",
            peer_id="peer1",
            peer_name="Peer1",
            state="completed",
            started_at=1000.0,
            completed_at=1100.0,
            duration=100.0,
            avg_speed=20.48,
            file_hash="abc123"
        )
        self.db.add_to_history(history)
        entries = self.db.get_history()
        self.assertGreaterEqual(len(entries), 1)

    def test_settings(self):
        self.db.set_setting("theme", "dark")
        self.assertEqual(self.db.get_setting("theme"), "dark")
        self.assertEqual(self.db.get_setting("nonexistent", "default"), "default")

    def test_logs(self):
        import time
        self.db.add_log(time.time(), "INFO", "test", "test message")
        logs = self.db.get_logs()
        self.assertGreaterEqual(len(logs), 1)

    def test_peer_with_metadata(self):
        peer = Peer(
            peer_id="meta_peer",
            display_name="MetaPeer",
            host="10.0.0.1",
            port=53333,
            metadata={"os": "Windows", "version": "1.0"}
        )
        self.db.save_peer(peer)
        loaded = self.db.get_peer("meta_peer")
        self.assertEqual(loaded.metadata.get("os"), "Windows")

    def test_update_peer_state(self):
        peer = Peer(peer_id="state_peer", display_name="StatePeer", host="10.0.0.1", port=53333)
        self.db.save_peer(peer)
        self.db.update_peer_state("state_peer", "connected")
        loaded = self.db.get_peer("state_peer")
        self.assertEqual(loaded.state, "connected")

    def test_delete_transfer(self):
        peer = Peer(peer_id="del_peer", display_name="DelPeer", host="10.0.0.1", port=53333)
        self.db.save_peer(peer)
        transfer = Transfer(
            transfer_id="del_trans",
            file_name="delete.bin", file_size=100,
            direction="send", state="pending", peer_id="del_peer",
            peer_name="DelPeer", bytes_total=100
        )
        self.db.save_transfer(transfer)
        self.db.delete_transfer("del_trans")
        self.assertIsNone(self.db.get_transfer("del_trans"))


if __name__ == "__main__":
    unittest.main()
