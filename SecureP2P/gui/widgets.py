import math
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import (
    Qt, QTimer, QRectF, QPointF, pyqtSignal, QSize, QMimeData
)
from PyQt6.QtGui import (
    QAction, QBrush, QColor, QDragEnterEvent, QDropEvent, QFont,
    QIcon, QPainter, QPainterPath, QPen, QPixmap
)
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QListWidget, QListWidgetItem, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QTextEdit, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget, QStyledItemDelegate,
    QStyleOptionViewItem, QStyle, QAbstractItemView
)

from storage.models import Peer, Transfer
from utils.constants import (
    PEER_STATE_AUTHENTICATED, PEER_STATE_CONNECTED, PEER_STATE_CONNECTING,
    PEER_STATE_DISCONNECTED, TRANSFER_STATE_COMPLETED, TRANSFER_STATE_IN_PROGRESS,
    TRANSFER_STATE_PAUSED, TRANSFER_STATE_PENDING, TRANSFER_DIRECTION_SEND,
    TRANSFER_DIRECTION_RECEIVE
)
from utils.helpers import format_bytes, format_duration, format_speed


class StatusIndicator(QWidget):
    """Shows connection, encryption, and compression status."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._connection_state: str = PEER_STATE_DISCONNECTED
        self._encryption_active: bool = False
        self._compression_active: bool = False
        self.setMinimumSize(200, 24)
        self.setMaximumHeight(24)

    def set_connection(self, state: str) -> None:
        self._connection_state = state
        self.update()

    def set_encryption(self, active: bool) -> None:
        self._encryption_active = active
        self.update()

    def set_compression(self, active: bool) -> None:
        self._compression_active = active
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter: QPainter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        x: int = 5
        items: List[Tuple[str, bool, QColor]] = [
            ("Conn", self._connection_state == PEER_STATE_AUTHENTICATED,
             QColor("#00ff88") if self._connection_state == PEER_STATE_AUTHENTICATED
             else QColor("#ffaa00") if self._connection_state in (PEER_STATE_CONNECTED, PEER_STATE_CONNECTING)
             else QColor("#ff4444")),
            ("Enc", self._encryption_active, QColor("#00ff88") if self._encryption_active else QColor("#ff4444")),
            ("Zip", self._compression_active, QColor("#00ff88") if self._compression_active else QColor("#888888")),
        ]
        for label, active, color in items:
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color.darker(150), 1))
            painter.drawEllipse(QPointF(x + 6, 12), 5, 5)
            painter.setPen(QPen(QColor("#cccccc"), 1))
            painter.drawText(int(x + 14), 16, label)
            x += 55


class PeerListWidget(QWidget):
    """Displays discovered peers with connection controls."""

    peer_selected = pyqtSignal(object)
    connect_requested = pyqtSignal(str)
    disconnect_requested = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._peers: Dict[str, Peer] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout: QVBoxLayout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header: QLabel = QLabel("Peers")
        header.setStyleSheet("font-weight: bold; font-size: 14px; padding: 4px;")
        layout.addWidget(header)

        self._tree: QTreeWidget = QTreeWidget()
        self._tree.setHeaderLabels(["Peer", "Status", "Type", "Latency"])
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.itemClicked.connect(self._on_item_clicked)
        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._tree)

        btn_layout: QHBoxLayout = QHBoxLayout()
        self._connect_btn: QPushButton = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._on_connect)
        self._disconnect_btn: QPushButton = QPushButton("Disconnect")
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        self._disconnect_btn.setEnabled(False)
        btn_layout.addWidget(self._connect_btn)
        btn_layout.addWidget(self._disconnect_btn)
        layout.addLayout(btn_layout)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        peer_id: str = item.data(0, Qt.ItemDataRole.UserRole)
        if peer_id and peer_id in self._peers:
            peer: Peer = self._peers[peer_id]
            self.peer_selected.emit(peer)
            self._connect_btn.setEnabled(peer.state == PEER_STATE_DISCONNECTED)
            self._disconnect_btn.setEnabled(peer.state in (
                PEER_STATE_CONNECTED, PEER_STATE_AUTHENTICATED
            ))

    def _on_connect(self) -> None:
        item = self._tree.currentItem()
        if item:
            peer_id: str = item.data(0, Qt.ItemDataRole.UserRole)
            if peer_id:
                self.connect_requested.emit(peer_id)

    def _on_disconnect(self) -> None:
        item = self._tree.currentItem()
        if item:
            peer_id: str = item.data(0, Qt.ItemDataRole.UserRole)
            if peer_id:
                self.disconnect_requested.emit(peer_id)

    def add_peer(self, peer: Peer) -> None:
        self._peers[peer.peer_id] = peer
        self._update_peer_item(peer)

    def update_peer(self, peer: Peer) -> None:
        self._peers[peer.peer_id] = peer
        self._update_peer_item(peer)

    def remove_peer(self, peer_id: str) -> None:
        self._peers.pop(peer_id, None)
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item and item.data(0, Qt.ItemDataRole.UserRole) == peer_id:
                self._tree.takeTopLevelItem(i)
                break

    def _update_peer_item(self, peer: Peer) -> None:
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item and item.data(0, Qt.ItemDataRole.UserRole) == peer.peer_id:
                self._set_peer_item_data(item, peer)
                return
        item = QTreeWidgetItem(self._tree)
        item.setData(0, Qt.ItemDataRole.UserRole, peer.peer_id)
        self._set_peer_item_data(item, peer)
        self._tree.addTopLevelItem(item)

    def _set_peer_item_data(self, item: QTreeWidgetItem, peer: Peer) -> None:
        state_colors: Dict[str, str] = {
            PEER_STATE_AUTHENTICATED: "#00ff88",
            PEER_STATE_CONNECTED: "#ffaa00",
            PEER_STATE_CONNECTING: "#ffaa00",
            PEER_STATE_DISCONNECTED: "#ff4444"
        }
        color: str = state_colors.get(peer.state, "#888888")
        hostname: str = peer.metadata.get("hostname", "") if peer.metadata else ""
        display: str = hostname if hostname else peer.display_name
        item.setText(0, display)
        item.setText(1, peer.state.capitalize())
        item.setText(2, peer.connection_type.upper())
        item.setText(3, f"{peer.latency:.0f}ms" if peer.latency > 0 else "-")
        item.setForeground(1, QColor(color))
        for col in range(4):
            item.setToolTip(col,
                f"Device: {hostname}\n"
                f"Peer ID: {peer.peer_id[:16]}...\n"
                f"IP: {peer.host}:{peer.port}\n"
                f"Type: {peer.connection_type}\n"
                f"NAT: {peer.nat_type}\n"
                f"Encrypted: {'Yes' if peer.session_key else 'No'}"
            )

    def clear(self) -> None:
        self._peers.clear()
        self._tree.clear()


class TransferListWidget(QWidget):
    """Shows active and queued transfers."""

    transfer_selected = pyqtSignal(object)
    pause_requested = pyqtSignal(str)
    resume_requested = pyqtSignal(str)
    cancel_requested = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._transfers: Dict[str, Transfer] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout: QVBoxLayout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header: QLabel = QLabel("Transfers")
        header.setStyleSheet("font-weight: bold; font-size: 14px; padding: 4px;")
        layout.addWidget(header)

        self._table: QTableWidget = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ["File", "Peer", "Size", "Progress", "Speed", "State", "ETA"]
        )
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self._table.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._table)

        btn_layout: QHBoxLayout = QHBoxLayout()
        self._pause_btn: QPushButton = QPushButton("Pause")
        self._pause_btn.clicked.connect(lambda: self.pause_requested.emit(self._selected_id()))
        self._resume_btn: QPushButton = QPushButton("Resume")
        self._resume_btn.clicked.connect(lambda: self.resume_requested.emit(self._selected_id()))
        self._cancel_btn: QPushButton = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self._selected_id()))
        for btn in (self._pause_btn, self._resume_btn, self._cancel_btn):
            btn.setEnabled(False)
        btn_layout.addWidget(self._pause_btn)
        btn_layout.addWidget(self._resume_btn)
        btn_layout.addWidget(self._cancel_btn)
        layout.addLayout(btn_layout)

    def _selected_id(self) -> str:
        row: int = self._table.currentRow()
        if row >= 0:
            item = self._table.item(row, 0)
            if item:
                return item.data(Qt.ItemDataRole.UserRole)
        return ""

    def _on_item_clicked(self, item: QTableWidgetItem) -> None:
        row: int = item.row()
        transfer_id: str = self._table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        transfer: Optional[Transfer] = self._transfers.get(transfer_id)
        if transfer:
            self.transfer_selected.emit(transfer)
            self._pause_btn.setEnabled(transfer.state == TRANSFER_STATE_IN_PROGRESS)
            self._resume_btn.setEnabled(transfer.state == TRANSFER_STATE_PAUSED)
            self._cancel_btn.setEnabled(transfer.state in (
                TRANSFER_STATE_PENDING, TRANSFER_STATE_IN_PROGRESS, TRANSFER_STATE_PAUSED
            ))

    def add_or_update_transfer(self, transfer: Transfer) -> None:
        self._transfers[transfer.transfer_id] = transfer
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == transfer.transfer_id:
                self._set_row_data(row, transfer)
                return
        row = self._table.rowCount()
        self._table.insertRow(row)
        item = QTableWidgetItem(transfer.file_name)
        item.setData(Qt.ItemDataRole.UserRole, transfer.transfer_id)
        self._table.setItem(row, 0, item)
        self._set_row_data(row, transfer)

    def _set_row_data(self, row: int, transfer: Transfer) -> None:
        self._table.item(row, 0).setText(transfer.file_name)
        self._set_cell(row, 1, transfer.peer_name)
        self._set_cell(row, 2, format_bytes(transfer.file_size))
        progress = transfer.progress
        self._set_cell(row, 3, f"{progress:.1f}%")
        self._set_cell(row, 4, format_speed(transfer.speed) if transfer.speed > 0 else "-")
        state_colors: Dict[str, QColor] = {
            TRANSFER_STATE_IN_PROGRESS: QColor("#00ff88"),
            TRANSFER_STATE_PAUSED: QColor("#ffaa00"),
            TRANSFER_STATE_COMPLETED: QColor("#4466ff"),
            TRANSFER_STATE_PENDING: QColor("#888888"),
            "failed": QColor("#ff4444"),
            "cancelled": QColor("#ff4444")
        }
        state_item = QTableWidgetItem(transfer.state.replace("_", " ").title())
        state_item.setForeground(state_colors.get(transfer.state, QColor("#888888")))
        self._table.setItem(row, 5, state_item)
        self._set_cell(row, 6, transfer.eta or "-")

    def _set_cell(self, row: int, col: int, text: str) -> None:
        if self._table.item(row, col):
            self._table.item(row, col).setText(text)
        else:
            self._table.setItem(row, col, QTableWidgetItem(text))

    def remove_transfer(self, transfer_id: str) -> None:
        self._transfers.pop(transfer_id, None)
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == transfer_id:
                self._table.removeRow(row)
                break

    def clear(self) -> None:
        self._transfers.clear()
        self._table.setRowCount(0)


class FileDropWidget(QWidget):
    """Drag-and-drop file selection widget."""

    files_dropped = pyqtSignal(list)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(100)
        self.setStyleSheet("""
            FileDropWidget {
                border: 2px dashed #555;
                border-radius: 8px;
                background: #1a1a2e;
            }
        """)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout: QVBoxLayout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label: QLabel = QLabel("Drop files here\nor click Browse")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("color: #888; font-size: 14px;")
        layout.addWidget(self._label)

        self._browse_btn: QPushButton = QPushButton("Browse Files")
        self._browse_btn.clicked.connect(self._browse)
        layout.addWidget(self._browse_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("""
                FileDropWidget {
                    border: 2px dashed #00ff88;
                    border-radius: 8px;
                    background: #1a3a2e;
                }
            """)

    def dragLeaveEvent(self, event: Any) -> None:
        self.setStyleSheet("""
            FileDropWidget {
                border: 2px dashed #555;
                border-radius: 8px;
                background: #1a1a2e;
            }
        """)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setStyleSheet("""
            FileDropWidget {
                border: 2px dashed #555;
                border-radius: 8px;
                background: #1a1a2e;
            }
        """)
        paths: list = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                paths.append(url.toLocalFile())
        if paths:
            self.files_dropped.emit(paths)

    def _browse(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select files to send"
        )
        if paths:
            self.files_dropped.emit(paths)


class BandwidthGraph(QWidget):
    """Real-time bandwidth usage graph."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._data: List[float] = [0.0] * 60
        self._max_value: float = 1024.0
        self.setMinimumSize(300, 100)
        self.setMaximumHeight(150)

    def add_sample(self, bytes_per_sec: float) -> None:
        self._data.append(bytes_per_sec)
        if len(self._data) > 60:
            self._data.pop(0)
        self._max_value = max(max(self._data), 1024.0)
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter: QPainter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w: float = self.width()
        h: float = self.height()

        painter.fillRect(0, 0, int(w), int(h), QColor("#0d0d1a"))

        if not self._data:
            return

        pen: QPen = QPen(QColor("#00ff88"), 2)
        painter.setPen(pen)

        path: QPainterPath = QPainterPath()
        step: float = w / 59.0
        for i, value in enumerate(self._data):
            x: float = i * step
            y: float = h - (value / self._max_value * (h - 10))
            y = max(0, y)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        painter.drawPath(path)

        painter.setPen(QPen(QColor("#4466ff"), 1))
        avg: float = sum(self._data) / len(self._data)
        avg_y: float = h - (avg / self._max_value * (h - 10))
        painter.drawLine(0, int(avg_y), int(w), int(avg_y))

        painter.setPen(QColor("#888888"))
        painter.drawText(5, int(h) - 5,
            f"{format_speed(self._data[-1])} / Avg: {format_speed(avg)}")


