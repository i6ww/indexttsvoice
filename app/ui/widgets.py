from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)
from shiboken6 import isValid


@dataclass
class CloneItem:
    item_id: int
    text: str
    profile_name: str
    output_path: Path | None = None
    status: str = "待生成"


class NavButton(QPushButton):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(48)


class RowWidget(QFrame):
    generate_requested = Signal(int)
    play_requested = Signal(int)
    pause_requested = Signal(int)
    add_requested = Signal(int)
    delete_requested = Signal(int)
    speed_changed = Signal(int, str)

    def __init__(
        self,
        item: CloneItem,
        index: int,
        profile_names: list[str],
        is_player_active: bool,
        parent: QFrame | None = None,
    ) -> None:
        super().__init__(parent)
        self.item = item
        self.setObjectName("CloneCard")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel(f"No.{index:02d}  第 {index} 条文案")
        title.setObjectName("CardTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.status_label = QLabel(item.status)
        self.status_label.setObjectName("StatusPill")
        header.addWidget(self.status_label)
        root.addLayout(header)

        self.text_edit = QTextEdit()
        self.text_edit.setObjectName("ScriptEditor")
        self.text_edit.setPlainText(item.text)
        self.text_edit.setMinimumHeight(104)
        root.addWidget(self.text_edit)

        controls = QHBoxLayout()
        role_label = QLabel("选择音色")
        role_label.setObjectName("FieldLabel")
        controls.addWidget(role_label)
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(180)
        self.profile_combo.addItems(profile_names)
        if item.profile_name in profile_names:
            self.profile_combo.setCurrentText(item.profile_name)
        controls.addWidget(self.profile_combo)
        controls.addStretch(1)

        self.generate_button = QPushButton("重新生成" if item.output_path else "生成")
        self.generate_button.setObjectName("PrimarySmallButton")
        self.generate_button.clicked.connect(lambda: self.generate_requested.emit(item.item_id))
        controls.addWidget(self.generate_button)

        self.play_button = QPushButton("播放")
        self.play_button.setObjectName("GhostButton")
        self.play_button.clicked.connect(lambda: self.play_requested.emit(item.item_id))
        controls.addWidget(self.play_button)

        add_button = QPushButton("新增下行")
        add_button.setObjectName("GhostButton")
        add_button.clicked.connect(lambda: self.add_requested.emit(item.item_id))
        controls.addWidget(add_button)

        delete_button = QPushButton("删除")
        delete_button.setObjectName("DangerButton")
        delete_button.clicked.connect(lambda: self.delete_requested.emit(item.item_id))
        controls.addWidget(delete_button)
        root.addLayout(controls)

        self.player_panel = QFrame()
        self.player_panel.setObjectName("PlayerPanel")
        player_layout = QHBoxLayout(self.player_panel)
        player_layout.setContentsMargins(14, 10, 14, 10)
        player_layout.setSpacing(10)
        player_layout.addWidget(QLabel("播放进度"))
        self.player_progress = QProgressBar()
        self.player_progress.setRange(0, 1000)
        self.player_progress.setTextVisible(False)
        player_layout.addWidget(self.player_progress, 1)
        self.player_time = QLabel("0:00 / 0:00")
        self.player_time.setObjectName("MutedLabel")
        player_layout.addWidget(self.player_time)

        pause_button = QPushButton("暂停播放")
        pause_button.setObjectName("GhostButton")
        pause_button.clicked.connect(lambda: self.pause_requested.emit(item.item_id))
        player_layout.addWidget(pause_button)

        player_layout.addWidget(QLabel("倍速"))
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.75x", "1x", "1.25x", "1.5x", "2x"])
        self.speed_combo.setCurrentText("1x")
        self.speed_combo.currentTextChanged.connect(
            lambda value: self.speed_changed.emit(item.item_id, value)
        )
        player_layout.addWidget(self.speed_combo)
        self.player_panel.setVisible(is_player_active)
        root.addWidget(self.player_panel)

    def snapshot(self) -> bool:
        if not isValid(self) or not isValid(self.text_edit) or not isValid(self.profile_combo):
            return False
        self.item.text = self.text_edit.toPlainText().strip()
        self.item.profile_name = self.profile_combo.currentText().strip()
        return True

    def set_status(self, status: str) -> None:
        self.item.status = status
        self.status_label.setText(status)
