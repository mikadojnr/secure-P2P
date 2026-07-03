import asyncio
import logging
import os
import socket
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QMainWindow, QMenu, QMenuBar, QMessageBox, QPushButton,
    QSplitter, QStatusBar, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget
)

from gui.settings import SettingsDialog
from gui.transfer_window import TransferDetailDialog
from gui.widgets import (
    BandwidthGraph, FileDropWidget, LogViewer,
    PeerListWidget, StatusIndicator, TransferListWidget
)
from network.connection_manager import ConnectionManager, SecureConnection
from network.peer_discovery import PeerDiscovery
from network.transfer_controller import TransferController
from storage.database import DatabaseManager
from storage.logger import AppLogger
from storage.models import Peer, Transfer, TransferHistory
from utils.config import ConfigManager
from utils.constants import (
    APP_NAME, APP_VERSION, PEER_STATE_AUTHENTICATED, PEER_STATE_DISCONNECTED,
    TRANSFER_DIRECTION_SEND, TRANSFER_STATE_IN_PROGRESS
)
from utils.firewall import configure_firewall
from utils.helpers import (
    create_id, format_bytes, format_duration, format_speed
)

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window with thread-safe cross-thread signaling."""

    peer_found_signal = pyqtSignal(object)
    peer_lost_signal = pyqtSignal(str)
    peer_connected_signal = pyqtSignal(str, str, str)
    peer_disconnected_signal = pyqtSignal(str, str)
    peer_authenticated_signal = pyqtSignal(str, str)
    transfer_update_signal = pyqtSignal(str, str, str, float, int, int, float, str)
    transfer_complete_signal = pyqtSignal(str, str, str)
    incoming_transfer_signal = pyqtSignal(str, str, str, int, str)
    log_signal = pyqtSignal(str, str)
    firewall_warning_signal = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._config: ConfigManager = ConfigManager()
        self._db: DatabaseManager = DatabaseManager()
        self._app_logger: AppLogger = AppLogger()
        self._peer_id: str = create_id()
        self._hostname: str = socket.gethostname()
        self._display_name: str = f"{self._hostname} [{self._peer_id[:8]}]"
        self._peer_discovery: PeerDiscovery = PeerDiscovery(self._peer_id, self._display_name)
        self._connection_manager: ConnectionManager = ConnectionManager(
            self._peer_id, self._display_name
        )
        self._transfer_controller: TransferController = TransferController(
            self._connection_manager, self._peer_id, self._display_name
        )
        self._asyncio_loop: Optional[asyncio.AbstractEventLoop] = None
        self._running: bool = False
        self._server_port: int = 0
        self._pending_incoming: Dict[str, Transfer] = {}

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1024, 700)
        self._setup_ui()
        self._setup_menus()
        self._setup_timers()
        self._apply_theme()
        self._connect_signals()
        self._restore_geometry()

    def _setup_ui(self) -> None:
        central: QWidget = QWidget()
        self.setCentralWidget(central)
        main_layout: QVBoxLayout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)

        splitter: QSplitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel: QWidget = QWidget()
        left_layout: QVBoxLayout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self._peer_list: PeerListWidget = PeerListWidget()
        left_layout.addWidget(self._peer_list)
        self._file_drop: FileDropWidget = FileDropWidget()
        left_layout.addWidget(self._file_drop)
        splitter.addWidget(left_panel)

        right_panel: QWidget = QWidget()
        right_layout: QVBoxLayout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        tabs: QTabWidget = QTabWidget()

        transfers_tab = QWidget()
        transfers_layout = QVBoxLayout(transfers_tab)
        transfers_layout.setContentsMargins(0, 0, 0, 0)
        self._transfer_list: TransferListWidget = TransferListWidget()
        transfers_layout.addWidget(self._transfer_list)
        tabs.addTab(transfers_tab, "Transfers")

        stats_tab = QWidget()
        stats_layout = QVBoxLayout(stats_tab)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        self._bandwidth_graph: BandwidthGraph = BandwidthGraph()
        stats_layout.addWidget(self._bandwidth_graph)
        stats_info = QLabel("Bandwidth Usage (last 60 seconds)")
        stats_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stats_info.setStyleSheet("color: #888;")
        stats_layout.addWidget(stats_info)
        tabs.addTab(stats_tab, "Bandwidth")

        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_table = QTableWidget()
        self._history_table.setColumnCount(7)
        self._history_table.setHorizontalHeaderLabels(
            ["File", "Peer", "Size", "Direction", "Date", "Duration", "State"]
        )
        self._history_table.setAlternatingRowColors(True)
        self._history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._history_table.verticalHeader().setVisible(False)
        self._history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self._history_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        history_layout.addWidget(self._history_table)
        tabs.addTab(history_tab, "History")

        logs_tab = QWidget()
        logs_layout = QVBoxLayout(logs_tab)
        logs_layout.setContentsMargins(0, 0, 0, 0)
        self._log_viewer: LogViewer = LogViewer()
        logs_layout.addWidget(self._log_viewer)
        tabs.addTab(logs_tab, "Logs")

        right_layout.addWidget(tabs)
        splitter.addWidget(right_panel)
        splitter.setSizes([350, 674])
        main_layout.addWidget(splitter)

        self._status_indicator: StatusIndicator = StatusIndicator()
        status_bar: QStatusBar = self.statusBar()
        status_bar.addPermanentWidget(self._status_indicator)
        self._status_label: QLabel = QLabel("Ready")
        status_bar.addWidget(self._status_label, 1)
        self._peer_count_label: QLabel = QLabel("Peers: 0")
        status_bar.addPermanentWidget(self._peer_count_label)
        self._transfer_count_label: QLabel = QLabel("Transfers: 0")
        status_bar.addPermanentWidget(self._transfer_count_label)

    def _setup_menus(self) -> None:
        menubar: QMenuBar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        send_action = QAction("Send File...", self)
        send_action.setShortcut(QKeySequence("Ctrl+O"))
        send_action.triggered.connect(self._browse_and_send)
        file_menu.addAction(send_action)
        file_menu.addSeparator()
        settings_action = QAction("Settings...", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._show_settings)
        file_menu.addAction(settings_action)
        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        network_menu = menubar.addMenu("&Network")
        connect_action = QAction("Connect to Peer...", self)
        connect_action.setShortcut(QKeySequence("Ctrl+D"))
        connect_action.triggered.connect(self._manual_connect)
        network_menu.addAction(connect_action)
        disconnect_all_action = QAction("Disconnect All", self)
        disconnect_all_action.triggered.connect(self._disconnect_all)
        network_menu.addAction(disconnect_all_action)
        network_menu.addSeparator()
        refresh_action = QAction("Refresh Discovery", self)
        refresh_action.setShortcut(QKeySequence("F5"))
        refresh_action.triggered.connect(self._refresh_discovery)
        network_menu.addAction(refresh_action)

        help_menu = menubar.addMenu("&Help")
        about_action = QAction(f"About {APP_NAME}", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_timers(self) -> None:
        self._ui_timer: QTimer = QTimer(self)
        self._ui_timer.timeout.connect(self._update_ui)
        self._ui_timer.start(1000)
        self._bandwidth_timer: QTimer = QTimer(self)
        self._bandwidth_timer.timeout.connect(self._update_bandwidth_graph)
        self._bandwidth_timer.start(2000)

    def _connect_signals(self) -> None:
        self._peer_list.connect_requested.connect(self._on_connect_request)
        self._peer_list.disconnect_requested.connect(self._on_disconnect_request)
        self._transfer_list.pause_requested.connect(self._on_pause_request)
        self._transfer_list.resume_requested.connect(self._on_resume_request)
        self._transfer_list.cancel_requested.connect(self._on_cancel_request)
        self._transfer_list.transfer_selected.connect(self._on_transfer_selected)
        self._file_drop.files_dropped.connect(self._on_files_dropped)

        self.peer_found_signal.connect(self._on_peer_found_gui)
        self.peer_lost_signal.connect(self._on_peer_lost_gui)
        self.peer_connected_signal.connect(self._on_peer_connected_gui)
        self.peer_disconnected_signal.connect(self._on_peer_disconnected_gui)
        self.peer_authenticated_signal.connect(self._on_peer_authenticated_gui)
        self.transfer_update_signal.connect(self._on_transfer_update_gui)
        self.transfer_complete_signal.connect(self._on_transfer_complete_gui)
        self.incoming_transfer_signal.connect(self._on_incoming_transfer_gui)
        self.log_signal.connect(self._on_log_gui)
        self.firewall_warning_signal.connect(self._on_firewall_warning_gui)

        self._peer_discovery.set_callbacks(
            on_peer_found=self._on_peer_found,
            on_peer_lost=self._on_peer_lost
        )
        self._connection_manager.set_connection_callback(self._on_peer_connected)
        self._connection_manager.set_disconnection_callback(self._on_peer_disconnected)
        self._connection_manager.set_authentication_callback(self._on_peer_authenticated)
        self._transfer_controller.set_update_callback(self._on_transfer_update)
        self._transfer_controller.set_complete_callback(self._on_transfer_complete)
        self._transfer_controller.set_incoming_callback(self._on_incoming_transfer)

    def _schedule_async(self, coro) -> None:
        if self._asyncio_loop and self._asyncio_loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self._asyncio_loop)

    def _apply_theme(self) -> None:
        if self._config.dark_mode:
            self.setStyleSheet("""
                QMainWindow, QWidget { background-color: #0d0d1a; color: #cccccc; }
                QMenuBar { background-color: #1a1a2e; color: #cccccc; border-bottom: 1px solid #2a2a3e; }
                QMenuBar::item:selected { background-color: #2a2a4e; }
                QMenu { background-color: #1a1a2e; color: #cccccc; border: 1px solid #2a2a3e; }
                QMenu::item:selected { background-color: #2a2a4e; }
                QTabWidget::pane { border: 1px solid #2a2a3e; background-color: #0d0d1a; }
                QTabBar::tab { background-color: #1a1a2e; color: #888; padding: 6px 16px; border: 1px solid #2a2a3e; border-bottom: none; border-radius: 4px 4px 0 0; }
                QTabBar::tab:selected { background-color: #0d0d1a; color: #00ff88; }
                QTableWidget { background-color: #0d0d1a; color: #ccc; gridline-color: #1a1a2e; border: 1px solid #2a2a3e; }
                QTableWidget::item:selected { background-color: #2a2a4e; }
                QHeaderView::section { background-color: #1a1a2e; color: #ccc; padding: 4px; border: 1px solid #2a2a3e; }
                QTreeWidget { background-color: #0d0d1a; color: #ccc; border: 1px solid #2a2a3e; }
                QTreeWidget::item:selected { background-color: #2a2a4e; }
                QPushButton { background-color: #2a2a4e; color: #ccc; border: 1px solid #3a3a5e; padding: 6px 16px; border-radius: 4px; }
                QPushButton:hover { background-color: #3a3a5e; }
                QPushButton:pressed { background-color: #4a4a6e; }
                QPushButton:disabled { background-color: #1a1a2e; color: #555; }
                QProgressBar { border: 1px solid #2a2a3e; border-radius: 4px; background-color: #1a1a2e; text-align: center; color: #ccc; }
                QProgressBar::chunk { background-color: #00ff88; border-radius: 3px; }
                QSplitter::handle { background-color: #2a2a3e; width: 2px; }
                QScrollBar:vertical { background: #0d0d1a; width: 10px; }
                QScrollBar::handle:vertical { background: #2a2a3e; border-radius: 5px; min-height: 20px; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
                QScrollBar:horizontal { background: #0d0d1a; height: 10px; }
                QScrollBar::handle:horizontal { background: #2a2a3e; border-radius: 5px; min-width: 20px; }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
                QTextEdit { background-color: #0d0d1a; color: #ccc; border: 1px solid #2a2a3e; }
                QLabel { color: #ccc; }
                QCheckBox { color: #ccc; }
                QComboBox { background: #1a1a2e; color: #ccc; border: 1px solid #2a2a3e; padding: 4px; border-radius: 4px; }
                QComboBox::item:selected { background: #2a2a4e; }
                QSpinBox { background: #1a1a2e; color: #ccc; border: 1px solid #2a2a3e; padding: 4px; border-radius: 4px; }
                QLineEdit { background: #1a1a2e; color: #ccc; border: 1px solid #2a2a3e; padding: 4px; border-radius: 4px; }
                QStatusBar { background-color: #1a1a2e; color: #888; border-top: 1px solid #2a2a3e; }
                QDialog { background-color: #0d0d1a; color: #ccc; }
            """)
        else:
            self.setStyleSheet("")

    def _restore_geometry(self) -> None:
        geometry = self._config.get("window_geometry")
        if geometry and len(geometry) == 4:
            self.setGeometry(*geometry)

    def _save_geometry(self) -> None:
        geo = self.geometry()
        self._config.set("window_geometry", [geo.x(), geo.y(), geo.width(), geo.height()])

    def closeEvent(self, event: Any) -> None:
        self._running = False
        self._save_geometry()
        if self._asyncio_loop:
            asyncio.run_coroutine_threadsafe(self._cleanup(), self._asyncio_loop)
        event.accept()

    async def _cleanup(self) -> None:
        await self._transfer_controller.stop()
        await self._peer_discovery.stop()
        await self._connection_manager.stop()
        self._db.close()

    async def start(self) -> None:
        self._running = True
        self._server_port = await self._connection_manager.start_server()
        fw_ok, fw_msg = configure_firewall(self._server_port)
        if fw_ok:
            self.log_signal.emit("INFO", f"Firewall rules configured for port {self._server_port}")
        else:
            self.log_signal.emit("WARNING",
                f"Firewall rules not added (run as Admin to enable): {fw_msg}")
            if sys.platform == "win32":
                self.firewall_warning_signal.emit(
                    f"Incoming connections may be blocked by Windows Defender Firewall.\n\n"
                    f"Please restart the application as Administrator to allow SecureP2P "
                    f"through the firewall.\n\nDetails: {fw_msg}")
        await self._peer_discovery.start(self._server_port)
        await self._transfer_controller.start()
        asyncio.create_task(self._connection_manager.health_check())
        self.log_signal.emit("INFO",
            f"Listening on port {self._server_port}, Peer ID: {self._peer_id[:8]}...")
        self._load_history()

    def _load_history(self) -> None:
        try:
            history = self._db.get_history(100)
            self._history_table.setRowCount(0)
            for entry in history:
                row = self._history_table.rowCount()
                self._history_table.insertRow(row)
                self._history_table.setItem(row, 0, QTableWidgetItem(entry.file_name))
                self._history_table.setItem(row, 1, QTableWidgetItem(entry.peer_name))
                self._history_table.setItem(row, 2, QTableWidgetItem(format_bytes(entry.file_size)))
                direction_str = "Send" if entry.direction == TRANSFER_DIRECTION_SEND else "Receive"
                self._history_table.setItem(row, 3, QTableWidgetItem(direction_str))
                date_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(entry.completed_at))
                self._history_table.setItem(row, 4, QTableWidgetItem(date_str))
                self._history_table.setItem(row, 5, QTableWidgetItem(format_duration(entry.duration)))
                self._history_table.setItem(row, 6, QTableWidgetItem(entry.state.replace("_", " ").title()))
        except Exception as e:
            logger.error(f"Failed to load history: {e}")

    # --- Callbacks from asyncio thread (emit signals) ---

    def _on_peer_found(self, peer: Peer) -> None:
        self.peer_found_signal.emit(peer)

    def _on_peer_lost(self, peer: Peer) -> None:
        self.peer_lost_signal.emit(peer.peer_id)

    def _on_peer_connected(self, conn: SecureConnection) -> None:
        self.peer_connected_signal.emit(
            conn.peer.peer_id, conn.peer.display_name, conn.peer.state
        )

    def _on_peer_disconnected(self, conn: SecureConnection) -> None:
        self.peer_disconnected_signal.emit(
            conn.peer.peer_id, conn.peer.display_name
        )

    def _on_peer_authenticated(self, conn: SecureConnection) -> None:
        self.peer_authenticated_signal.emit(
            conn.peer.peer_id, conn.peer.display_name
        )

    def _on_transfer_update(self, transfer: Transfer) -> None:
        self.transfer_update_signal.emit(
            transfer.transfer_id, transfer.file_name, transfer.peer_name,
            transfer.progress, transfer.bytes_transferred, transfer.bytes_total,
            transfer.speed, transfer.state
        )

    def _on_transfer_complete(self, transfer: Transfer) -> None:
        self.transfer_complete_signal.emit(
            transfer.transfer_id, transfer.file_name, transfer.peer_name
        )

    def _on_incoming_transfer(self, transfer: Transfer) -> None:
        self._pending_incoming[transfer.transfer_id] = transfer
        self.incoming_transfer_signal.emit(
            transfer.transfer_id, transfer.file_name, transfer.peer_name,
            transfer.file_size, transfer.file_hash
        )

    # --- GUI thread slots (connected to signals) ---

    def _on_peer_found_gui(self, peer: Peer) -> None:
        self._peer_list.add_peer(peer)
        self._peer_count_label.setText(f"Peers: {len(self._peer_list._peers)}")
        self._log_viewer.append_log("INFO", f"Discovered peer: {peer.display_name}")

    def _on_peer_lost_gui(self, peer_id: str) -> None:
        self._peer_list.remove_peer(peer_id)
        self._peer_count_label.setText(f"Peers: {len(self._peer_list._peers)}")
        self._log_viewer.append_log("INFO", f"Peer lost")

    def _on_peer_connected_gui(self, peer_id: str, name: str, state: str) -> None:
        self._status_indicator.set_connection(state)
        self._status_label.setText(f"Connected to {name}")
        self._log_viewer.append_log("INFO", f"Connected to {name}")
        peer = self._peer_list._peers.get(peer_id)
        if peer:
            peer.state = state
            self._peer_list.update_peer(peer)

    def _on_peer_disconnected_gui(self, peer_id: str, name: str) -> None:
        self._status_indicator.set_connection(PEER_STATE_DISCONNECTED)
        self._status_label.setText(f"Disconnected from {name}")
        self._log_viewer.append_log("INFO", f"Disconnected from {name}")
        peer = self._peer_list._peers.get(peer_id)
        if peer:
            peer.state = PEER_STATE_DISCONNECTED
            self._peer_list.update_peer(peer)

    def _on_peer_authenticated_gui(self, peer_id: str, name: str) -> None:
        self._status_indicator.set_connection(PEER_STATE_AUTHENTICATED)
        self._status_indicator.set_encryption(True)
        self._status_label.setText(f"Secure: {name}")
        self._log_viewer.append_log("INFO", f"Encrypted session with {name}")
        peer = self._peer_list._peers.get(peer_id)
        if peer:
            peer.state = PEER_STATE_AUTHENTICATED
            self._peer_list.update_peer(peer)

    def _on_transfer_update_gui(self, transfer_id: str, file_name: str,
                                 peer_name: str, progress: float,
                                 bytes_xfer: int, bytes_total: int,
                                 speed: float, state: str) -> None:
        transfers = self._transfer_controller.get_all_active_transfers()
        transfer = transfers.get(transfer_id)
        if not transfer:
            return
        self._transfer_list.add_or_update_transfer(transfer)
        active = len(transfers)
        self._transfer_count_label.setText(f"Transfers: {active}")

    def _on_transfer_complete_gui(self, transfer_id: str, file_name: str,
                                   peer_name: str) -> None:
        self._log_viewer.append_log("INFO",
            f"Transfer done: {file_name} to {peer_name}")
        self._load_history()

    def _on_incoming_transfer_gui(self, transfer_id: str, file_name: str,
                                   peer_name: str, file_size: int,
                                   file_hash: str) -> None:
        reply = QMessageBox.question(
            self, "Incoming File Transfer",
            f"{peer_name} wants to send:\n\n"
            f"File: {file_name}\nSize: {format_bytes(file_size)}\n"
            f"Hash: {file_hash[:16]}...\n\nAccept?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        transfer = self._pending_incoming.pop(transfer_id, None)
        if not transfer:
            return
        if reply == QMessageBox.StandardButton.Yes:
            download_dir = self._config.download_dir
            self._schedule_async(
                self._transfer_controller.accept_transfer(transfer_id, download_dir)
            )
        else:
            self._schedule_async(
                self._transfer_controller.reject_transfer(transfer_id)
            )

    def _on_log_gui(self, level: str, message: str) -> None:
        self._log_viewer.append_log(level, message)

    def _on_firewall_warning_gui(self, message: str) -> None:
        self._status_label.setText("Firewall blocking connections — run as Admin")
        QMessageBox.warning(self, "Firewall Blocking Connections", message)

    # --- GUI signal handlers (GUI thread) ---

    def _on_connect_request(self, peer_id: str) -> None:
        peer = self._peer_discovery.get_peer(peer_id)
        if peer:
            self._log_viewer.append_log("INFO",
                f"Connecting to {peer.display_name} ({peer.host}:{peer.port})...")
            self._schedule_async(self._connection_manager.connect_to_peer(peer))

    def _on_disconnect_request(self, peer_id: str) -> None:
        self._schedule_async(
            self._connection_manager.disconnect_from_peer(peer_id, "user requested")
        )

    def _on_pause_request(self, transfer_id: str) -> None:
        self._schedule_async(self._transfer_controller.pause_transfer(transfer_id))
        self._log_viewer.append_log("INFO", f"Paused {transfer_id[:8]}...")

    def _on_resume_request(self, transfer_id: str) -> None:
        self._schedule_async(self._transfer_controller.resume_transfer(transfer_id))
        self._log_viewer.append_log("INFO", f"Resumed {transfer_id[:8]}...")

    def _on_cancel_request(self, transfer_id: str) -> None:
        self._schedule_async(self._transfer_controller.cancel_transfer(transfer_id))
        self._log_viewer.append_log("INFO", f"Cancelled {transfer_id[:8]}...")

    def _on_transfer_selected(self, transfer: Transfer) -> None:
        dialog = TransferDetailDialog(transfer, self)
        dialog.show()

    def _on_files_dropped(self, paths: List[str]) -> None:
        peer_ids = list(self._connection_manager.connections.keys())
        if not peer_ids:
            QMessageBox.warning(self, "No Peers",
                "No connected peers. Connect to a peer first.")
            return
        connected = [self._connection_manager.connections[pid].peer for pid in peer_ids]
        if len(connected) == 1:
            peer = connected[0]
            for file_path in paths:
                self._schedule_async(
                    self._transfer_controller.send_file(peer.peer_id, file_path)
                )
                self._log_viewer.append_log("INFO",
                    f"Queued {os.path.basename(file_path)} for {peer.display_name}")
        else:
            names = [p.display_name for p in connected]
            name, ok = QInputDialog.getItem(self, "Select Peer", "Send to:",
                                             names, 0, False)
            if ok and name:
                for peer in connected:
                    if peer.display_name == name:
                        for file_path in paths:
                            self._schedule_async(
                                self._transfer_controller.send_file(peer.peer_id, file_path)
                            )
                        break

    def _browse_and_send(self) -> None:
        self._file_drop._browse()

    def _manual_connect(self) -> None:
        host, ok = QInputDialog.getText(self, "Connect to Peer", "IP Address:")
        if ok and host:
            port, ok = QInputDialog.getInt(self, "Connect to Peer", "Port:",
                                           value=self._server_port or 53333,
                                           min=1024, max=65535)
            if ok:
                peer = self._peer_discovery.add_manual_peer(
                    host, port, f"Peer@{host}:{port}")
                if peer:
                    self._schedule_async(self._connection_manager.connect_to_peer(peer))

    def _disconnect_all(self) -> None:
        self._schedule_async(self._connection_manager.disconnect_all())

    def _refresh_discovery(self) -> None:
        self._log_viewer.append_log("INFO", "Refreshing discovery...")

    def _show_settings(self) -> None:
        dialog = SettingsDialog(self)
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            if dialog.settings_changed:
                self._apply_theme()
                self._log_viewer.append_log("INFO", "Settings updated")

    def _show_about(self) -> None:
        QMessageBox.about(self, f"About {APP_NAME}",
            f"<h2>{APP_NAME} v{APP_VERSION}</h2>"
            f"<p>Secure P2P File Sharing</p>"
            f"<p>X25519 + HKDF-SHA256 + AES-256-GCM</p>"
            f"<p>Academic Research Project</p>")

    def _update_ui(self) -> None:
        if not self._running:
            return
        transfers = self._transfer_controller.get_all_active_transfers()
        self._transfer_count_label.setText(f"Transfers: {len(transfers)}")
        for transfer in transfers.values():
            if transfer.state == TRANSFER_STATE_IN_PROGRESS:
                elapsed = time.time() - transfer.started_at if transfer.started_at else 0
                eta = None
                if transfer.bytes_transferred > 0 and elapsed > 0:
                    speed = transfer.bytes_transferred / elapsed
                    remaining = transfer.bytes_total - transfer.bytes_transferred
                    if speed > 0:
                        eta = format_duration(remaining / speed)
                transfer.eta = eta
                self._transfer_list.add_or_update_transfer(transfer)
        for peer_id, conn in self._connection_manager.connections.items():
            peer = self._peer_list._peers.get(peer_id)
            if peer:
                peer.latency = conn.peer.latency
                peer.state = conn.peer.state
                self._peer_list.update_peer(peer)

    def _update_bandwidth_graph(self) -> None:
        if not self._running:
            return
        total = 0.0
        for t in self._transfer_controller.get_all_active_transfers().values():
            total += t.speed
        self._bandwidth_graph.add_sample(total)


def run_gui(config: ConfigManager) -> None:
    """Run the GUI application with asyncio in a background thread."""
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("SecureP2P")

    window = MainWindow()
    window.show()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    window._asyncio_loop = loop

    async def _start() -> None:
        await window.start()
        while window._running:
            await asyncio.sleep(0.1)

    def run_loop() -> None:
        loop.run_until_complete(_start())

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()

    exit_code = app.exec()
    window._running = False
    sys.exit(exit_code)
