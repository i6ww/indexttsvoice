from __future__ import annotations

import asyncio
import os
import tempfile
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from app.core.config import AppConfig, VoiceProfile, load_config, save_config
from app.services.gitee_tts import GiteeTTSRequest, create_speech
from app.services.task_log import task_log_path, write_task_log
from app.ui.widgets import CloneItem, NavButton, RowWidget
from app.ui.workers import AsyncJob


APP_DISPLAY_NAME = "秒图语音工厂"
APP_SUBTITLE = "Voice Factory"


def asset_path(relative_path: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path.cwd()))
    return base / relative_path


@dataclass(frozen=True)
class GenerateSpec:
    item_id: int
    index: int
    text: str
    output_path: Path
    output_format: str
    request: GiteeTTSRequest


@dataclass(frozen=True)
class GenerateOutcome:
    item_id: int
    index: int
    output_path: Path | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.output_path is not None


class VoiceCloneWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.app_icon = QIcon(str(asset_path("assets/icons/app.ico")))
        self.setWindowIcon(self.app_icon)
        self.resize(1220, 760)
        self.setMinimumSize(1040, 680)

        self.config_model = load_config()
        self.clone_items: list[CloneItem] = []
        self.row_widgets: dict[int, RowWidget] = {}
        self.next_item_id = 1
        self.current_jobs: list[AsyncJob] = []
        self.running_item_ids: set[int] = set()
        self.active_player_item_id: int | None = None
        self.player_duration_ms = 0
        self.player_speed = 1.0
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.9)
        self.media_player = QMediaPlayer(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.positionChanged.connect(self._on_player_position_changed)
        self.media_player.durationChanged.connect(self._on_player_duration_changed)
        self.media_player.playbackStateChanged.connect(self._on_player_state_changed)

        self._build_window()
        self._apply_styles()
        self._ensure_clone_items()
        self.show_start_page()

    def _build_window(self) -> None:
        central = QWidget()
        central.setObjectName("Root")
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(238)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(18, 24, 18, 18)
        sidebar_layout.setSpacing(8)

        brand = QHBoxLayout()
        logo = QLabel()
        logo.setObjectName("Logo")
        logo.setAlignment(Qt.AlignCenter)
        logo.setPixmap(self.app_icon.pixmap(28, 28))
        brand.addWidget(logo)
        brand_text = QVBoxLayout()
        title = QLabel(APP_DISPLAY_NAME)
        title.setObjectName("BrandTitle")
        subtitle = QLabel(APP_SUBTITLE)
        subtitle.setObjectName("BrandSubtitle")
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)
        brand.addLayout(brand_text)
        sidebar_layout.addLayout(brand)
        sidebar_layout.addSpacing(26)

        self.nav_buttons: dict[str, NavButton] = {
            "start": NavButton("▶  开始克隆"),
            "library": NavButton("▣  音色库"),
            "settings": NavButton("⚙  设置"),
        }
        self.nav_buttons["start"].clicked.connect(self.show_start_page)
        self.nav_buttons["library"].clicked.connect(self.show_library_page)
        self.nav_buttons["settings"].clicked.connect(self.show_settings_page)
        for button in self.nav_buttons.values():
            sidebar_layout.addWidget(button)
        sidebar_layout.addStretch(1)

        hint = QLabel("IndexTTS-2\n异步合成")
        hint.setObjectName("SidebarHint")
        hint.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        sidebar_layout.addWidget(hint)
        layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("ContentStack")
        layout.addWidget(self.stack, 1)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget#Root, QStackedWidget#ContentStack {
                background: #f5f8fc;
                color: #1c2f4c;
                font-family: "Microsoft YaHei UI";
                font-size: 14px;
            }
            QFrame#Sidebar {
                background: #10264a;
            }
            QLabel#Logo {
                min-width: 42px;
                min-height: 42px;
                border-radius: 12px;
                background: #2f7df6;
            }
            QLabel#BrandTitle {
                color: #ffffff;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#BrandSubtitle, QLabel#SidebarHint {
                color: #9fb5d3;
                font-size: 12px;
            }
            QLabel#SidebarHint {
                padding: 14px;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 12px;
                background: rgba(255, 255, 255, 0.06);
            }
            QPushButton {
                min-height: 36px;
                padding: 8px 14px;
                border-radius: 9px;
                border: 1px solid #d7e2f1;
                background: #ffffff;
                color: #25405f;
            }
            QPushButton:hover {
                border-color: #9fc3fb;
                background: #f4f8ff;
            }
            QPushButton:disabled {
                color: #9aa9bb;
                background: #eef3f8;
                border-color: #dce5ef;
            }
            NavButton {
                text-align: left;
                padding-left: 18px;
                border: none;
                border-radius: 12px;
                background: transparent;
                color: #bed0e6;
                font-size: 15px;
                font-weight: 600;
            }
            NavButton:hover {
                background: rgba(255, 255, 255, 0.08);
                color: #ffffff;
            }
            NavButton:checked {
                background: #2f7df6;
                color: #ffffff;
            }
            QLabel#PageTitle {
                color: #10264a;
                font-size: 26px;
                font-weight: 800;
            }
            QLabel#PageSubTitle {
                color: #6d7d92;
                font-size: 13px;
            }
            QLabel#Accent {
                color: #2f7df6;
                font-size: 22px;
                font-weight: 800;
            }
            QFrame#CloneCard, QFrame#PanelCard, QFrame#BottomBar {
                background: #ffffff;
                border: 1px solid #dde7f4;
                border-radius: 16px;
            }
            QFrame#BottomBar {
                border-color: #d4e2f4;
            }
            QLabel#CardTitle {
                color: #183457;
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#FieldLabel {
                color: #52657d;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#MutedLabel {
                color: #77869a;
                font-size: 12px;
            }
            QLabel#StatusPill {
                padding: 5px 10px;
                border-radius: 10px;
                background: #eef5ff;
                color: #2f70d8;
                font-size: 12px;
                font-weight: 700;
            }
            QTextEdit#ScriptEditor, QTextEdit, QLineEdit, QComboBox, QListWidget {
                background: #ffffff;
                border: 1px solid #d7e2f1;
                border-radius: 10px;
                padding: 8px;
                color: #1e3352;
                selection-background-color: #2f7df6;
            }
            QTextEdit#ScriptEditor {
                background: #fbfdff;
                font-size: 14px;
                line-height: 1.5;
            }
            QListWidget::item {
                min-height: 38px;
                padding: 7px 10px;
                border-radius: 8px;
            }
            QListWidget::item:selected {
                background: #e8f1ff;
                color: #1d5fcc;
            }
            QPushButton#PrimaryButton, QPushButton#PrimarySmallButton {
                background: #2f7df6;
                border-color: #2f7df6;
                color: #ffffff;
                font-weight: 700;
            }
            QPushButton#PrimaryButton:hover, QPushButton#PrimarySmallButton:hover {
                background: #236ee4;
                border-color: #236ee4;
            }
            QPushButton#PrimaryButton {
                min-height: 42px;
                padding-left: 20px;
                padding-right: 20px;
            }
            QPushButton#GhostButton {
                background: #f8fbff;
                color: #315273;
            }
            QPushButton#DangerButton {
                background: #fff7f7;
                color: #c24141;
                border-color: #f3cccc;
            }
            QFrame#PlayerPanel {
                background: #f6faff;
                border: 1px solid #d8e8ff;
                border-radius: 12px;
            }
            QProgressBar {
                min-height: 8px;
                max-height: 8px;
                border: none;
                border-radius: 4px;
                background: #e3ebf6;
            }
            QProgressBar::chunk {
                border-radius: 4px;
                background: #2f7df6;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QCheckBox {
                color: #25405f;
                spacing: 8px;
            }
            """
        )

    def _select_nav(self, key: str) -> None:
        for item_key, button in self.nav_buttons.items():
            button.setChecked(item_key == key)

    def _page_shell(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("Page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(18)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_row = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")
        title_row.addWidget(title_label)
        accent = QLabel("≋")
        accent.setObjectName("Accent")
        title_row.addWidget(accent)
        title_row.addStretch(1)
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("PageSubTitle")
        title_box.addLayout(title_row)
        title_box.addWidget(subtitle_label)
        header.addLayout(title_box)
        layout.addLayout(header)
        return page, layout

    def show_start_page(self) -> None:
        self._select_nav("start")
        self._ensure_clone_items()
        page, layout = self._page_shell(
            "开始克隆",
            "每一行是一条独立文案，可选择音色、单独生成、重生成并预览。",
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rows_container = QWidget()
        self.rows_layout = QVBoxLayout(rows_container)
        self.rows_layout.setContentsMargins(0, 0, 8, 0)
        self.rows_layout.setSpacing(14)
        scroll.setWidget(rows_container)
        layout.addWidget(scroll, 1)

        self.bottom_bar = QFrame()
        self.bottom_bar.setObjectName("BottomBar")
        bottom_layout = QVBoxLayout(self.bottom_bar)
        bottom_layout.setContentsMargins(18, 16, 18, 16)
        bottom_layout.setSpacing(12)

        output_row = QGridLayout()
        output_row.setHorizontalSpacing(12)
        output_row.setVerticalSpacing(10)
        output_row.addWidget(self._field_label("输出目录"), 0, 0)
        self.output_dir_edit = QLineEdit(self.config_model.output_dir)
        output_row.addWidget(self.output_dir_edit, 0, 1)
        choose_button = QPushButton("选择")
        choose_button.setObjectName("GhostButton")
        choose_button.clicked.connect(self._choose_output_dir)
        output_row.addWidget(choose_button, 0, 2)
        output_row.addWidget(self._field_label("导出格式"), 0, 3)
        self.output_format_combo = QComboBox()
        self.output_format_combo.addItems(["wav", "mp3"])
        self.output_format_combo.setCurrentText(self.config_model.output_format)
        output_row.addWidget(self.output_format_combo, 0, 4)
        output_row.setColumnStretch(1, 1)
        bottom_layout.addLayout(output_row)

        actions = QHBoxLayout()
        add_button = QPushButton("新增行")
        add_button.setObjectName("GhostButton")
        add_button.clicked.connect(lambda: self._add_clone_row())
        actions.addWidget(add_button)
        import_button = QPushButton("导入文案")
        import_button.setObjectName("GhostButton")
        import_button.clicked.connect(self._import_script_text)
        actions.addWidget(import_button)
        self.generate_all_button = QPushButton("全部生成")
        self.generate_all_button.setObjectName("PrimaryButton")
        self.generate_all_button.clicked.connect(self._start_generate_all)
        actions.addWidget(self.generate_all_button)
        open_button = QPushButton("打开输出目录")
        open_button.setObjectName("GhostButton")
        open_button.clicked.connect(self._open_output_dir)
        actions.addWidget(open_button)
        actions.addStretch(1)
        self.busy_progress = QProgressBar()
        self.busy_progress.setRange(0, 1)
        self.busy_progress.setValue(0)
        self.busy_progress.setFixedWidth(160)
        self.status_label = QLabel("准备就绪")
        self.status_label.setObjectName("MutedLabel")
        actions.addWidget(self.busy_progress)
        actions.addWidget(self.status_label)
        bottom_layout.addLayout(actions)
        layout.addWidget(self.bottom_bar)

        self._replace_page(page)
        self._render_clone_rows()

    def show_library_page(self) -> None:
        self._select_nav("library")
        page, layout = self._page_shell(
            "音色库",
            "在这里维护角色音色，生成时每一行都可以选择不同音色。",
        )

        body = QHBoxLayout()
        body.setSpacing(18)
        list_card = QFrame()
        list_card.setObjectName("PanelCard")
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(18, 18, 18, 18)
        list_layout.setSpacing(12)
        list_layout.addWidget(self._section_title("音色列表"))
        self.profile_list = QListWidget()
        self.profile_list.itemSelectionChanged.connect(self._load_selected_profile)
        list_layout.addWidget(self.profile_list, 1)
        new_button = QPushButton("新增音色")
        new_button.setObjectName("PrimarySmallButton")
        new_button.clicked.connect(self._new_profile)
        list_layout.addWidget(new_button)
        body.addWidget(list_card, 1)

        form_card = QFrame()
        form_card.setObjectName("PanelCard")
        form_layout = QGridLayout(form_card)
        form_layout.setContentsMargins(20, 20, 20, 20)
        form_layout.setHorizontalSpacing(14)
        form_layout.setVerticalSpacing(12)

        self.profile_name_edit = QLineEdit()
        self.profile_voice_edit = QLineEdit()
        self.profile_prompt_audio_edit = QLineEdit()
        self.profile_emo_audio_edit = QLineEdit()
        self.profile_emo_alpha_edit = QLineEdit()
        self.profile_prompt_text_edit = QTextEdit()
        self.profile_prompt_text_edit.setMinimumHeight(140)

        self._form_row(form_layout, 0, "音色名称", self.profile_name_edit)
        self._form_row(form_layout, 1, "Voice", self.profile_voice_edit)
        self._form_row(form_layout, 2, "音色参考 URL", self.profile_prompt_audio_edit)
        self._form_row(form_layout, 3, "情绪参考 URL", self.profile_emo_audio_edit)
        self._form_row(form_layout, 4, "情绪强度", self.profile_emo_alpha_edit)
        form_layout.addWidget(self._field_label("参考音频文本"), 5, 0, Qt.AlignTop)
        form_layout.addWidget(self.profile_prompt_text_edit, 5, 1)
        form_layout.setColumnStretch(1, 1)
        form_layout.setRowStretch(5, 1)

        buttons = QHBoxLayout()
        save_button = QPushButton("保存音色")
        save_button.setObjectName("PrimarySmallButton")
        save_button.clicked.connect(self._save_profile)
        delete_button = QPushButton("删除音色")
        delete_button.setObjectName("DangerButton")
        delete_button.clicked.connect(self._delete_profile)
        use_button = QPushButton("设为当前音色")
        use_button.setObjectName("GhostButton")
        use_button.clicked.connect(self._use_profile)
        buttons.addWidget(save_button)
        buttons.addWidget(delete_button)
        buttons.addWidget(use_button)
        buttons.addStretch(1)
        self.profile_status_label = QLabel("")
        self.profile_status_label.setObjectName("MutedLabel")
        buttons.addWidget(self.profile_status_label)
        form_layout.addLayout(buttons, 6, 0, 1, 2)
        body.addWidget(form_card, 2)
        layout.addLayout(body, 1)

        self._replace_page(page)
        self._refresh_profile_list()
        self._load_profile_into_form(self._selected_or_first_profile())

    def show_settings_page(self) -> None:
        self._select_nav("settings")
        page, layout = self._page_shell(
            "设置",
            "API Key 只保存在本机配置中，接口调用在后台异步执行。",
        )

        card = QFrame()
        card.setObjectName("PanelCard")
        form = QGridLayout(card)
        form.setContentsMargins(22, 22, 22, 22)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)

        self.api_key_edit = QLineEdit(self.config_model.api_key)
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.base_url_edit = QLineEdit(self.config_model.base_url)
        self.model_edit = QLineEdit(self.config_model.model)
        self.settings_output_dir_edit = QLineEdit(self.config_model.output_dir)
        self.max_concurrency_spin = QSpinBox()
        self.max_concurrency_spin.setRange(1, 10)
        self.max_concurrency_spin.setValue(self.config_model.max_concurrent_tasks)
        self.max_concurrency_spin.setSuffix(" 条")
        self.failover_check = QCheckBox("接口异常时自动切换")
        self.failover_check.setChecked(self.config_model.failover_enabled)

        self._form_row(form, 0, "API Key", self.api_key_edit)
        self._form_row(form, 1, "Base URL", self.base_url_edit)
        self._form_row(form, 2, "模型", self.model_edit)
        self._form_row(form, 3, "默认输出目录", self.settings_output_dir_edit)
        self._form_row(form, 4, "同时生成数量", self.max_concurrency_spin)
        form.addWidget(self.failover_check, 5, 1)
        form.setColumnStretch(1, 1)

        actions = QHBoxLayout()
        save_button = QPushButton("保存设置")
        save_button.setObjectName("PrimarySmallButton")
        save_button.clicked.connect(self._save_settings)
        choose_button = QPushButton("选择输出目录")
        choose_button.setObjectName("GhostButton")
        choose_button.clicked.connect(self._choose_settings_output_dir)
        self.connectivity_button = QPushButton("测试连通性")
        self.connectivity_button.setObjectName("GhostButton")
        self.connectivity_button.clicked.connect(self._start_connectivity_test)
        actions.addWidget(save_button)
        actions.addWidget(choose_button)
        actions.addWidget(self.connectivity_button)
        actions.addStretch(1)
        self.settings_status_label = QLabel("")
        self.settings_status_label.setObjectName("MutedLabel")
        actions.addWidget(self.settings_status_label)
        form.addLayout(actions, 6, 0, 1, 2)

        layout.addWidget(card)
        layout.addItem(QSpacerItem(1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding))
        self._replace_page(page)

    def _replace_page(self, page: QWidget) -> None:
        self._sync_rows_from_widgets()
        self.row_widgets = {}
        while self.stack.count():
            old = self.stack.widget(0)
            self.stack.removeWidget(old)
            old.deleteLater()
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    def _section_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("CardTitle")
        return label

    def _form_row(self, layout: QGridLayout, row: int, label: str, widget: QWidget) -> None:
        layout.addWidget(self._field_label(label), row, 0)
        layout.addWidget(widget, row, 1)

    def _ensure_clone_items(self) -> None:
        if self.clone_items:
            return
        texts = self._split_lines(self._load_default_script_text()) or [""]
        for text in texts:
            self.clone_items.append(self._new_clone_item(text=text))

    def _new_clone_item(self, text: str = "", after_id: int | None = None) -> CloneItem:
        item = CloneItem(
            item_id=self.next_item_id,
            text=text,
            profile_name=self.config_model.selected_voice_profile,
        )
        self.next_item_id += 1
        if after_id is None:
            return item
        for index, existing in enumerate(self.clone_items):
            if existing.item_id == after_id:
                self.clone_items.insert(index + 1, item)
                return item
        self.clone_items.append(item)
        return item

    def _render_clone_rows(self) -> None:
        if not hasattr(self, "rows_layout"):
            return
        self._sync_rows_from_widgets()
        self.row_widgets = {}
        while self.rows_layout.count():
            child = self.rows_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()
        profile_names = self._profile_names()
        for index, item in enumerate(self.clone_items, start=1):
            row = RowWidget(
                item,
                index,
                profile_names,
                is_player_active=item.item_id == self.active_player_item_id,
            )
            row.generate_requested.connect(self._start_generate_item)
            row.play_requested.connect(self._play_item)
            row.pause_requested.connect(self._pause_item_playback)
            row.add_requested.connect(self._add_clone_row)
            row.delete_requested.connect(self._delete_clone_row)
            row.speed_changed.connect(self._restart_audio_with_speed)
            self.rows_layout.addWidget(row)
            self.row_widgets[item.item_id] = row
        self.rows_layout.addStretch(1)

    def _sync_rows_from_widgets(self) -> None:
        valid_rows: dict[int, RowWidget] = {}
        for item_id, row in list(self.row_widgets.items()):
            try:
                if row.snapshot():
                    valid_rows[item_id] = row
            except RuntimeError:
                continue
        self.row_widgets = valid_rows

    def _add_clone_row(self, after_id: int | None = None) -> None:
        self._sync_rows_from_widgets()
        if after_id is None:
            self.clone_items.append(self._new_clone_item())
        else:
            self._new_clone_item(after_id=after_id)
        self._render_clone_rows()

    def _delete_clone_row(self, item_id: int) -> None:
        if len(self.clone_items) <= 1:
            self._set_status("至少保留一行文案")
            return
        self.clone_items = [item for item in self.clone_items if item.item_id != item_id]
        if self.active_player_item_id == item_id:
            self._stop_audio_playback()
        self._render_clone_rows()

    def _import_script_text(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入文案",
            str(Path.cwd()),
            "Text Files (*.txt);;All Files (*)",
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        lines = self._split_lines(text)
        if not lines:
            self._set_status("导入文件没有可用文案")
            return
        self.clone_items = [self._new_clone_item(text=line) for line in lines]
        self._render_clone_rows()

    def _load_default_script_text(self) -> str:
        path = Path("文案.txt")
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _split_lines(self, text: str) -> list[str]:
        return [line.strip() for line in text.splitlines() if line.strip()]

    def _choose_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "选择输出目录", str(self._resolve_output_dir())
        )
        if directory:
            self.output_dir_edit.setText(directory)
            self.config_model.output_dir = directory

    def _choose_settings_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "选择输出目录", str(self._resolve_output_dir())
        )
        if directory:
            self.settings_output_dir_edit.setText(directory)

    def _resolve_output_dir(self) -> Path:
        raw = self.config_model.output_dir
        if self._widget_is_alive("output_dir_edit"):
            raw = self.output_dir_edit.text().strip() or raw
        path = Path(raw or "outputs")
        if not path.is_absolute():
            path = Path.cwd() / path
        return path

    def _start_generate_all(self) -> None:
        self._sync_rows_from_widgets()
        try:
            specs = self._build_generate_specs(
                [item for item in self.clone_items if item.item_id not in self.running_item_ids]
            )
        except ValueError as exc:
            self._set_status(str(exc))
            QMessageBox.warning(self, "无法生成", str(exc))
            return
        self._run_generate_specs(specs, "正在批量生成...")

    def _start_generate_item(self, item_id: int) -> None:
        self._sync_rows_from_widgets()
        item = self._find_item(item_id)
        if item is None:
            return
        if item_id in self.running_item_ids:
            self._set_status("当前行正在生成中")
            return
        try:
            specs = self._build_generate_specs([item])
        except ValueError as exc:
            self._set_status(str(exc))
            QMessageBox.warning(self, "无法生成", str(exc))
            return
        self._run_generate_specs(specs, "正在生成当前行...")

    def _build_generate_specs(self, items: list[CloneItem]) -> list[GenerateSpec]:
        self._save_config_from_visible_ui()
        api_key = self.config_model.api_key.strip()
        if not api_key:
            raise ValueError("API Key 缺失：请先在设置中填写 API Key，并点击保存设置。")
        output_format = self._normalize_output_format(self.config_model.output_format)
        output_dir = self._resolve_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)

        specs: list[GenerateSpec] = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        for index, item in enumerate(self.clone_items, start=1):
            if item not in items:
                continue
            text = item.text.strip()
            if not text:
                continue
            profile = self._find_profile(item.profile_name) or self._selected_or_first_profile()
            if profile is None:
                raise ValueError("请先在音色库中添加音色。")
            if not profile.prompt_audio_url.strip():
                raise ValueError(
                    f"音色“{profile.name}”缺少音色参考 URL：请填写公网可访问的 mp3/wav 链接。"
                )
            if not profile.emo_audio_prompt_url.strip():
                raise ValueError(
                    f"音色“{profile.name}”缺少情绪参考 URL：请填写公网可访问的 mp3/wav 链接。"
                )
            text_prefix = self._filename_text_prefix(text)
            filename = f"voice_{timestamp}_{index:02d}_{text_prefix}.{output_format}"
            output_path = output_dir / filename
            request = GiteeTTSRequest(
                api_key=api_key,
                base_url=self.config_model.base_url,
                model=self.config_model.model,
                input_text=text,
                output_path=output_path,
                voice=profile.voice.strip() or "alloy",
                prompt_audio_url=profile.prompt_audio_url.strip(),
                emo_audio_prompt_url=profile.emo_audio_prompt_url.strip(),
                prompt_text=profile.prompt_text.strip(),
                emo_alpha=profile.emo_alpha,
                failover_enabled=self.config_model.failover_enabled,
            )
            specs.append(
                GenerateSpec(
                    item_id=item.item_id,
                    index=index,
                    text=text,
                    output_path=output_path,
                    output_format=output_format,
                    request=request,
                )
            )
        if not specs:
            raise ValueError("请至少填写一行文案。")
        return specs

    def _run_generate_specs(self, specs: list[GenerateSpec], status: str) -> None:
        max_concurrency = max(1, min(10, self.config_model.max_concurrent_tasks))

        async def job(progress: Callable[[object], None]) -> list[GenerateOutcome]:
            semaphore = asyncio.Semaphore(max_concurrency)

            async def run_one(spec: GenerateSpec) -> GenerateOutcome:
                async with semaphore:
                    return await generate_one(spec)

            async def generate_one(spec: GenerateSpec) -> GenerateOutcome:
                progress(("item_status", spec.item_id, "生成中"))
                await asyncio.to_thread(
                    write_task_log,
                    "started",
                    item_id=spec.item_id,
                    index=spec.index,
                    text=spec.text,
                    output_path=spec.output_path,
                    output_format=spec.output_format,
                )
                try:
                    output = await self._generate_spec(spec)
                except BaseException as exc:  # noqa: BLE001 - keep other rows running
                    message = str(exc)
                    await asyncio.to_thread(
                        write_task_log,
                        "failed",
                        item_id=spec.item_id,
                        index=spec.index,
                        error=message,
                    )
                    progress(("item_failed", spec.item_id, message))
                    return GenerateOutcome(item_id=spec.item_id, index=spec.index, error=message)
                await asyncio.to_thread(
                    write_task_log,
                    "finished",
                    item_id=spec.item_id,
                    index=spec.index,
                    output_path=output,
                )
                progress(("item_done", spec.item_id, output))
                return GenerateOutcome(
                    item_id=spec.item_id,
                    index=spec.index,
                    output_path=output,
                )

            tasks = [asyncio.create_task(run_one(spec)) for spec in specs]
            try:
                return await asyncio.gather(*tasks)
            except BaseException:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise

        item_ids = {spec.item_id for spec in specs}
        self.running_item_ids.update(item_ids)
        self._set_busy(True, status)
        worker = AsyncJob(job)
        worker.progress.connect(self._handle_worker_progress)
        worker.succeeded.connect(self._generate_success)
        worker.failed.connect(self._generate_failed)
        worker.finished.connect(lambda ids=item_ids, job=worker: self._generate_job_finished(ids, job))
        self.current_jobs.append(worker)
        worker.start()

    async def _generate_spec(self, spec: GenerateSpec) -> Path:
        return await create_speech(spec.request)

    def _handle_worker_progress(self, payload: object) -> None:
        if not isinstance(payload, tuple):
            return
        kind = payload[0]
        if kind == "item_status":
            item_id = int(payload[1])
            status = str(payload[2])
            item = self._find_item(item_id)
            if item is not None:
                item.status = status
            row = self.row_widgets.get(item_id)
            if row is not None:
                row.set_status(status)
        elif kind == "item_done":
            item_id = int(payload[1])
            output = Path(payload[2])
            item = self._find_item(item_id)
            if item is not None:
                item.output_path = output
                item.status = "已生成"
            row = self.row_widgets.get(item_id)
            if row is not None:
                row.item.output_path = output
                row.set_status("已生成")
                row.generate_button.setText("重新生成")
        elif kind == "item_failed":
            item_id = int(payload[1])
            message = str(payload[2])
            item = self._find_item(item_id)
            if item is not None:
                item.status = "生成失败"
            row = self.row_widgets.get(item_id)
            if row is not None:
                row.set_status("生成失败")
            self._set_status(f"有文案生成失败：{message[:80]}")

    def _generate_success(self, outcomes: list[GenerateOutcome]) -> None:
        succeeded = [outcome for outcome in outcomes if outcome.ok]
        failed = [outcome for outcome in outcomes if not outcome.ok]
        status = f"已生成 {len(succeeded)} 个文件"
        if failed:
            status += f"，失败 {len(failed)} 条"
        self._set_busy(False, status)
        self._render_clone_rows()
        paths = "\n".join(
            str(outcome.output_path) for outcome in succeeded[:8] if outcome.output_path
        )
        if len(succeeded) > 8:
            paths += f"\n... 其余 {len(succeeded) - 8} 个文件已保存到输出目录"
        if failed:
            failures = "\n".join(
                f"第 {outcome.index} 条：{outcome.error}" for outcome in failed[:5]
            )
            if len(failed) > 5:
                failures += f"\n... 其余 {len(failed) - 5} 条失败请查看日志"
            message = (
                f"成功 {len(succeeded)} 条，失败 {len(failed)} 条。\n"
                f"\n失败原因：\n{failures}\n\n"
                f"任务日志：{task_log_path()}"
            )
            if paths:
                message += f"\n\n已保存：\n{paths}"
            QMessageBox.warning(self, "生成完成但有失败", message)
            return
        QMessageBox.information(self, "生成完成", f"音频已保存：\n{paths}")

    def _generate_failed(self, exc: BaseException) -> None:
        self._set_busy(False, "生成失败")
        QMessageBox.critical(self, "生成失败", str(exc))

    def _generate_job_finished(self, item_ids: set[int], worker: AsyncJob) -> None:
        self.running_item_ids.difference_update(item_ids)
        if worker in self.current_jobs:
            self.current_jobs.remove(worker)
        if not self.running_item_ids:
            self._set_busy(False, "准备就绪")

    def _set_busy(self, busy: bool, status: str) -> None:
        self._set_status(status)
        if hasattr(self, "generate_all_button"):
            self.generate_all_button.setDisabled(False)
        if hasattr(self, "busy_progress"):
            self.busy_progress.setRange(0, 0 if busy else 1)
            self.busy_progress.setValue(0)

    def _set_status(self, status: str) -> None:
        if hasattr(self, "status_label"):
            self.status_label.setText(status)

    def _open_output_dir(self) -> None:
        directory = self._resolve_output_dir()
        directory.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(str(directory))
        else:
            QMessageBox.information(self, "输出目录", str(directory))

    def _play_item(self, item_id: int) -> None:
        self._sync_rows_from_widgets()
        item = self._find_item(item_id)
        if item is None or item.output_path is None:
            QMessageBox.information(self, "播放", "当前行还没有生成音频。")
            return
        if not item.output_path.exists():
            QMessageBox.information(self, "播放", "音频文件不存在，请重新生成。")
            return
        if (
            self.active_player_item_id == item_id
            and self.media_player.playbackState() == QMediaPlayer.PlaybackState.PausedState
        ):
            self.media_player.play()
            return
        self._start_audio_playback(item, speed=1.0)

    def _pause_item_playback(self, item_id: int) -> None:
        if self.active_player_item_id != item_id:
            return
        self.media_player.pause()

    def _start_audio_playback(self, item: CloneItem, speed: float) -> None:
        if item.output_path is None:
            return

        self._stop_audio_process_only()
        self.active_player_item_id = item.item_id
        self.player_speed = speed
        self._render_clone_rows()

        row = self.row_widgets.get(item.item_id)
        if row is not None:
            row.speed_combo.setCurrentText(f"{speed:g}x".replace("1x", "1x"))

        self.media_player.setSource(QUrl.fromLocalFile(str(item.output_path)))
        self.media_player.setPlaybackRate(speed)
        self.media_player.play()

    def _restart_audio_with_speed(self, item_id: int, speed_text: str) -> None:
        if self.active_player_item_id != item_id:
            return
        try:
            speed = float(speed_text.rstrip("x"))
        except ValueError:
            speed = 1.0
        self.player_speed = speed
        self.media_player.setPlaybackRate(speed)

    def _on_player_position_changed(self, position_ms: int) -> None:
        self._set_player_progress(position_ms)

    def _on_player_duration_changed(self, duration_ms: int) -> None:
        self.player_duration_ms = max(0, duration_ms)
        self._set_player_progress(self.media_player.position())

    def _on_player_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.StoppedState and self.active_player_item_id is not None:
            self._set_player_progress(self.player_duration_ms)

    def _set_player_progress(self, current_ms: int) -> None:
        row = self.row_widgets.get(self.active_player_item_id or -1)
        if row is None:
            return
        duration = max(self.player_duration_ms, 1)
        row.player_progress.setValue(int((max(0, current_ms) / duration) * 1000))
        row.player_time.setText(
            f"{self._format_seconds(current_ms / 1000)} / {self._format_seconds(self.player_duration_ms / 1000)}"
        )

    def _stop_audio_playback(self) -> None:
        self._stop_audio_process_only()
        self.active_player_item_id = None
        self.player_duration_ms = 0
        self._render_clone_rows()

    def _stop_audio_process_only(self) -> None:
        self.media_player.stop()

    def _format_seconds(self, seconds: float) -> str:
        seconds = max(0, int(seconds))
        minutes, remainder = divmod(seconds, 60)
        return f"{minutes}:{remainder:02d}"

    def _refresh_profile_list(self) -> None:
        if not hasattr(self, "profile_list"):
            return
        self.profile_list.clear()
        active = self.config_model.selected_voice_profile
        for profile in self.config_model.voice_profiles:
            item = QListWidgetItem(profile.name)
            self.profile_list.addItem(item)
            if profile.name == active:
                self.profile_list.setCurrentItem(item)

    def _load_selected_profile(self) -> None:
        if not hasattr(self, "profile_list"):
            return
        item = self.profile_list.currentItem()
        if item is None:
            return
        self.config_model.selected_voice_profile = item.text()
        self._load_profile_into_form(self._find_profile(item.text()))

    def _load_profile_into_form(self, profile: VoiceProfile | None) -> None:
        if not hasattr(self, "profile_name_edit"):
            return
        if profile is None:
            profile = VoiceProfile(name="")
        self.profile_name_edit.setText(profile.name)
        self.profile_voice_edit.setText(profile.voice)
        self.profile_prompt_audio_edit.setText(profile.prompt_audio_url)
        self.profile_emo_audio_edit.setText(profile.emo_audio_prompt_url)
        self.profile_emo_alpha_edit.setText(str(profile.emo_alpha))
        self.profile_prompt_text_edit.setPlainText(profile.prompt_text)

    def _new_profile(self) -> None:
        base = "新音色"
        existing = set(self._profile_names())
        name = base
        index = 2
        while name in existing:
            name = f"{base}{index}"
            index += 1
        profile = VoiceProfile(name=name)
        self.config_model.voice_profiles.append(profile)
        self.config_model.selected_voice_profile = name
        save_config(self.config_model)
        self._refresh_profile_list()
        self._load_profile_into_form(profile)
        self.profile_status_label.setText("已新增")

    def _profile_from_form(self) -> VoiceProfile:
        name = self.profile_name_edit.text().strip()
        if not name:
            raise ValueError("请填写音色名称。")
        try:
            emo_alpha = float(self.profile_emo_alpha_edit.text().strip() or "1")
        except ValueError as exc:
            raise ValueError("情绪强度需要是数字。") from exc
        return VoiceProfile(
            name=name,
            voice=self.profile_voice_edit.text().strip() or "alloy",
            prompt_audio_url=self.profile_prompt_audio_edit.text().strip(),
            emo_audio_prompt_url=self.profile_emo_audio_edit.text().strip(),
            prompt_text=self.profile_prompt_text_edit.toPlainText().strip(),
            emo_alpha=emo_alpha,
        )

    def _save_profile(self) -> None:
        try:
            profile = self._profile_from_form()
        except ValueError as exc:
            self.profile_status_label.setText(str(exc))
            return
        old_name = self.config_model.selected_voice_profile
        old_profile = self._find_profile(old_name)
        duplicate = self._find_profile(profile.name)
        if duplicate is not None and duplicate is not old_profile:
            self.profile_status_label.setText("音色名称已存在")
            return
        if old_profile is None:
            self.config_model.voice_profiles.append(profile)
        else:
            index = self.config_model.voice_profiles.index(old_profile)
            self.config_model.voice_profiles[index] = profile
        self.config_model.selected_voice_profile = profile.name
        save_config(self.config_model)
        self._refresh_profile_list()
        self.profile_status_label.setText("已保存")

    def _delete_profile(self) -> None:
        profile = self._find_profile(self.config_model.selected_voice_profile)
        if profile is None:
            return
        if len(self.config_model.voice_profiles) <= 1:
            self.profile_status_label.setText("至少保留一个音色")
            return
        if (
            QMessageBox.question(self, "删除音色", f"确定删除“{profile.name}”？")
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.config_model.voice_profiles.remove(profile)
        self.config_model.selected_voice_profile = self.config_model.voice_profiles[0].name
        save_config(self.config_model)
        self._refresh_profile_list()
        self._load_profile_into_form(self._selected_or_first_profile())
        self.profile_status_label.setText("已删除")

    def _use_profile(self) -> None:
        self._save_profile()
        self.profile_status_label.setText("已设为当前音色")

    def _save_settings(self) -> None:
        self._save_config_from_visible_ui()
        save_config(self.config_model)
        self.settings_status_label.setText("已保存")

    def _save_config_from_visible_ui(self) -> AppConfig:
        if self._widget_is_alive("api_key_edit"):
            self.config_model.api_key = self.api_key_edit.text().strip()
            self.config_model.base_url = self.base_url_edit.text().strip() or "https://ai.gitee.com/v1"
            self.config_model.model = self.model_edit.text().strip() or "IndexTTS-2"
            self.config_model.output_dir = self.settings_output_dir_edit.text().strip() or "outputs"
            self.config_model.max_concurrent_tasks = self.max_concurrency_spin.value()
            self.config_model.failover_enabled = self.failover_check.isChecked()
        if self._widget_is_alive("output_dir_edit"):
            self.config_model.output_dir = self.output_dir_edit.text().strip() or "outputs"
        if self._widget_is_alive("output_format_combo"):
            self.config_model.output_format = self._normalize_output_format(
                self.output_format_combo.currentText()
            )
        save_config(self.config_model)
        return self.config_model

    def _normalize_output_format(self, value: str) -> str:
        audio_format = value.strip().lower()
        if audio_format not in {"wav", "mp3"}:
            return "mp3"
        return audio_format

    def _filename_text_prefix(self, text: str) -> str:
        illegal_chars = set('<>:"/\\|?*')
        cleaned = "".join(
            char
            for char in text.strip()
            if char not in illegal_chars and not char.isspace()
        )
        cleaned = cleaned.strip(".")
        return (cleaned[:5] or "文案")

    def _widget_is_alive(self, name: str) -> bool:
        widget = getattr(self, name, None)
        return widget is not None and isValid(widget)

    def _start_connectivity_test(self) -> None:
        try:
            request = self._build_connectivity_request()
        except ValueError as exc:
            self.settings_status_label.setText(str(exc))
            return

        async def job(_progress: Callable[[object], None]) -> Path:
            output_path = await create_speech(request)
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass
            return output_path

        self.connectivity_button.setDisabled(True)
        self.settings_status_label.setText("正在测试连通性...")
        worker = AsyncJob(job)
        worker.succeeded.connect(lambda _result: self._connectivity_done(True, "连通正常"))
        worker.failed.connect(lambda exc: self._connectivity_done(False, f"连通失败：{exc}"))
        worker.finished.connect(lambda job=worker: self._job_finished(job))
        self.current_jobs.append(worker)
        worker.start()

    def _build_connectivity_request(self) -> GiteeTTSRequest:
        self._save_config_from_visible_ui()
        if not self.config_model.api_key.strip():
            raise ValueError("API Key 缺失：请先填写 API Key，并点击保存设置。")
        profile = self._selected_or_first_profile()
        if profile is None:
            raise ValueError("请先在音色库中添加音色。")
        if not profile.prompt_audio_url.strip():
            raise ValueError("测试音色缺少音色参考 URL：请填写公网可访问的 mp3/wav 链接。")
        if not profile.emo_audio_prompt_url.strip():
            raise ValueError("测试音色缺少情绪参考 URL：请填写公网可访问的 mp3/wav 链接。")
        temp_path = Path(tempfile.gettempdir()) / "voice_clone_connectivity_test.wav"
        return GiteeTTSRequest(
            api_key=self.config_model.api_key,
            base_url=self.config_model.base_url,
            model=self.config_model.model,
            input_text="连通性测试。",
            output_path=temp_path,
            voice=profile.voice.strip() or "alloy",
            prompt_audio_url=profile.prompt_audio_url.strip(),
            emo_audio_prompt_url=profile.emo_audio_prompt_url.strip(),
            prompt_text=profile.prompt_text.strip(),
            emo_alpha=profile.emo_alpha,
            failover_enabled=self.config_model.failover_enabled,
        )

    def _connectivity_done(self, ok: bool, message: str) -> None:
        self.connectivity_button.setDisabled(False)
        self.settings_status_label.setText(message if len(message) <= 60 else message[:57] + "...")
        if not ok:
            QMessageBox.warning(self, "连通性测试", message)

    def _profile_names(self) -> list[str]:
        return [profile.name for profile in self.config_model.voice_profiles]

    def _selected_or_first_profile(self) -> VoiceProfile | None:
        return self._find_profile(self.config_model.selected_voice_profile) or (
            self.config_model.voice_profiles[0] if self.config_model.voice_profiles else None
        )

    def _find_profile(self, name: str) -> VoiceProfile | None:
        for profile in self.config_model.voice_profiles:
            if profile.name == name:
                return profile
        return None

    def _find_item(self, item_id: int) -> CloneItem | None:
        for item in self.clone_items:
            if item.item_id == item_id:
                return item
        return None

    def closeEvent(self, event: Any) -> None:
        self._stop_audio_process_only()
        for worker in list(self.current_jobs):
            if worker.isRunning():
                worker.wait(1500)
        event.accept()

    def _job_finished(self, worker: AsyncJob) -> None:
        if worker in self.current_jobs:
            self.current_jobs.remove(worker)


def run_app() -> int:
    app = QApplication.instance() or QApplication([])
    window = VoiceCloneWindow()
    window.show()
    return app.exec()
