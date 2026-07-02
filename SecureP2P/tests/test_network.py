"""Tests for network modules."""
import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from network.bandwidth_estimator import BandwidthEstimator
from network.stun_client import STUNClient


class TestBandwidthEstimator(unittest.TestCase):
    """Test bandwidth estimation."""

    def setUp(self):
        self.estimator = BandwidthEstimator()

    def test_initial_state(self):
        self.assertEqual(self.estimator.bandwidth, 0.0)
        self.assertEqual(self.estimator.avg_rtt, 0.0)
        self.assertEqual(self.estimator.loss_rate, 0.0)

    def test_record_throughput(self):
        bw = self.estimator.record_throughput(65536)
        self.assertGreater(bw, 0)

    def test_record_rtt(self):
        self.estimator.record_rtt(0.050)
        self.estimator.record_rtt(0.060)
        self.assertAlmostEqual(self.estimator.avg_rtt, 0.055, places=3)

    def test_record_packet_loss(self):
        self.estimator.record_packet_loss(True)
        self.estimator.record_packet_loss(False)
        self.estimator.record_packet_loss(True)
        self.assertAlmostEqual(self.estimator.loss_rate, 2/3)

    def test_quality_poor(self):
        self.estimator._current_bw = 10000  # 10 KB/s
        self.assertEqual(self.estimator.get_quality(), "poor")

    def test_quality_excellent(self):
        self.estimator._current_bw = 2 * 1024 * 1024  # 2 MB/s
        self.assertEqual(self.estimator.get_quality(), "excellent")

    def test_recommended_chunk_size(self):
        self.estimator._current_bw = 30000
        self.assertEqual(self.estimator.get_recommended_chunk_size(), 32 * 1024)

        self.estimator._current_bw = 500 * 1024
        self.assertEqual(self.estimator.get_recommended_chunk_size(), 256 * 1024)

    def test_recommended_compression(self):
        self.estimator._current_bw = 30000
        self.assertEqual(self.estimator.get_recommended_compression(), "maximum")

        self.estimator._current_bw = 2 * 1024 * 1024
        self.assertEqual(self.estimator.get_recommended_compression(), "fast")

    def test_should_throttle(self):
        self.estimator.record_packet_loss(True)
        self.estimator.record_packet_loss(True)
        self.estimator.record_packet_loss(True)
        self.assertTrue(self.estimator.should_throttle())

    def test_reset(self):
        self.estimator.record_throughput(65536)
        self.estimator.record_rtt(0.1)
        self.estimator.record_packet_loss(True)
        self.estimator.reset()
        self.assertEqual(self.estimator.bandwidth, 0.0)
        self.assertEqual(self.estimator.avg_rtt, 0.0)
        self.assertEqual(self.estimator.loss_rate, 0.0)

    def test_statistics(self):
        self.estimator.record_throughput(65536)
        stats = self.estimator.get_statistics()
        self.assertIn("bandwidth", stats)
        self.assertIn("quality", stats)
        self.assertIn("recommended_chunk", stats)
        self.assertIn("recommended_compression", stats)

    def test_get_estimated_capacity(self):
        self.estimator._current_bw = 100000
        self.estimator._loss_rate = 0.1
        cap = self.estimator.get_estimated_capacity()
        self.assertAlmostEqual(cap, 90000)


class TestSTUNClient(unittest.TestCase):
    """Test STUN client."""

    @patch("socket.socket")
    def test_create_binding_request(self, mock_socket):
        client = STUNClient(servers=["stun.l.google.com:19302"])
        request = client._create_binding_request()
        self.assertEqual(len(request), 20)
        self.assertEqual(request[:2], b"\x00\x01")

    def test_default_servers(self):
        client = STUNClient()
        self.assertTrue(len(client._servers) > 0)

    def test_add_server(self):
        client = STUNClient(servers=[])
        client.add_server("custom.stun.com:3478")
        self.assertIn("custom.stun.com:3478", client._servers)

    def test_initial_state(self):
        client = STUNClient()
        self.assertIsNone(client.public_ip)
        self.assertIsNone(client.public_port)
        self.assertEqual(client.nat_type, "unknown")


if __name__ == "__main__":
    unittest.main()
