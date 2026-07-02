import asyncio
import hashlib
import json
import logging
import socket
import struct
import time
from typing import Callable, Dict, Optional, Tuple

from crypto.aes_engine import AESCipher
from crypto.key_exchange import KeyExchange
from crypto.hashing import Hasher
from network.bandwidth_estimator import BandwidthEstimator
from storage.database import DatabaseManager
from storage.models import Peer
from utils.constants import (
    BUFFER_SIZE, CONNECT_BACKOFF_BASE, CONNECTION_TIMEOUT, KEY_SIZE,
    MAX_CONNECT_RETRIES, MAX_RETRANSMITS, NONCE_SIZE, PROTOCOL_MAGIC,
    PROTOCOL_VERSION, RECONNECT_INTERVAL, SOCKET_TIMEOUT, TAG_SIZE,
    PEER_STATE_AUTHENTICATED, PEER_STATE_AUTHENTICATING, PEER_STATE_CONNECTED,
    PEER_STATE_CONNECTING, PEER_STATE_DISCONNECTED
)
from utils.helpers import create_id, get_local_ip

logger = logging.getLogger(__name__)

MSG_TYPE_HELLO: int = 0x01
MSG_TYPE_HELLO_ACK: int = 0x02
MSG_TYPE_KEY_EXCHANGE: int = 0x03
MSG_TYPE_KEY_EXCHANGE_ACK: int = 0x04
MSG_TYPE_DATA: int = 0x05
MSG_TYPE_DATA_ACK: int = 0x06
MSG_TYPE_PING: int = 0x07
MSG_TYPE_PONG: int = 0x08
MSG_TYPE_FILE_META: int = 0x09
MSG_TYPE_FILE_CHUNK: int = 0x0A
MSG_TYPE_FILE_ACK: int = 0x0B
MSG_TYPE_FILE_REQUEST: int = 0x0C
MSG_TYPE_FILE_RESPONSE: int = 0x0D
MSG_TYPE_DISCONNECT: int = 0x0E
MSG_TYPE_ERROR: int = 0xFF


class SecureConnection:
    """Manages a single encrypted peer connection."""

    def __init__(self, peer: Peer, reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter) -> None:
        self.peer: Peer = peer
        self.reader: asyncio.StreamReader = reader
        self.writer: asyncio.StreamWriter = writer
        self.key_exchange: KeyExchange = KeyExchange()
        self.cipher: Optional[AESCipher] = None
        self.bandwidth_estimator: BandwidthEstimator = BandwidthEstimator()
        self.connected_at: float = time.time()
        self.last_activity: float = time.time()
        self.authenticated: bool = False
        self._buffer: bytes = b""
        self._pending_hello: Optional[dict] = None

    @property
    def host(self) -> str:
        return self.peer.host

    @property
    def port(self) -> int:
        return self.peer.port

    async def send_message(self, msg_type: int, payload: bytes) -> None:
        if self.cipher and msg_type not in (MSG_TYPE_HELLO, MSG_TYPE_HELLO_ACK,
                                             MSG_TYPE_KEY_EXCHANGE, MSG_TYPE_KEY_EXCHANGE_ACK):
            payload = self.cipher.encrypt(payload)
        header: bytes = struct.pack("!4sII", PROTOCOL_MAGIC, msg_type, len(payload))
        self.writer.write(header + payload)
        await self.writer.drain()
        self.last_activity = time.time()

    async def read_message(self) -> Tuple[int, bytes]:
        header: bytes = await self.reader.readexactly(12)
        magic: bytes = header[:4]
        msg_type: int = struct.unpack("!I", header[4:8])[0]
        length: int = struct.unpack("!I", header[8:12])[0]
        if magic != PROTOCOL_MAGIC[:4]:
            logger.warning(f"Invalid protocol magic from {self.peer.display_name}")
            return MSG_TYPE_ERROR, b"invalid magic"
        payload: bytes = await self.reader.readexactly(length)
        self.last_activity = time.time()
        if self.cipher and msg_type not in (MSG_TYPE_HELLO, MSG_TYPE_HELLO_ACK,
                                             MSG_TYPE_KEY_EXCHANGE, MSG_TYPE_KEY_EXCHANGE_ACK):
            try:
                payload = self.cipher.decrypt(payload)
            except Exception as e:
                logger.error(f"Decryption failed from {self.peer.display_name}: {e}")
                return MSG_TYPE_ERROR, b"decryption failed"
        return msg_type, payload

    async def send_ping(self) -> None:
        start: float = time.time()
        await self.send_message(MSG_TYPE_PING, struct.pack("!d", start))

    async def send_pong(self, timestamp: float) -> None:
        await self.send_message(MSG_TYPE_PONG, struct.pack("!d", timestamp))

    async def send_disconnect(self, reason: str = "") -> None:
        try:
            payload: bytes = json.dumps({"reason": reason}).encode()
            await self.send_message(MSG_TYPE_DISCONNECT, payload)
        except Exception:
            pass

    async def send_error(self, message: str) -> None:
        payload: bytes = json.dumps({"error": message}).encode()
        await self.send_message(MSG_TYPE_ERROR, payload)

    async def close(self) -> None:
        try:
            if self.writer:
                self.writer.close()
                await self.writer.wait_closed()
        except Exception:
            pass

    def is_alive(self, timeout: float = 30.0) -> bool:
        return (time.time() - self.last_activity) < timeout


