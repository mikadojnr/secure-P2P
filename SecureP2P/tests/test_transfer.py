"""Tests for transfer modules."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from transfer.chunk_manager import ChunkManager
from transfer.compressor import Compressor
from transfer.resumable import ResumableTransfer


class TestChunkManager(unittest.TestCase):
    """Test chunk management."""

    def setUp(self):
        self.manager = ChunkManager()

    def test_init_send(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"x" * 100000)
            f.flush()
            fname = f.name
        try:
            chunks = self.manager.init_send("test1", fname, 16384)
            self.assertGreater(len(chunks), 0)
            self.assertEqual(chunks[0].index, 0)
            self.assertEqual(chunks[0].state, "pending")
            self.assertEqual(chunks[0].transfer_id, "test1")
        finally:
            os.unlink(fname)

    def test_init_receive(self):
        chunks = self.manager.init_receive("test2", 50000, 16384)
        self.assertGreater(len(chunks), 0)
        self.assertEqual(chunks[-1].size, 50000 - (16384 * 3))

    def test_get_next_pending_chunk(self):
        self.manager.init_receive("test3", 1000, 512)
        chunk = self.manager.get_next_pending_chunk("test3")
        self.assertIsNotNone(chunk)
        self.assertEqual(chunk.state, "sent")

    def test_receive_and_assemble(self):
        manager = ChunkManager()
        test_data = b"Hello SecureP2P World!" * 100
        file_size = len(test_data)
        chunk_size = 512
        manager.init_receive("test4", file_size, chunk_size)
        for i in range(0, file_size, chunk_size):
            chunk_data = test_data[i:i + chunk_size]
            idx = i // chunk_size
            manager.receive_chunk("test4", idx, chunk_data)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".test") as f:
            output = f.name
        try:
            success = manager.assemble_file("test4", output)
            self.assertTrue(success)
            with open(output, "rb") as f:
                result = f.read()
            self.assertEqual(result, test_data)
        finally:
            os.unlink(output)

    def test_chunk_progress(self):
        self.manager.init_receive("test5", 1000, 256)
        acked, total, failed = self.manager.get_chunk_progress("test5")
        self.assertEqual(acked, 0)
        self.assertEqual(total, 4)
        self.assertEqual(failed, 0)

    def test_ack_chunk(self):
        self.manager.init_receive("test6", 1000, 256)
        self.manager.ack_chunk("test6", 0)
        acked, total, failed = self.manager.get_chunk_progress("test6")
        self.assertEqual(acked, 1)

    def test_cleanup(self):
        self.manager.init_receive("test7", 100, 64)
        self.manager.cleanup("test7")
        self.assertIsNone(self.manager._chunks.get("test7"))

    def test_mark_chunk_failed(self):
        self.manager.init_receive("test8", 100, 64)
        self.manager.mark_chunk_failed("test8", 0)
        acked, total, failed = self.manager.get_chunk_progress("test8")
        self.assertEqual(failed, 1)


class TestCompressor(unittest.TestCase):
    """Test compression."""

    def setUp(self):
        self.compressor = Compressor()

    def test_compress_decompress(self):
        data = b"Hello World! " * 1000
        compressed = self.compressor.compress(data)
        self.assertLess(len(compressed), len(data))
        decompressed = self.compressor.decompress(compressed)
        self.assertEqual(data, decompressed)

    def test_small_data(self):
        data = b"small"
        compressed = self.compressor.compress(data)
        decompressed = self.compressor.decompress(compressed)
        self.assertEqual(data, decompressed)

    def test_compression_ratio(self):
        data = b"AAAAA" * 10000
        self.compressor.compress(data)
        ratio = self.compressor.get_ratio()
        self.assertLess(ratio, 1.0)
        self.assertGreater(ratio, 0.0)

    def test_savings(self):
        data = b"AAAAA" * 10000
        self.compressor.compress(data)
        savings = self.compressor.get_savings()
        self.assertGreater(savings, 0)

    def test_select_level(self):
        self.assertEqual(self.compressor.select_level("excellent"), 1)
        self.assertEqual(self.compressor.select_level("good"), 3)
        self.assertEqual(self.compressor.select_level("average"), 10)
        self.assertEqual(self.compressor.select_level("poor"), 10)

    def test_reset_stats(self):
        data = b"test" * 1000
        self.compressor.compress(data)
        self.compressor.reset_stats()
        self.assertEqual(self.compressor._total_original, 0)

    def test_statistics(self):
        data = b"test data" * 100
        self.compressor.compress(data)
        stats = self.compressor.statistics
        self.assertIn("total_original", stats)
        self.assertIn("ratio", stats)

    def test_should_compress(self):
        self.assertTrue(self.compressor.should_compress(1000, "poor"))
        self.assertTrue(self.compressor.should_compress(1000, "average"))
        self.assertTrue(self.compressor.should_compress(5000, "good"))
        self.assertFalse(self.compressor.should_compress(100, "good"))
        self.assertFalse(self.compressor.should_compress(100, "excellent"))


class TestResumableTransfer(unittest.TestCase):
    """Test transfer resume capability."""

    def setUp(self):
        self.resumable = ResumableTransfer()

    def test_get_state_file(self):
        path = self.resumable._get_state_file("test_transfer_123")
        self.assertTrue(path.endswith("test_transfer_123.json"))

    def test_save_and_load_state(self):
        from storage.models import Transfer, ChunkState
        transfer = Transfer(
            transfer_id="resume_test_1",
            file_name="test.bin",
            file_path="/tmp/test.bin",
            file_size=1000,
            direction="send",
            peer_id="peer123",
            peer_name="TestPeer"
        )
        chunks = [
            ChunkState(chunk_id="c1", transfer_id="resume_test_1", index=0,
                       offset=0, size=500, state="acked"),
            ChunkState(chunk_id="c2", transfer_id="resume_test_1", index=1,
                       offset=500, size=500, state="pending"),
        ]
        self.resumable.save_state(transfer, chunks)
        result = self.resumable.load_state("resume_test_1")
        self.assertIsNotNone(result)
        loaded_transfer, loaded_chunks = result
        self.assertEqual(loaded_transfer.file_name, "test.bin")
        self.assertEqual(len(loaded_chunks), 2)
        self.assertEqual(loaded_chunks[0].state, "acked")
        self.resumable.delete_state("resume_test_1")

    def test_delete_state(self):
        from storage.models import Transfer, ChunkState
        transfer = Transfer(
            transfer_id="resume_delete_test",
            file_name="del.bin", file_path="/tmp/del.bin",
            file_size=100, direction="send"
        )
        chunks = [ChunkState(chunk_id="c1", transfer_id="resume_delete_test",
                             index=0, offset=0, size=100, state="pending")]
        self.resumable.save_state(transfer, chunks)
        state_file = self.resumable._get_state_file("resume_delete_test")
        self.assertTrue(os.path.exists(state_file))
        self.resumable.delete_state("resume_delete_test")
        self.assertFalse(os.path.exists(state_file))


if __name__ == "__main__":
    unittest.main()
