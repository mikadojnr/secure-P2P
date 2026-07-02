from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget
)

from utils.config import ConfigManager
from utils.constants import (
    CHUNK_SIZES, COMPRESSION_LEVELS, DEFAULT_CHUNK_SIZE, DEFAULT_COMPRESSION,
    DEFAULT_DOWNLOAD_DIR
)


class SettingsDialog(QDialog):
    """Application settings dialog."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config: ConfigManager = ConfigManager()
        self._settings_changed: bool = False
        self.setWindowTitle("SecureP2P Settings")
        self.setMinimumSize(500, 400)
        self.setModal(True)
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        layout: QVBoxLayout = QVBoxLayout(self)
        tabs: QTabWidget = QTabWidget()

        general_tab: QWidget = self._create_general_tab()
        network_tab: QWidget = self._create_network_tab()
        transfer_tab: QWidget = self._create_transfer_tab()
        security_tab: QWidget = self._create_security_tab()

        tabs.addTab(general_tab, "General")
        tabs.addTab(transfer_tab, "Transfer")
        tabs.addTab(network_tab, "Network")
        tabs.addTab(security_tab, "Security")

        layout.addWidget(tabs)

        btn_layout: QHBoxLayout = QHBoxLayout()
        save_btn: QPushButton = QPushButton("Save")
        save_btn.clicked.connect(self._save_settings)
        cancel_btn: QPushButton = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        defaults_btn: QPushButton = QPushButton("Reset Defaults")
        defaults_btn.clicked.connect(self._reset_defaults)
        btn_layout.addWidget(defaults_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _create_general_tab(self) -> QWidget:
        widget: QWidget = QWidget()
        form: QFormLayout = QFormLayout(widget)
        self._download_dir_edit: QLineEdit = QLineEdit()
        self._download_dir_btn: QPushButton = QPushButton("Browse")
        self._download_dir_btn.clicked.connect(self._browse_download_dir)
        dir_layout: QHBoxLayout = QHBoxLayout()
        dir_layout.addWidget(self._download_dir_edit)
        dir_layout.addWidget(self._download_dir_btn)
        form.addRow("Download Directory:", dir_layout)
        self._dark_mode_cb: QCheckBox = QCheckBox("Enable Dark Mode")
        form.addRow("Appearance:", self._dark_mode_cb)
        self._log_level_combo: QComboBox = QComboBox()
        self._log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        form.addRow("Log Level:", self._log_level_combo)
        self._max_transfers_spin: QSpinBox = QSpinBox()
        self._max_transfers_spin.setRange(1, 50)
        self._max_transfers_spin.setValue(10)
        form.addRow("Max Concurrent Transfers:", self._max_transfers_spin)
        return widget

    def _create_network_tab(self) -> QWidget:
        widget: QWidget = QWidget()
        form: QFormLayout = QFormLayout(widget)
        self._auto_reconnect_cb: QCheckBox = QCheckBox("Auto Reconnect")
        form.addRow("Connection:", self._auto_reconnect_cb)
        self._peer_timeout_spin: QSpinBox = QSpinBox()
        self._peer_timeout_spin.setRange(10, 300)
        self._peer_timeout_spin.setSuffix(" seconds")
        form.addRow("Peer Timeout:", self._peer_timeout_spin)
        self._connect_timeout_spin: QSpinBox = QSpinBox()
        self._connect_timeout_spin.setRange(5, 120)
        self._connect_timeout_spin.setSuffix(" seconds")
        form.addRow("Connect Timeout:", self._connect_timeout_spin)
        self._max_retries_spin: QSpinBox = QSpinBox()
        self._max_retries_spin.setRange(0, 10)
        form.addRow("Max Connect Retries:", self._max_retries_spin)
        self._max_peers_spin: QSpinBox = QSpinBox()
        self._max_peers_spin.setRange(1, 100)
        form.addRow("Max Peers:", self._max_peers_spin)
        stun_label: QLabel = QLabel("STUN servers are configured in the config file.")
        stun_label.setStyleSheet("color: #888;")
        form.addRow(stun_label)
        return widget

    def _create_transfer_tab(self) -> QWidget:
        widget: QWidget = QWidget()
        form: QFormLayout = QFormLayout(widget)
        self._compression_combo: QComboBox = QComboBox()
        self._compression_combo.addItems(list(COMPRESSION_LEVELS.keys()))
        form.addRow("Compression Mode:", self._compression_combo)
        self._chunk_size_combo: QComboBox = QComboBox()
        size_names: dict = {
            "32 KB (Poor Network)": 32768,
            "64 KB (Average)": 65536,
            "256 KB (Good)": 262144,
            "512 KB (Excellent)": 524288
        }
        self._chunk_size_combo.addItems(list(size_names.keys()))
        self._chunk_sizes: dict = size_names
        form.addRow("Chunk Size:", self._chunk_size_combo)
        self._max_bw_spin: QSpinBox = QSpinBox()
        self._max_bw_spin.setRange(0, 1000000)
        self._max_bw_spin.setSuffix(" KB/s (0 = unlimited)")
        self._max_bw_spin.setSingleStep(100)
        form.addRow("Max Bandwidth:", self._max_bw_spin)
        return widget

    def _create_security_tab(self) -> QWidget:
        widget: QWidget = QWidget()
        form: QFormLayout = QFormLayout(widget)
        info: QLabel = QLabel(
            "Security is always enabled.\n\n"
            "Protocol: X25519 + HKDF-SHA256\n"
            "Encryption: AES-256-GCM\n"
            "Integrity: SHA-256\n"
            "Perfect Forward Secrecy: Enabled\n"
            "Replay Protection: Enabled\n"
            "Mutual Authentication: Enabled"
        )
        info.setStyleSheet("color: #aaa; padding: 10px;")
        info.setWordWrap(True)
        form.addRow(info)
        return widget

    def _load_settings(self) -> None:
        self._download_dir_edit.setText(self._config.download_dir)
        self._dark_mode_cb.setChecked(self._config.dark_mode)
        self._log_level_combo.setCurrentText(self._config.log_level.upper())
        self._max_transfers_spin.setValue(self._config.get("max_transfers", 10))
        self._auto_reconnect_cb.setChecked(self._config.auto_reconnect)
        self._peer_timeout_spin.setValue(int(self._config.peer_timeout))
        self._connect_timeout_spin.setValue(int(self._config.connect_timeout))
        self._max_retries_spin.setValue(self._config.max_connect_retries)
        self._max_peers_spin.setValue(self._config.get("max_peers", 50))
        self._compression_combo.setCurrentText(self._config.compression)
        current_chunk = self._config.chunk_size
        for name, size in self._chunk_sizes.items():
            if size == current_chunk:
                self._chunk_size_combo.setCurrentText(name)
                break
        self._max_bw_spin.setValue(self._config.max_bandwidth // 1024)

    def _save_settings(self) -> None:
        self._config.download_dir = self._download_dir_edit.text()
        self._config.dark_mode = self._dark_mode_cb.isChecked()
        self._config.log_level = self._log_level_combo.currentText()
        self._config.set("max_transfers", self._max_transfers_spin.value())
        self._config.auto_reconnect = self._auto_reconnect_cb.isChecked()
        self._config.peer_timeout = float(self._peer_timeout_spin.value())
        self._config.connect_timeout = float(self._connect_timeout_spin.value())
        self._config.max_connect_retries = self._max_retries_spin.value()
        self._config.set("max_peers", self._max_peers_spin.value())
        self._config.compression = self._compression_combo.currentText()
        chunk_name: str = self._chunk_size_combo.currentText()
        chunk_size: int = self._chunk_sizes.get(chunk_name, DEFAULT_CHUNK_SIZE)
        self._config.chunk_size = chunk_size
        self._config.max_bandwidth = self._max_bw_spin.value() * 1024
        self._settings_changed = True
        self.accept()

    def _reset_defaults(self) -> None:
        self._config.reset_to_defaults()
        self._load_settings()

    def _browse_download_dir(self) -> None:
        path: str = QFileDialog.getExistingDirectory(
            self, "Select Download Directory", self._download_dir_edit.text()
        )
        if path:
            self._download_dir_edit.setText(path)

    @property
    def settings_changed(self) -> bool:
        return self._settings_changed
