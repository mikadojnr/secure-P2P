from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QVBoxLayout, QWidget
)

from storage.models import Transfer
from utils.constants import (
    TRANSFER_DIRECTION_SEND, TRANSFER_DIRECTION_RECEIVE,
    TRANSFER_STATE_COMPLETED, TRANSFER_STATE_FAILED,
    TRANSFER_STATE_IN_PROGRESS, TRANSFER_STATE_PAUSED, TRANSFER_STATE_PENDING
)
from utils.helpers import format_bytes, format_duration, format_speed


class TransferDetailDialog(QDialog):
    """Detailed view of a single transfer."""

    def __init__(self, transfer: Transfer, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._transfer: Transfer = transfer
        self.setWindowTitle(f"Transfer: {transfer.file_name}")
        self.setMinimumSize(400, 300)
        self.setModal(True)
        self._setup_ui()
        self._update_display()

    def _setup_ui(self) -> None:
        layout: QVBoxLayout = QVBoxLayout(self)

        self._name_label: QLabel = QLabel()
        self._name_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        layout.addWidget(self._name_label)

        self._progress_bar: QProgressBar = QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setTextVisible(True)
        layout.addWidget(self._progress_bar)

        info_layout: QVBoxLayout = QVBoxLayout()
        self._size_label: QLabel = QLabel()
        info_layout.addWidget(self._size_label)
        self._speed_label: QLabel = QLabel()
        info_layout.addWidget(self._speed_label)
        self._eta_label: QLabel = QLabel()
        info_layout.addWidget(self._eta_label)
        self._state_label: QLabel = QLabel()
        info_layout.addWidget(self._state_label)
        self._peer_label: QLabel = QLabel()
        info_layout.addWidget(self._peer_label)
        self._direction_label: QLabel = QLabel()
        info_layout.addWidget(self._direction_label)
        self._hash_label: QLabel = QLabel()
        self._hash_label.setWordWrap(True)
        info_layout.addWidget(self._hash_label)
        layout.addLayout(info_layout)

        btn_layout: QHBoxLayout = QHBoxLayout()
        self._close_btn: QPushButton = QPushButton("Close")
        self._close_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(self._close_btn)
        layout.addLayout(btn_layout)

    def update_transfer(self, transfer: Transfer) -> None:
        self._transfer = transfer
        self._update_display()

    def _update_display(self) -> None:
        t = self._transfer
        self._name_label.setText(t.file_name)
        self._progress_bar.setValue(int(t.progress))
        self._progress_bar.setFormat(f"{t.progress:.1f}%")
        self._size_label.setText(f"Size: {format_bytes(t.file_size)} (Transferred: {format_bytes(t.bytes_transferred)})")
        self._speed_label.setText(f"Speed: {format_speed(t.speed) if t.speed > 0 else 'Waiting...'}")
        self._eta_label.setText(f"ETA: {t.eta or 'Calculating...'}")
        self._state_label.setText(f"State: {t.state.replace('_', ' ').title()}")
        self._peer_label.setText(f"Peer: {t.peer_name}")
        direction_str: str = "Sending" if t.direction == TRANSFER_DIRECTION_SEND else "Receiving"
        self._direction_label.setText(f"Direction: {direction_str}")
        self._hash_label.setText(f"SHA-256: {t.file_hash[:32]}..." if t.file_hash else "")


class TransferWindow(QWidget):
    """Transfer queue and history window."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        from gui.widgets import TransferListWidget
        layout: QVBoxLayout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._transfer_list: TransferListWidget = TransferListWidget()
        layout.addWidget(self._transfer_list)
