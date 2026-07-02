import asyncio
import json
import logging
import socket
import struct
import time
from typing import Callable, Dict, List, Optional, Set

from zeroconf import Zeroconf, ServiceInfo, ServiceListener

from storage.database import DatabaseManager
from storage.models import Peer
from utils.constants import PEER_DISCOVERY_PORT, PEER_DISCOVERY_INTERVAL
from utils.helpers import create_id, get_local_ip

HOSTNAME: str = socket.gethostname()

logger = logging.getLogger(__name__)

MULTICAST_GROUP: str = "224.0.0.251"
MULTICAST_PORT: int = PEER_DISCOVERY_PORT
SERVICE_TYPE: str = "_securep2p._tcp.local."


class PeerDiscovery:
    """LAN and mDNS peer discovery with multicast support."""

    def __init__(self, peer_id: str, display_name: str) -> None:
        self._peer_id: str = peer_id
        self._display_name: str = display_name
        self._port: int = 0
        self._db: DatabaseManager = DatabaseManager()
        self._zeroconf: Optional[Zeroconf] = None
        self._service_info: Optional[ServiceInfo] = None
        self._running: bool = False
        self._discovered_peers: Dict[str, Peer] = {}
        self._known_peers: Set[str] = set()
        self._on_peer_found: Optional[Callable] = None
        self._on_peer_lost: Optional[Callable] = None

    @property
    def discovered_peers(self) -> Dict[str, Peer]:
        return dict(self._discovered_peers)

    def set_callbacks(self, on_peer_found: Optional[Callable] = None,
                       on_peer_lost: Optional[Callable] = None) -> None:
        self._on_peer_found = on_peer_found
        self._on_peer_lost = on_peer_lost

    async def start(self, port: int) -> None:
        self._port = port
        self._running = True
        try:
            self._start_zeroconf()
        except Exception as e:
            logger.warning(f"mDNS init failed, using multicast only: {e}")
        asyncio.create_task(self._multicast_listener())
        asyncio.create_task(self._broadcast_loop())

    def _start_zeroconf(self) -> None:
        self._zeroconf = Zeroconf()
        local_ip: str = get_local_ip()
        self._service_info = ServiceInfo(
            SERVICE_TYPE,
            f"{self._peer_id}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(local_ip)],
            port=self._port,
            properties={
                "peer_id": self._peer_id,
                "display_name": self._display_name,
                "hostname": HOSTNAME,
                "version": "1.0.0"
            }
        )
        self._zeroconf.register_service(self._service_info)

        class P2PServiceListener(ServiceListener):
            def __init__(self, outer: "PeerDiscovery") -> None:
                self.outer = outer

            def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                self.outer._handle_service_added(zc, type_, name)

            def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                self.outer._handle_service_removed(zc, type_, name)

            def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                pass

        self._zeroconf.add_service_listener(SERVICE_TYPE, P2PServiceListener(self))

    def _handle_service_added(self, zc: Zeroconf, type_: str, name: str) -> None:
        try:
            info: Optional[ServiceInfo] = zc.get_service_info(type_, name)
            if info is None:
                return
            peer_id: str = info.properties.get(b"peer_id", b"").decode()
            if peer_id == self._peer_id or peer_id in self._known_peers:
                return
            display_name: str = info.properties.get(b"display_name", b"").decode()
            hostname: str = info.properties.get(b"hostname", b"").decode()
            host: str = socket.inet_ntoa(info.addresses[0]) if info.addresses else ""
            port: int = info.port
            label: str = f"{hostname} [{peer_id[:8]}]" if hostname else (display_name or peer_id)
            peer = Peer(
                peer_id=peer_id,
                display_name=label,
                host=host,
                port=port,
                state="disconnected",
                connection_type="lan",
                last_seen=time.time(),
                metadata={"hostname": hostname, "raw_display": display_name}
            )
            self._discovered_peers[peer_id] = peer
            self._known_peers.add(peer_id)
            self._db.save_peer(peer)
            logger.info(f"Discovered peer via mDNS: {label} ({host}:{port})")
            if self._on_peer_found:
                self._on_peer_found(peer)
        except Exception as e:
            logger.debug(f"Error handling mDNS add: {e}")

    def _handle_service_removed(self, zc: Zeroconf, type_: str, name: str) -> None:
        try:
            peer_id: str = name.split(".")[0]
            if peer_id in self._discovered_peers:
                peer: Peer = self._discovered_peers.pop(peer_id)
                logger.info(f"Peer left: {peer.display_name}")
                if self._on_peer_lost:
                    self._on_peer_lost(peer)
        except Exception as e:
            logger.debug(f"Error handling mDNS remove: {e}")

    async def _multicast_listener(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", MULTICAST_PORT))
        except OSError:
            sock.bind(("0.0.0.0", 0))
        mreq: bytes = struct.pack("4sl", socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(1.0)

        loop = asyncio.get_event_loop()
        while self._running:
            try:
                data, addr = await loop.sock_recvfrom(sock, 1024)
                self._handle_multicast_message(data, addr)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if self._running:
                    logger.debug(f"Multicast receive error: {e}")
                    await asyncio.sleep(1)
        sock.close()

    def _handle_multicast_message(self, data: bytes, addr: tuple) -> None:
        try:
            msg: dict = json.loads(data.decode())
            peer_id: str = msg.get("peer_id", "")
            if peer_id == self._peer_id:
                return
            display_name: str = msg.get("display_name", peer_id)
            hostname: str = msg.get("hostname", "")
            host: str = msg.get("host", addr[0])
            port: int = msg.get("port", 0)
            label: str = f"{hostname} [{peer_id[:8]}]" if hostname else display_name
            if peer_id not in self._discovered_peers:
                peer = Peer(
                    peer_id=peer_id,
                    display_name=label,
                    host=host,
                    port=port,
                    state="disconnected",
                    connection_type="lan",
                    last_seen=time.time(),
                    metadata={"hostname": hostname, "raw_display": display_name}
                )
                self._discovered_peers[peer_id] = peer
                self._known_peers.add(peer_id)
                self._db.save_peer(peer)
                logger.info(f"Discovered peer via multicast: {label} ({host}:{port})")
                if self._on_peer_found:
                    self._on_peer_found(peer)
            else:
                self._discovered_peers[peer_id].last_seen = time.time()
        except Exception as e:
            logger.debug(f"Error parsing multicast message: {e}")

    async def _broadcast_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        loop = asyncio.get_event_loop()

        while self._running:
            try:
                msg: dict = {
                    "peer_id": self._peer_id,
                    "display_name": self._display_name,
                    "hostname": HOSTNAME,
                    "host": get_local_ip(),
                    "port": self._port
                }
                data: bytes = json.dumps(msg).encode()
                await loop.sock_sendto(sock, data, (MULTICAST_GROUP, MULTICAST_PORT))
                await asyncio.sleep(PEER_DISCOVERY_INTERVAL)
            except Exception as e:
                logger.debug(f"Broadcast error: {e}")
                await asyncio.sleep(PEER_DISCOVERY_INTERVAL)
        sock.close()

    def add_manual_peer(self, host: str, port: int,
                         display_name: str = "") -> Optional[Peer]:
        peer_id: str = create_id()
        peer = Peer(
            peer_id=peer_id,
            display_name=display_name or f"Peer@{host}:{port}",
            host=host,
            port=port,
            state="disconnected",
            connection_type="manual",
            last_seen=time.time()
        )
        self._discovered_peers[peer_id] = peer
        self._known_peers.add(peer_id)
        self._db.save_peer(peer)
        logger.info(f"Added manual peer: {host}:{port}")
        if self._on_peer_found:
            self._on_peer_found(peer)
        return peer

    def get_peer(self, peer_id: str) -> Optional[Peer]:
        return self._discovered_peers.get(peer_id)

    def remove_peer(self, peer_id: str) -> None:
        if peer_id in self._discovered_peers:
            peer: Peer = self._discovered_peers.pop(peer_id)
            self._known_peers.discard(peer_id)
            if self._on_peer_lost:
                self._on_peer_lost(peer)

    async def stop(self) -> None:
        self._running = False
        if self._zeroconf:
            try:
                if self._service_info:
                    self._zeroconf.unregister_service(self._service_info)
                self._zeroconf.close()
            except Exception as e:
                logger.debug(f"Error stopping Zeroconf: {e}")
        logger.info("Peer discovery stopped")