class LogViewer(QWidget):
    """Log viewer widget with filtering."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout: QVBoxLayout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header: QLabel = QLabel("Logs")
        header.setStyleSheet("font-weight: bold; font-size: 14px; padding: 4px;")
        layout.addWidget(header)

        self._text: QTextEdit = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(QFont("Consolas", 9))
        layout.addWidget(self._text)

        btn_layout: QHBoxLayout = QHBoxLayout()
        self._clear_btn: QPushButton = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._text.clear)
        self._export_btn: QPushButton = QPushButton("Export")
        self._export_btn.clicked.connect(self._export)
        btn_layout.addWidget(self._clear_btn)
        btn_layout.addWidget(self._export_btn)
        layout.addLayout(btn_layout)

    def append_log(self, level: str, message: str) -> None:
        colors: Dict[str, str] = {
            "DEBUG": "#888888",
            "INFO": "#cccccc",
            "WARNING": "#ffaa00",
            "ERROR": "#ff4444",
            "CRITICAL": "#ff0000"
        }
        color: str = colors.get(level, "#888888")
        timestamp: str = time.strftime("%H:%M:%S")
        html: str = f'<span style="color: {color};">[{timestamp}] [{level}] {message}</span><br>'
        self._text.insertHtml(html)
        scrollbar = self._text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _export(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Logs", "securep2p_logs.txt", "Text Files (*.txt)"
        )
        if path:
            try:
                with open(path, "w") as f:
                    f.write(self._text.toPlainText())
            except Exception as e:
                self.append_log("ERROR", f"Failed to export logs: {e}")
