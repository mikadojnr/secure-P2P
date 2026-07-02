import asyncio
import logging
import socket
import struct
import time
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

TURN_MAGIC_COOKIE: int = 0x2112A442
TURN_ALLOCATE_REQUEST: int = 0x0003
TURN_ALLOCATE_RESPONSE: int = 0x0103
TURN_SEND_INDICATION: int = 0x0016
TURN_DATA_INDICATION: int = 0x0017
TURN_CREATE_PERMISSION: int = 0x0008
TURN_ATTR_LIFETIME: int = 0x000d
TURN_ATTR_XOR_RELAYED_ADDRESS: int = 0x0016
TURN_ATTR_XOR_PEER_ADDRESS: int = 0x0012
TURN_ATTR_DATA: int = 0x0013


class TURNClient:
    """TURN relay client as fallback for NAT traversal."""

    def __init__(self, server: str = "", username: str = "",
                 password: str = "") -> None:
        self._server: str = server
        self._username: str = username
        self._password: str = password
        self._relay_ip: Optional[str] = None
        self._relay_port: Optional[int] = None
        self._allocation_lifetime: int = 300
        self._sock: Optional[socket.socket] = None
        self._connected: bool = False
        self._data_callback: Optional[Callable] = None

    @property
    def relay_ip(self) -> Optional[str]:
        return self._relay_ip

    @property
    def relay_port(self) -> Optional[int]:
        return self._relay_port

    @property
    def connected(self) -> bool:
        return self._connected

    def set_data_callback(self, callback: Callable) -> None:
        self._data_callback = callback

    async def allocate_relay(self, timeout: float = 10.0) -> bool:
        if not self._server:
            logger.warning("No TURN server configured")
            return False

        try:
            host, port_str = self._server.split(":")
            port: int = int(port_str)

            loop = asyncio.get_event_loop()
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.settimeout(timeout)

            request: bytes = self._build_allocate_request()
            await loop.sock_sendto(self._sock, request, (host, port))
            response: bytes = await loop.sock_recv(self._sock, 2048)

            if self._parse_allocate_response(response):
                self._connected = True
                logger.info(f"TURN relay allocated: {self._relay_ip}:{self._relay_port}")
                return True

        except Exception as e:
            logger.error(f"TURN allocation failed: {e}")

        return False

    def _build_allocate_request(self) -> bytes:
        transaction_id: bytes = bytes(range(12))
        header: bytes = struct.pack("!HHI", TURN_ALLOCATE_REQUEST, 0, TURN_MAGIC_COOKIE)
        header += transaction_id

        lifetime_attr: bytes = struct.pack("!HH", TURN_ATTR_LIFETIME, 4)
        lifetime_attr += struct.pack("!I", self._allocation_lifetime)

        total_length: int = len(lifetime_attr)
        header = header[:2] + struct.pack("!H", total_length) + header[4:]

        return header + lifetime_attr

    def _parse_allocate_response(self, response: bytes) -> bool:
        if len(response) < 20:
            return False

        msg_type: int = struct.unpack("!H", response[:2])[0]
        if msg_type != TURN_ALLOCATE_RESPONSE:
            return False

        length: int = struct.unpack("!H", response[2:4])[0]
        magic: int = struct.unpack("!I", response[4:8])[0]

        if magic != TURN_MAGIC_COOKIE:
            return False

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

            if attr_type == TURN_ATTR_XOR_RELAYED_ADDRESS and attr_length >= 8:
                family: int = attr_value[1]
                xor_port: int = struct.unpack("!H", attr_value[2:4])[0]
                self._relay_port = xor_port ^ (TURN_MAGIC_COOKIE >> 16)
                if family == 0x01 and attr_length >= 8:
                    ip_bytes: bytes = attr_value[4:8]
                    xor_ip: int = struct.unpack("!I", ip_bytes)[0] ^ TURN_MAGIC_COOKIE
                    self._relay_ip = socket.inet_ntoa(struct.pack("!I", xor_ip))
                return True

        return False

    async def create_permission(self, peer_ip: str, peer_port: int) -> bool:
        if not self._connected or not self._sock:
            logger.warning("TURN not connected")
            return False

        try:
            loop = asyncio.get_event_loop()
            peer_addr_bytes: bytes = socket.inet_aton(peer_ip)
            xor_peer: int = struct.unpack("!I", peer_addr_bytes)[0] ^ TURN_MAGIC_COOKIE
            xor_port: int = peer_port ^ (TURN_MAGIC_COOKIE >> 16)

            attr_value: bytes = bytes([0, 0x01]) + struct.pack("!H", xor_port) + struct.pack("!I", xor_peer)
            attr: bytes = struct.pack("!HH", TURN_ATTR_XOR_PEER_ADDRESS, len(attr_value)) + attr_value

            header: bytes = struct.pack("!HHI", TURN_CREATE_PERMISSION, len(attr), TURN_MAGIC_COOKIE)
            header += bytes(range(12))

            await loop.sock_sendto(self._sock, header + attr, (self._server.split(":")[0], int(self._server.split(":")[1])))
            return True
        except Exception as e:
            logger.error(f"TURN create permission failed: {e}")
            return False

    async def send_data(self, peer_ip: str, peer_port: int, data: bytes) -> bool:
        if not self._connected or not self._sock:
            return False

        try:
            loop = asyncio.get_event_loop()
            peer_addr_bytes: bytes = socket.inet_aton(peer_ip)
            xor_peer: int = struct.unpack("!I", peer_addr_bytes)[0] ^ TURN_MAGIC_COOKIE
            xor_port: int = peer_port ^ (TURN_MAGIC_COOKIE >> 16)

            peer_attr: bytes = struct.pack("!HH", TURN_ATTR_XOR_PEER_ADDRESS, 8)
            peer_attr += bytes([0, 0x01]) + struct.pack("!H", xor_port) + struct.pack("!I", xor_peer)

            data_attr: bytes = struct.pack("!HH", TURN_ATTR_DATA, len(data))
            data_attr += data

            total_attrs: bytes = peer_attr + data_attr
            header: bytes = struct.pack("!HHI", TURN_SEND_INDICATION, len(total_attrs), TURN_MAGIC_COOKIE)
            header += bytes(range(12))

            server_host, server_port_str = self._server.split(":")
            await loop.sock_sendto(self._sock, header + total_attrs, (server_host, int(server_port_str)))
            return True
        except Exception as e:
            logger.error(f"TURN send failed: {e}")
            return False

    async def receive_loop(self) -> None:
        while self._connected and self._sock:
            try:
                loop = asyncio.get_event_loop()
                data: bytes = await loop.sock_recv(self._sock, 4096)
                if data and self._data_callback:
                    self._data_callback(data)
            except Exception as e:
                if self._connected:
                    logger.error(f"TURN receive error: {e}")
                break

    def disconnect(self) -> None:
        self._connected = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        logger.info("TURN disconnected")
