import asyncio
import logging
import random
import socket
import struct
import time
from typing import Dict, List, Optional, Tuple

from utils.constants import STUN_SERVERS

logger = logging.getLogger(__name__)

STUN_MAGIC_COOKIE: int = 0x2112A442
STUN_BINDING_REQUEST: int = 0x0001
STUN_BINDING_RESPONSE: int = 0x0101
STUN_ATTR_MAPPED_ADDRESS: int = 0x0001
STUN_ATTR_XOR_MAPPED_ADDRESS: int = 0x0020


class STUNClient:
    """STUN client for NAT type detection and hole punching."""

    def __init__(self, servers: Optional[List[str]] = None) -> None:
        self._servers: List[str] = servers or list(STUN_SERVERS)
        self._public_ip: Optional[str] = None
        self._public_port: Optional[int] = None
        self._nat_type: str = "unknown"
        self._local_ip: Optional[str] = None
        self._local_port: Optional[int] = None

    @property
    def public_ip(self) -> Optional[str]:
        return self._public_ip

    @property
    def public_port(self) -> Optional[int]:
        return self._public_port

    @property
    def nat_type(self) -> str:
        return self._nat_type

    def _create_binding_request(self) -> bytes:
        transaction_id: bytes = bytes(random.randint(0, 255) for _ in range(12))
        header: bytes = struct.pack("!HHI", STUN_BINDING_REQUEST, 0, STUN_MAGIC_COOKIE)
        return header + transaction_id

    def _parse_response(self, response: bytes) -> Tuple[Optional[str], Optional[int]]:
        if len(response) < 20:
            return None, None

        msg_type: int = struct.unpack("!H", response[:2])[0]
        if msg_type != STUN_BINDING_RESPONSE:
            return None, None

        length: int = struct.unpack("!H", response[2:4])[0]
        magic_cookie: int = struct.unpack("!I", response[4:8])[0]
        transaction_id: bytes = response[8:20]

        if magic_cookie != STUN_MAGIC_COOKIE:
            return None, None

        ip: Optional[str] = None
        port: Optional[int] = None
        pos: int = 20

        while pos < len(response):
            if pos + 4 > len(response):
                break
            attr_type, attr_length = struct.unpack("!HH", response[pos:pos+4])
            pos += 4
            if pos + attr_length > len(response):
                break
            attr_value = response[pos:pos+attr_length]
            pos += attr_length
            if pos % 4 != 0:
                pos += 4 - (pos % 4)

            if attr_type == STUN_ATTR_XOR_MAPPED_ADDRESS and attr_length >= 8:
                family: int = attr_value[1]
                xor_port: int = struct.unpack("!H", attr_value[2:4])[0]
                port = xor_port ^ (STUN_MAGIC_COOKIE >> 16)
                ip_bytes: bytes = attr_value[4:8]
                xor_ip: int = struct.unpack("!I", ip_bytes)[0] ^ STUN_MAGIC_COOKIE
                ip = socket.inet_ntoa(struct.pack("!I", xor_ip))
                break
            elif attr_type == STUN_ATTR_MAPPED_ADDRESS and attr_length >= 8:
                family = attr_value[1]
                port = struct.unpack("!H", attr_value[2:4])[0]
                if family == 0x01:
                    ip = socket.inet_ntoa(attr_value[4:8])
                break

        return ip, port

    async def discover_public_address(self, timeout: float = 5.0) -> Tuple[Optional[str], Optional[int]]:
        for server in self._servers:
            try:
                result = await self._query_server(server, timeout)
                if result and result[0]:
                    self._public_ip, self._public_port = result
                    return result
            except Exception as e:
                logger.debug(f"STUN query failed for {server}: {e}")
        return None, None

    async def _query_server(self, server: str, timeout: float) -> Tuple[Optional[str], Optional[int]]:
        host, port_str = server.split(":")
        port: int = int(port_str)

        loop = asyncio.get_event_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)

        try:
            request: bytes = self._create_binding_request()
            await loop.sock_sendto(sock, request, (host, port))
            response: bytes = await loop.sock_recv(sock, 1024)
            return self._parse_response(response)
        finally:
            sock.close()

    async def detect_nat_type(self, timeout: float = 10.0) -> str:
        if not self._public_ip:
            await self.discover_public_address(timeout)
        if not self._public_ip:
            self._nat_type = "unknown"
            return self._nat_type

        try:
            from utils.helpers import get_local_ip
            local_ip: str = get_local_ip()
            self._local_ip = local_ip

            if self._public_ip == local_ip:
                self._nat_type = "open"
            else:
                alt_mapping: Optional[Tuple[Optional[str], Optional[int]]] = None
                if len(self._servers) > 1:
                    alt_mapping = await self._query_server(self._servers[1], timeout)
                if alt_mapping and alt_mapping[0] and alt_mapping[1]:
                    if alt_mapping[0] == self._public_ip and alt_mapping[1] == self._public_port:
                        self._nat_type = "cone"
                    else:
                        self._nat_type = "symmetric"
                else:
                    self._nat_type = "moderate"
        except Exception as e:
            logger.error(f"NAT type detection failed: {e}")
            self._nat_type = "moderate"

        return self._nat_type

    async def perform_hole_punch(self, peer_host: str, peer_port: int,
                                   local_port: int = 0) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if local_port:
            sock.bind(("0.0.0.0", local_port))

        try:
            loop = asyncio.get_event_loop()
            punch_data: bytes = b"SECP2P_HOLE_PUNCH"
            for _ in range(5):
                await loop.sock_sendto(sock, punch_data, (peer_host, peer_port))
                await asyncio.sleep(0.1)
            return True
        except Exception as e:
            logger.error(f"Hole punch failed: {e}")
            return False
        finally:
            sock.close()

    def add_server(self, server: str) -> None:
        if server not in self._servers:
            self._servers.append(server)