class ConnectionManager:
    """Manages all peer connections, encryption setup, and message routing."""

    def __init__(self, peer_id: str, display_name: str) -> None:
        self._peer_id: str = peer_id
        self._display_name: str = display_name
        self._db: DatabaseManager = DatabaseManager()
        self._server: Optional[asyncio.AbstractServer] = None
        self._connections: Dict[str, SecureConnection] = {}
        self._pending_connections: Dict[str, asyncio.Task] = {}
        self._running: bool = False
        self._message_handlers: Dict[int, Callable] = {}
        self._on_connection: Optional[Callable] = None
        self._on_disconnection: Optional[Callable] = None
        self._on_authentication: Optional[Callable] = None

    def set_connection_callback(self, callback: Optional[Callable] = None) -> None:
        self._on_connection = callback

    def set_disconnection_callback(self, callback: Optional[Callable] = None) -> None:
        self._on_disconnection = callback

    def set_authentication_callback(self, callback: Optional[Callable] = None) -> None:
        self._on_authentication = callback

    def register_handler(self, msg_type: int, handler: Callable) -> None:
        self._message_handlers[msg_type] = handler

    def unregister_handler(self, msg_type: int) -> None:
        self._message_handlers.pop(msg_type, None)

    @property
    def connections(self) -> Dict[str, SecureConnection]:
        return dict(self._connections)

    @property
    def is_running(self) -> bool:
        return self._running

    async def start_server(self, port: int = 0) -> int:
        self._running = True
        try:
            self._server = await asyncio.start_server(
                self._handle_incoming, host="0.0.0.0", port=port
            )
            actual_port: int = self._server.sockets[0].getsockname()[1]
            logger.info(f"Listening on port {actual_port}")
            asyncio.create_task(self._server_serve())
            return actual_port
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            raise

    async def _server_serve(self) -> None:
        try:
            await self._server.serve_forever()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Server error: {e}")

    async def connect_to_peer(self, peer: Peer,
                               max_retries: int = MAX_CONNECT_RETRIES) -> Optional[SecureConnection]:
        if peer.peer_id in self._connections:
            logger.debug(f"Already connected to {peer.display_name}")
            return self._connections[peer.peer_id]

        task_key: str = f"connect_{peer.peer_id}"
        if task_key in self._pending_connections:
            logger.debug(f"Already connecting to {peer.display_name}")
            return None

        async def _do_connect() -> Optional[SecureConnection]:
            last_error: Optional[str] = None
            try:
                for attempt in range(1, max_retries + 1):
                    try:
                        logger.info(f"Connecting to {peer.display_name} at "
                                    f"{peer.host}:{peer.port} "
                                    f"(attempt {attempt}/{max_retries})")
                        peer.state = PEER_STATE_CONNECTING
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(peer.host, peer.port),
                            timeout=CONNECTION_TIMEOUT
                        )
                        conn: SecureConnection = SecureConnection(peer, reader, writer)
                        self._connections[peer.peer_id] = conn
                        peer.state = PEER_STATE_CONNECTED
                        asyncio.create_task(self._handle_connection(conn))
                        logger.info(f"Connected to {peer.display_name}")
                        if self._on_connection:
                            self._on_connection(conn)
                        return conn
                    except (OSError, ConnectionError, asyncio.TimeoutError) as e:
                        last_error = str(e)
                        if attempt < max_retries:
                            backoff: float = CONNECT_BACKOFF_BASE ** (attempt - 1)
                            logger.warning(f"Connection attempt {attempt} failed: {e}, "
                                           f"retrying in {backoff:.1f}s")
                            await asyncio.sleep(backoff)
                    except Exception as e:
                        last_error = str(e)
                        break
                logger.error(f"Failed to connect to {peer.display_name} after "
                             f"{max_retries} attempts: {last_error}")
                peer.state = PEER_STATE_DISCONNECTED
                return None
            finally:
                self._pending_connections.pop(task_key, None)

        task: asyncio.Task = asyncio.create_task(_do_connect())
        self._pending_connections[task_key] = task
        return await task

    async def disconnect_from_peer(self, peer_id: str, reason: str = "") -> None:
        conn: Optional[SecureConnection] = self._connections.pop(peer_id, None)
        if conn:
            await conn.send_disconnect(reason)
            await conn.close()
            conn.peer.state = PEER_STATE_DISCONNECTED
            logger.info(f"Disconnected from {conn.peer.display_name}: {reason}")
            if self._on_disconnection:
                self._on_disconnection(conn)

    async def disconnect_all(self) -> None:
        for peer_id in list(self._connections.keys()):
            await self.disconnect_from_peer(peer_id, "server shutting down")

    def get_connection(self, peer_id: str) -> Optional[SecureConnection]:
        return self._connections.get(peer_id)

    def is_connected(self, peer_id: str) -> bool:
        return peer_id in self._connections

    async def _handle_incoming(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter) -> None:
        peername: tuple = writer.get_extra_info("peername")
        try:
            msg_type, payload = await self._read_initial_message(reader)
            if msg_type != MSG_TYPE_HELLO:
                logger.warning(f"Expected HELLO from {peername}, got {msg_type}")
                writer.close()
                return
            hello_data: dict = json.loads(payload.decode())
            peer_id: str = hello_data.get("peer_id", "")
            display_name: str = hello_data.get("display_name", "Unknown")
            public_key_hex: str = hello_data.get("public_key", "")
            if not peer_id or not public_key_hex:
                logger.warning(f"Invalid HELLO from {peername}")
                writer.close()
                return
            temp_id: str = f"incoming_{id(reader)}"
            peer = Peer(
                peer_id=temp_id,
                display_name=display_name,
                host=peername[0],
                port=hello_data.get("port", 0) or peername[1],
                state=PEER_STATE_CONNECTING
            )
            conn: SecureConnection = SecureConnection(peer, reader, writer)
            conn._pending_hello = {
                "peer_id": peer_id,
                "display_name": display_name,
                "public_key_hex": public_key_hex,
                "port": hello_data.get("port", 0) or peername[1]
            }
            self._connections[temp_id] = conn
            peer.state = PEER_STATE_CONNECTED
            logger.info(f"Incoming connection from {display_name} ({peername[0]})")
            asyncio.create_task(self._handle_connection(conn))
        except Exception as e:
            logger.error(f"Error handling incoming connection from {peername}: {e}")
            try:
                writer.close()
            except Exception:
                pass

    async def _read_initial_message(self, reader: asyncio.StreamReader) -> Tuple[int, bytes]:
        header: bytes = await reader.readexactly(12)
        msg_type: int = struct.unpack("!I", header[4:8])[0]
        length: int = struct.unpack("!I", header[8:12])[0]
        payload: bytes = await reader.readexactly(length)
        return msg_type, payload

    async def _handle_connection(self, conn: SecureConnection) -> None:
        try:
            if conn.peer.state == PEER_STATE_CONNECTED:
                await self._perform_key_exchange(conn)
            while self._running and conn.peer.peer_id in self._connections:
                try:
                    msg_type, payload = await conn.read_message()
                    conn.last_activity = time.time()
                    if msg_type == MSG_TYPE_DISCONNECT:
                        logger.info(f"{conn.peer.display_name} disconnected")
                        break
                    elif msg_type == MSG_TYPE_PING:
                        timestamp: float = struct.unpack("!d", payload)[0]
                        await conn.send_pong(timestamp)
                    elif msg_type == MSG_TYPE_PONG:
                        timestamp = struct.unpack("!d", payload)[0]
                        rtt: float = time.time() - timestamp
                        conn.bandwidth_estimator.record_rtt(rtt)
                        conn.peer.latency = rtt * 1000
                    elif msg_type == MSG_TYPE_ERROR:
                        error_data: dict = json.loads(payload.decode())
                        logger.error(f"Error from {conn.peer.display_name}: {error_data}")
                    elif msg_type in self._message_handlers:
                        await self._message_handlers[msg_type](conn, payload)
                    else:
                        logger.debug(f"Unknown message type {msg_type} from {conn.peer.display_name}")
                except (asyncio.IncompleteReadError, ConnectionError, OSError) as e:
                    logger.info(f"Connection lost to {conn.peer.display_name}: {e}")
                    break
                except Exception as e:
                    logger.error(f"Error handling message from {conn.peer.display_name}: {e}")
                    break
        except Exception as e:
            logger.error(f"Connection handler error for {conn.peer.display_name}: {e}")
        finally:
            await self._cleanup_connection(conn)

    async def _perform_key_exchange(self, conn: SecureConnection) -> None:
        try:
            conn.peer.state = PEER_STATE_AUTHENTICATING
            my_public_key: bytes = conn.key_exchange.public_bytes
            my_port: int = self._server.sockets[0].getsockname()[1] if self._server else 0

            if conn._pending_hello:
                # Server side: HELLO already consumed by _handle_incoming
                hello_data: dict = conn._pending_hello
                conn._pending_hello = None
                peer_public_key_hex: str = hello_data["public_key_hex"]
                peer_public_key: bytes = bytes.fromhex(peer_public_key_hex)
                real_peer_id: str = hello_data["peer_id"]
                old_id: str = conn.peer.peer_id
                conn.peer.peer_id = real_peer_id
                conn.peer.display_name = hello_data.get("display_name", conn.peer.display_name)
                conn.peer.port = hello_data.get("port", 0) or conn.peer.port
                if old_id in self._connections:
                    del self._connections[old_id]
                self._connections[real_peer_id] = conn
                hello_response: dict = {
                    "peer_id": self._peer_id,
                    "display_name": self._display_name,
                    "public_key": my_public_key.hex(),
                    "port": my_port
                }
                await conn.send_message(MSG_TYPE_HELLO, json.dumps(hello_response).encode())
                if self._on_connection:
                    self._on_connection(conn)
            else:
                # Client side: initiate handshake
                hello_msg: dict = {
                    "peer_id": self._peer_id,
                    "display_name": self._display_name,
                    "public_key": my_public_key.hex(),
                    "port": my_port
                }
                await conn.send_message(MSG_TYPE_HELLO, json.dumps(hello_msg).encode())
                msg_type, payload = await conn.read_message()
                if msg_type != MSG_TYPE_HELLO:
                    raise ValueError(f"Expected HELLO, got {msg_type}")
                hello_data = json.loads(payload.decode())
                peer_public_key_hex = hello_data.get("public_key", "")
                if not peer_public_key_hex:
                    raise ValueError("No public key in HELLO")
                peer_public_key = bytes.fromhex(peer_public_key_hex)
                real_peer_id: str = hello_data.get("peer_id", "")
                if real_peer_id:
                    old_id: str = conn.peer.peer_id
                    conn.peer.peer_id = real_peer_id
                    conn.peer.display_name = hello_data.get("display_name", conn.peer.display_name)
                    if old_id in self._connections and old_id != real_peer_id:
                        del self._connections[old_id]
                    self._connections[real_peer_id] = conn
                peer_port: int = hello_data.get("port", 0)
                if peer_port:
                    conn.peer.port = peer_port

            my_salt: bytes = conn.key_exchange.generate_salt()
            conn.key_exchange.compute_shared_secret(peer_public_key)
            ack_msg: dict = {
                "salt": my_salt.hex(),
                "status": "ok"
            }
            await conn.send_message(MSG_TYPE_KEY_EXCHANGE, json.dumps(ack_msg).encode())
            msg_type, payload = await conn.read_message()
            if msg_type != MSG_TYPE_KEY_EXCHANGE:
                raise ValueError(f"Expected KEY_EXCHANGE, got {msg_type}")
            exchange_data: dict = json.loads(payload.decode())
            peer_salt_hex: str = exchange_data.get("salt", "")
            if not peer_salt_hex:
                raise ValueError("No salt in KEY_EXCHANGE")
            peer_salt: bytes = bytes.fromhex(peer_salt_hex)
            combined: bytes = b"".join(sorted([my_salt, peer_salt]))
            common_salt: bytes = hashlib.sha256(combined).digest()
            session_key: bytes = conn.key_exchange.derive_session_key(common_salt)
            conn.cipher = AESCipher(session_key)
            conn.authenticated = True
            conn.peer.session_key = session_key
            conn.peer.state = PEER_STATE_AUTHENTICATED
            self._db.save_peer(conn.peer)
            logger.info(f"Key exchange complete with {conn.peer.display_name}")
            if self._on_authentication:
                self._on_authentication(conn)
        except Exception as e:
            logger.error(f"Key exchange failed with {conn.peer.display_name}: {e}")
            raise

    async def _cleanup_connection(self, conn: SecureConnection) -> None:
        peer_id: str = conn.peer.peer_id
        if peer_id in self._connections:
            del self._connections[peer_id]
        conn.peer.state = PEER_STATE_DISCONNECTED
        try:
            await conn.close()
        except Exception:
            pass
        logger.info(f"Cleaned up connection to {conn.peer.display_name}")
        if self._on_disconnection:
            self._on_disconnection(conn)

    async def send_to_peer(self, peer_id: str, msg_type: int, payload: bytes) -> bool:
        conn: Optional[SecureConnection] = self.get_connection(peer_id)
        if not conn:
            logger.warning(f"No connection to peer {peer_id}")
            return False
        try:
            await conn.send_message(msg_type, payload)
            return True
        except Exception as e:
            logger.error(f"Failed to send to {peer_id}: {e}")
            return False

    async def broadcast(self, msg_type: int, payload: bytes) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
        for peer_id, conn in list(self._connections.items()):
            if conn.authenticated:
                results[peer_id] = await self.send_to_peer(peer_id, msg_type, payload)
        return results

    async def health_check(self) -> None:
        while self._running:
            await asyncio.sleep(15.0)
            for peer_id, conn in list(self._connections.items()):
                try:
                    if conn.authenticated:
                        await conn.send_ping()
                    if not conn.is_alive():
                        logger.info(f"Peer {conn.peer.display_name} timed out")
                        await self.disconnect_from_peer(peer_id, "timeout")
                except (ConnectionError, OSError) as e:
                    logger.debug(f"Health check ping failed for {peer_id}: {e}")

    async def stop(self) -> None:
        self._running = False
        await self.disconnect_all()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        logger.info("Connection manager stopped")
