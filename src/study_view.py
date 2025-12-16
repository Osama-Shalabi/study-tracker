import base64
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QTimer, Qt, QRectF, QUrl, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QIcon, QAction, QFont, QIntValidator
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QApplication,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
    QSystemTrayIcon,
    QMenu,
    QAbstractItemView,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from .data_store import DataStore
from .theme import apply_panel_style, apply_primary_button, apply_secondary_button


def base_assets_path() -> Path:
    """Locate asset folder, supporting PyInstaller bundles."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


class TrayNotifier:
    """Simple system tray notifier for Windows (falls back silently elsewhere)."""

    def __init__(self):
        self.tray: Optional[QSystemTrayIcon] = None
        self.menu: Optional[QMenu] = None
        self.current_stop_cb = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon_path = base_assets_path() / "timer-notification.png"
        icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
        tray = QSystemTrayIcon(icon)
        tray.setIcon(icon)
        tray.setVisible(True)
        tray.messageClicked.connect(self._on_message_clicked)
        self.tray = tray

    def _on_message_clicked(self):
        if self.current_stop_cb:
            self.current_stop_cb()

    def show(self, title: str, message: str, stop_cb=None):
        if not self.tray:
            return
        self.current_stop_cb = stop_cb
        if stop_cb:
            menu = QMenu()
            act = QAction("Dismiss alarm")
            act.triggered.connect(stop_cb)
            menu.addAction(act)
            self.tray.setContextMenu(menu)
            self.menu = menu
        else:
            self.tray.setContextMenu(None)
            self.menu = None
        self.tray.showMessage(title, message, self.tray.icon(), 5000)


class TimerCircle(QWidget):
    def __init__(self):
        super().__init__()
        self.total_seconds = 1
        self.remaining_seconds = 1
        self.display_text = "00:00:00"
        self.setMinimumSize(220, 220)

    def update_state(self, total_seconds: int, remaining_seconds: int, text: str):
        self.total_seconds = max(1, total_seconds)
        self.remaining_seconds = max(0, remaining_seconds)
        self.display_text = text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        size = min(self.width(), self.height()) - 20
        rect = QRectF(
            (self.width() - size) / 2,
            (self.height() - size) / 2,
            size,
            size,
        )
        # background ring
        pen_bg = QPen(QColor(110, 120, 140, 120), 12)
        painter.setPen(pen_bg)
        painter.drawArc(rect, 0, 360 * 16)

        # progress
        progress = self.remaining_seconds / self.total_seconds
        pen_fg = QPen(QColor("#7ac7ff"), 12)
        painter.setPen(pen_fg)
        painter.drawArc(rect, -90 * 16, int(360 * 16 * progress))

        # text
        painter.setPen(QColor("#e7ecf4"))
        font = painter.font()
        # Scale font with widget size for readability
        size_hint = max(11, int(min(self.width(), self.height()) * 0.13))
        font.setPointSize(size_hint)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, self.display_text or "")


class TimerEditDialog(QDialog):
    def __init__(self, parent, hours: int, minutes: int, seconds: int):
        super().__init__(parent)
        self.setWindowTitle("Edit timer")
        self.setModal(True)

        # Ensure the dialog paints its own background
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            "QDialog { background-color:#0f1624; border:1px solid rgba(255,255,255,0.08); border-radius:12px; }"
            "QWidget { color:#e7ecf4; }"
        )
        self.pending_hours = hours
        self.pending_minutes = minutes
        self.pending_seconds = seconds
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Edit timer")
        title.setStyleSheet("color:#f3f6ff; font-size:18px; font-weight:700;")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        def arrow_btn(txt, cb):
            btn = QPushButton(txt)
            btn.setFixedSize(32, 26)
            btn.setStyleSheet(
                "QPushButton { background:rgba(255,255,255,0.06); color:#e7ecf4; border:1px solid rgba(255,255,255,0.12); border-radius:8px; }"
                "QPushButton:hover { border-color:#7ac7ff; color:#7ac7ff; }"
            )
            btn.clicked.connect(cb)
            return btn

        top_row = QHBoxLayout()
        top_row.addWidget(arrow_btn("▲", lambda: self._nudge("h", 1)), alignment=Qt.AlignHCenter)
        top_row.addWidget(arrow_btn("▲", lambda: self._nudge("m", 1)), alignment=Qt.AlignHCenter)
        top_row.addWidget(arrow_btn("▲", lambda: self._nudge("s", 1)), alignment=Qt.AlignHCenter)
        layout.addLayout(top_row)

        center_box = QWidget()
        center_box.setStyleSheet(
            """
            QWidget {
              background: rgba(255,255,255,0.04);
              border: 1px solid rgba(255,255,255,0.12);
              border-radius: 10px;
              padding: 10px;
              border-bottom: 3px solid #7ac7ff;
            }
            """
        )
        digits_row = QHBoxLayout(center_box)
        digits_row.setContentsMargins(12, 8, 12, 8)
        digits_row.setSpacing(8)
        validator = QIntValidator(0, 99, self)
        self.hour_edit = QLineEdit()
        self.min_edit = QLineEdit()
        self.sec_edit = QLineEdit()
        for field, edit in (("h", self.hour_edit), ("m", self.min_edit), ("s", self.sec_edit)):
            edit.setValidator(validator)
            edit.setMaxLength(2)
            edit.setAlignment(Qt.AlignCenter)
            edit.setFixedWidth(58)
            edit.setStyleSheet(
                "QLineEdit { color:#f3f6ff; font-size:28px; font-weight:800; background: rgba(0,0,0,0.12);"
                "border:1px solid rgba(255,255,255,0.15); border-radius:10px; padding:6px; }"
                "QLineEdit:focus { border-color:#7ac7ff; background: rgba(122,199,255,0.10); }"
            )
            edit.editingFinished.connect(lambda f=field, e=edit: self._commit_field(f, e))
            digits_row.addWidget(edit, alignment=Qt.AlignHCenter)
            if edit != self.sec_edit:
                colon = QLabel(":")
                colon.setStyleSheet("color:#f3f6ff; font-size:28px; font-weight:800;")
                digits_row.addWidget(colon)
        layout.addWidget(center_box)

        bottom_row = QHBoxLayout()
        bottom_row.addWidget(arrow_btn("▼", lambda: self._nudge("h", -1)), alignment=Qt.AlignHCenter)
        bottom_row.addWidget(arrow_btn("▼", lambda: self._nudge("m", -1)), alignment=Qt.AlignHCenter)
        bottom_row.addWidget(arrow_btn("▼", lambda: self._nudge("s", -1)), alignment=Qt.AlignHCenter)
        layout.addLayout(bottom_row)

        buttons = QHBoxLayout()
        save_btn = QPushButton("💾 Save")
        apply_primary_button(save_btn)
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("✕ Cancel")
        apply_secondary_button(cancel_btn)
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

        self._refresh_labels()

    def _nudge(self, field: str, delta: int):
        if field == "h":
            self.pending_hours = max(0, min(23, self.pending_hours + delta))
        elif field == "m":
            self.pending_minutes = max(0, min(59, self.pending_minutes + delta))
        elif field == "s":
            self.pending_seconds = max(0, min(59, self.pending_seconds + delta))
        self._refresh_labels()

    def _refresh_labels(self):
        self.hour_edit.blockSignals(True)
        self.min_edit.blockSignals(True)
        self.sec_edit.blockSignals(True)
        self.hour_edit.setText(f"{self.pending_hours:02d}")
        self.min_edit.setText(f"{self.pending_minutes:02d}")
        self.sec_edit.setText(f"{self.pending_seconds:02d}")
        self.hour_edit.blockSignals(False)
        self.min_edit.blockSignals(False)
        self.sec_edit.blockSignals(False)

    def result_time(self):
        return self.pending_hours, self.pending_minutes, self.pending_seconds
    
    def _commit_field(self, field: str, edit: QLineEdit):
        text = edit.text().strip()
        val = int(text) if text.isdigit() else 0
        if field == "h":
            val = max(0, min(23, val))
            self.pending_hours = val
        elif field == "m":
            val = max(0, min(59, val))
            self.pending_minutes = val
        elif field == "s":
            val = max(0, min(59, val))
            self.pending_seconds = val
        self._refresh_labels()


class StopwatchWidget(QWidget):
    def __init__(self, on_finish):
        super().__init__()
        self.on_finish = on_finish
        self.elapsed_seconds = 0
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.display = QLabel(self._format_time())
        self.display.setStyleSheet("color:#7ac7ff; font-size:18px; font-weight:700;")
        self.display.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.display)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.start_btn = QPushButton("▶")
        self.start_btn.setFixedSize(46, 42)
        self.start_btn.clicked.connect(self.start)
        apply_primary_button(self.start_btn)
        self.start_btn.setToolTip("Start stopwatch")
        btns.addWidget(self.start_btn)

        self.pause_btn = QPushButton("⏸")
        self.pause_btn.setFixedSize(46, 42)
        apply_secondary_button(self.pause_btn)
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.pause_btn.setToolTip("Pause/Resume")
        btns.addWidget(self.pause_btn)

        self.reset_btn = QPushButton("↺")
        self.reset_btn.setFixedSize(46, 42)
        apply_secondary_button(self.reset_btn)
        self.reset_btn.clicked.connect(self.reset)
        self.reset_btn.setToolTip("Reset stopwatch")
        btns.addWidget(self.reset_btn)

        self.finish_btn = QPushButton("Finish")
        apply_primary_button(self.finish_btn)
        self.finish_btn.clicked.connect(self.finish)
        btns.addWidget(self.finish_btn)

        layout.addLayout(btns)

    def _format_time(self):
        hrs = self.elapsed_seconds // 3600
        mins = (self.elapsed_seconds % 3600) // 60
        secs = self.elapsed_seconds % 60
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"

    def start(self):
        if self.timer.isActive():
            return
        self.timer.start()

    def toggle_pause(self):
        if self.timer.isActive():
            self.timer.stop()
            self.pause_btn.setText("▶")
        else:
            self.timer.start()
            self.pause_btn.setText("⏸")

    def reset(self):
        self.timer.stop()
        self.elapsed_seconds = 0
        self.display.setText(self._format_time())
        self.pause_btn.setText("⏸")

    def finish(self):
        self.timer.stop()
        secs = self.elapsed_seconds
        self.elapsed_seconds = 0
        self.display.setText(self._format_time())
        self.pause_btn.setText("⏸")
        if secs > 0:
            self.on_finish(secs)

    def _tick(self):
        self.elapsed_seconds += 1
        self.display.setText(self._format_time())


class CountdownWidget(QWidget):
    def __init__(self, label: str, default_minutes: int, on_complete, notify_cb=None):
        super().__init__()
        self.total_seconds = max(1, default_minutes * 60)
        self.remaining_seconds = self.total_seconds
        self.on_complete = on_complete
        self.notify_cb = notify_cb
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)

        self.label = label or f"{default_minutes} min"
        self.hours = default_minutes // 60
        self.minutes = default_minutes % 60
        self.seconds = 0
        self.pending_hours = self.hours
        self.pending_minutes = self.minutes
        self.pending_seconds = self.seconds

        self.circle = TimerCircle()
        self.circle.update_state(self.total_seconds, self.remaining_seconds, self._format_time())
        self.alarm_player: Optional[QMediaPlayer] = None
        self.alarm_output: Optional[QAudioOutput] = None
        self._load_alarm_sound()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addWidget(self.circle, alignment=Qt.AlignHCenter)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        controls.addStretch()
        self.start_btn = QPushButton("▶")
        self.start_btn.setFixedSize(52, 48)
        self.start_btn.setStyleSheet(
            "QPushButton { background:qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7ac7ff, stop:1 #c792ff);"
            "color:#0a0f1a; font-weight:800; border:none; border-radius:14px; padding:10px; }"
            "QPushButton:hover { background:qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8ed2ff, stop:1 #d4b3ff); }"
        )
        self.start_btn.clicked.connect(self.start)
        self.start_btn.setToolTip("Start timer")
        controls.addWidget(self.start_btn)

        self.pause_btn = QPushButton("⏸")
        self.pause_btn.setFixedSize(52, 48)
        self.pause_btn.setStyleSheet(
            "QPushButton { background:rgba(255,255,255,0.07); color:#e7ecf4; border:1px solid rgba(122,199,255,0.28); border-radius:24px; }"
            "QPushButton:hover { border-color:#7ac7ff; color:#7ac7ff; }"
        )
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.pause_btn.setToolTip("Pause/Resume")
        controls.addWidget(self.pause_btn)

        self.reset_btn = QPushButton("↺")
        self.reset_btn.setFixedSize(52, 48)
        self.reset_btn.setStyleSheet(
            "QPushButton { background:rgba(255,255,255,0.07); color:#e7ecf4; border:1px solid rgba(122,199,255,0.28); border-radius:24px; }"
            "QPushButton:hover { border-color:#7ac7ff; color:#7ac7ff; }"
        )
        self.reset_btn.clicked.connect(self.reset)
        self.reset_btn.setToolTip("Reset timer")
        controls.addWidget(self.reset_btn)

        edit_btn = QPushButton("✎")
        edit_btn.setFixedSize(46, 44)
        edit_btn.setStyleSheet(
            "QPushButton { background:rgba(255,255,255,0.06); color:#e7ecf4; border:1px solid rgba(255,255,255,0.12); border-radius:12px; }"
            "QPushButton:hover { border-color:#7ac7ff; color:#7ac7ff; }"
        )
        edit_btn.clicked.connect(self.open_editor)
        edit_btn.setToolTip("Edit duration")
        controls.addWidget(edit_btn)
        controls.addStretch()
        root.addLayout(controls)

    def _arrow_button(self, text: str, handler):
        btn = QPushButton(text)
        btn.setFixedSize(36, 28)
        btn.setStyleSheet(
            "QPushButton { background:rgba(255,255,255,0.06); color:#e7ecf4; border:1px solid rgba(255,255,255,0.12); border-radius:8px; }"
            "QPushButton:hover { border-color:#7ac7ff; color:#7ac7ff; }"
        )
        btn.clicked.connect(handler)
        return btn

    def _format_time(self):
        hrs = self.remaining_seconds // 3600
        mins = (self.remaining_seconds % 3600) // 60
        secs = self.remaining_seconds % 60
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"

    def _get_active_total_seconds(self) -> int:
        return self.hours * 3600 + self.minutes * 60 + self.seconds

    def _refresh_circle(self):
        self.circle.update_state(self.total_seconds, self.remaining_seconds, self._format_time())

    def open_editor(self):
        dialog = TimerEditDialog(self, self.hours, self.minutes, self.seconds)
        if dialog.exec() == QDialog.Accepted:
            h, m, s = dialog.result_time()
            total = h * 3600 + m * 60 + s
            if total > 0:
                self.hours = h
                self.minutes = m
                self.seconds = s
                self.total_seconds = total
                self.remaining_seconds = total
                self.total_minutes = max(1, total // 60)
                self.timer.stop()
                self._paused = False
                self.pause_btn.setText("⏸")
                self._refresh_circle()

    def start(self):
        total_seconds = self._get_active_total_seconds()
        if total_seconds <= 0 or self.timer.isActive():
            return
        self.remaining_seconds = total_seconds
        self.total_seconds = total_seconds
        self.total_minutes = max(1, total_seconds // 60)
        self._refresh_circle()
        self.timer.start()
        self._paused = False
        self.pause_btn.setText("⏸")

    def reset(self):
        self.timer.stop()
        total_seconds = self._get_active_total_seconds()
        self.remaining_seconds = total_seconds
        self._refresh_circle()
        self._paused = False
        self.pause_btn.setText("⏸")

    def toggle_pause(self):
        if not self.timer.isActive() and not self._paused:
            return
        if self.timer.isActive():
            self.timer.stop()
            self._paused = True
            self.pause_btn.setText("▶")
        else:
            self.timer.start()
            self._paused = False
            self.pause_btn.setText("⏸")

    def _tick(self):
        self.remaining_seconds -= 1
        if self.remaining_seconds <= 0:
            self.timer.stop()
            self.remaining_seconds = 0
            self._refresh_circle()
            self.on_complete(self.total_minutes)
            self._play_alarm()
            if self.notify_cb:
                self.notify_cb(self.label, self.total_minutes, self.stop_alarm)
            return
        self._refresh_circle()

    def _load_alarm_sound(self):
        try:
            base_path = base_assets_path()
            sound_path = base_path / "Video Project.m4a"
            if not sound_path.exists():
                self.alarm_player = None
                return
            audio_output = QAudioOutput()
            player = QMediaPlayer()
            player.setAudioOutput(audio_output)
            player.setSource(QUrl.fromLocalFile(str(sound_path)))
            audio_output.setVolume(0.4)
            player.setLoops(1)
            self.alarm_player = player
            self.alarm_output = audio_output
        except Exception:
            self.alarm_player = None

    def _play_alarm(self):
        if self.alarm_player:
            self.alarm_player.stop()
            self.alarm_player.setPosition(0)
            self.alarm_player.play()

    def stop_alarm(self):
        if self.alarm_player:
            self.alarm_player.stop()


class CircularProgress(QWidget):
    def __init__(self):
        super().__init__()
        self._value = 0
        self.setMinimumSize(140, 140)

    def set_value(self, value: int):
        self._value = max(0, min(100, value))
        self.update()

    def paintEvent(self, event):
        radius_padding = 10
        size = min(self.width(), self.height()) - radius_padding * 2
        rect = QRectF(
            (self.width() - size) / 2,
            (self.height() - size) / 2,
            size,
            size,
        )
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # background ring
        pen_bg = QPen(QColor(255, 255, 255, 40), 12)
        painter.setPen(pen_bg)
        painter.drawArc(rect, 0, 360 * 16)

        # progress arc
        pen_fg = QPen(QColor("#7ac7ff"), 12)
        painter.setPen(pen_fg)
        painter.drawArc(rect, -90 * 16, int(360 * 16 * (self._value / 100)))

        # text
        painter.setPen(QColor("#e7ecf4"))
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignCenter, f"{self._value}%")


class ChapterListWidget(QListWidget):
    """List widget that supports internal drag-and-drop reorder and emits new order."""

    orderChanged = Signal(list)

    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def dropEvent(self, event):
        super().dropEvent(event)
        ordered_ids: List[int] = []
        for i in range(self.count()):
            cid = self.item(i).data(Qt.UserRole)
            if cid is not None:
                ordered_ids.append(int(cid))
        self.orderChanged.emit(ordered_ids)


class StudyView(QWidget):
    def __init__(self, store: DataStore, to_home: Callable[[], None], to_subjects: Callable[[], None]):
        super().__init__()
        self.store = store
        self.to_home = to_home
        self.to_subjects = to_subjects
        self.subject_id: Optional[int] = None
        self.done_sound: Optional[QMediaPlayer] = None
        self.done_audio_output: Optional[QAudioOutput] = None
        self.notifier = TrayNotifier()

        self.chapter_list = ChapterListWidget()
        self.note_editor = QTextEdit()
        self.note_editor.setPlaceholderText("Enter notes for the selected chapter...")
        self.note_editor.textChanged.connect(self._save_notes)
        self._editing_chapter_id: Optional[int] = None
        self._loading_chapters = False

        self.progress_indicator = CircularProgress()

        self.timer30 = CountdownWidget("30 min focus", 30, self._log_session, self._notify_timer_done)
        self.timer5 = CountdownWidget("5 min break", 5, lambda minutes: None, self._notify_timer_done)
        self.stopwatch = StopwatchWidget(self._log_stopwatch)

        self._ensure_done_sound()
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        header = QHBoxLayout()
        self.title = QLabel("Subject")
        self.title.setStyleSheet("color:#f3f6ff; font-size:20px; font-weight:700;")
        header.addWidget(self.title)
        header.addStretch()
        back_btn = QPushButton("← Subjects")
        apply_secondary_button(back_btn)
        back_btn.clicked.connect(self.to_subjects)
        home_btn = QPushButton("Home")
        apply_secondary_button(home_btn)
        home_btn.clicked.connect(self.to_home)
        header.addWidget(back_btn)
        header.addWidget(home_btn)
        root.addLayout(header)

        timers_panel = QWidget()
        apply_panel_style(timers_panel)
        timers_layout = QHBoxLayout(timers_panel)
        timers_layout.setContentsMargins(12, 12, 12, 12)
        timers_layout.addWidget(self.timer30)
        timers_layout.addWidget(self.timer5)
        timers_layout.addWidget(self.stopwatch)
        root.addWidget(timers_panel)

        body = QHBoxLayout()

        chapters_panel = QWidget()
        apply_panel_style(chapters_panel)
        chapters_layout = QVBoxLayout(chapters_panel)
        chapters_layout.setContentsMargins(12, 12, 12, 12)
        chapters_layout.addWidget(QLabel("Chapters"))

        self.chapter_list.itemSelectionChanged.connect(self._load_notes_for_selected)
        self.chapter_list.itemChanged.connect(self._toggle_done)
        self.chapter_list.orderChanged.connect(self._persist_order)
        self.chapter_list.setStyleSheet(
            """
            QListWidget { color:#f3f6ff; }
            QListWidget::item { color:#f3f6ff; padding:4px 6px; }
            QListWidget::item:selected { color:#f3f6ff; background: rgba(122,199,255,0.20); }
            QListWidget QLineEdit {
              color:#f3f6ff;
              background: #0c1422;
              border: 1px solid rgba(122,199,255,0.45);
              border-radius: 6px;
              padding:4px 6px;
              selection-background-color: rgba(122,199,255,0.35);
              selection-color:#0a0f1a;
            }
            """
        )
        chapters_layout.addWidget(self.chapter_list)

        add_row = QHBoxLayout()
        self.chapter_input = QLineEdit()
        self.chapter_input.setPlaceholderText("Add chapter title")
        self.chapter_input.returnPressed.connect(self._add_chapter)
        add_btn = QPushButton("Add")
        apply_primary_button(add_btn)
        add_btn.clicked.connect(self._add_chapter)
        delete_btn = QPushButton("Delete selected")
        apply_secondary_button(delete_btn)
        delete_btn.clicked.connect(self._delete_selected_chapter)
        add_row.addWidget(self.chapter_input)
        add_row.addWidget(add_btn)
        add_row.addWidget(delete_btn)
        chapters_layout.addLayout(add_row)

        body.addWidget(chapters_panel, stretch=1)

        notes_panel = QWidget()
        apply_panel_style(notes_panel)
        notes_layout = QVBoxLayout(notes_panel)
        notes_layout.setContentsMargins(12, 12, 12, 12)
        notes_layout.addWidget(QLabel("Notes for selected chapter"))
        notes_layout.addWidget(self.note_editor)
        progress_container = QVBoxLayout()
        progress_container.setSpacing(6)
        progress_label = QLabel("Progress")
        progress_label.setStyleSheet("color:#f3f6ff; font-weight:700;")
        progress_container.addWidget(progress_label, alignment=Qt.AlignHCenter)
        progress_container.addWidget(self.progress_indicator, alignment=Qt.AlignHCenter)
        notes_layout.addLayout(progress_container)
        body.addWidget(notes_panel, stretch=1)

        root.addLayout(body)

    def load_subject(self, subject_id: int):
        self.subject_id = subject_id
        subjects = {row["id"]: row for row in self.store.list_subjects()}
        subject = subjects.get(subject_id)
        self.title.setText(f"Studying: {subject['name']}" if subject else "Subject")
        self.refresh_chapters()

    def _log_session(self, minutes: int):
        if not self.subject_id:
            return
        self.store.log_session(self.subject_id, minutes, datetime.utcnow())

    def _log_stopwatch(self, seconds: int):
        if not self.subject_id:
            return
        minutes = max(1, math.ceil(seconds / 60))
        self.store.log_session(self.subject_id, minutes, datetime.utcnow())

    def _notify_timer_done(self, label: str, minutes: int, stop_cb):
        if not self.notifier:
            return
        message = f"{label} finished."
        if label.lower().find("break") != -1:
            message += " Break is over."
        else:
            message += f" Logged {minutes} min."
        self.notifier.show("Study Tracker", message, stop_cb)

    def refresh_chapters(self):
        self._loading_chapters = True
        self.chapter_list.blockSignals(True)
        self.chapter_list.clear()
        for row in self.store.list_chapters(self.subject_id):
            item = QListWidgetItem(row["title"])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEditable)
            item.setCheckState(Qt.Checked if row["done"] else Qt.Unchecked)
            item.setData(Qt.UserRole, row["id"])
            item.setForeground(QColor("#f3f6ff"))
            self.chapter_list.addItem(item)
        self.chapter_list.blockSignals(False)
        self.note_editor.clear()
        self._editing_chapter_id = None
        self._loading_chapters = False
        self._update_progress()

    def _add_chapter(self):
        title = self.chapter_input.text().strip()
        if not title or not self.subject_id:
            return
        self.store.add_chapter(self.subject_id, title)
        self.chapter_input.clear()
        self.refresh_chapters()

    def _toggle_done(self, item: QListWidgetItem):
        chapter_id = item.data(Qt.UserRole)
        done = item.checkState() == Qt.Checked
        self.store.toggle_chapter(chapter_id, done)
        if done:
            self._play_done_sound()
        self._update_progress()

    def _persist_order(self, ordered_ids: List[int]):
        if self._loading_chapters or not self.subject_id:
            return
        self.store.reorder_chapters(self.subject_id, ordered_ids)

    def _load_notes_for_selected(self):
        items = self.chapter_list.selectedItems()
        if not items:
            self.note_editor.clear()
            self._editing_chapter_id = None
            return
        item = items[0]
        chapter_id = item.data(Qt.UserRole)
        self._editing_chapter_id = chapter_id
        # fetch notes
        for row in self.store.list_chapters(self.subject_id):
            if row["id"] == chapter_id:
                self.note_editor.blockSignals(True)
                self.note_editor.setPlainText(row["notes"] or "")
                self.note_editor.blockSignals(False)
                break

    def _save_notes(self):
        if not self._editing_chapter_id:
            return
        notes = self.note_editor.toPlainText()
        self.store.update_notes(self._editing_chapter_id, notes)

    def _delete_selected_chapter(self):
        items = self.chapter_list.selectedItems()
        if not items:
            QMessageBox.information(self, "Select a chapter", "Please select a chapter to delete.")
            return
        item = items[0]
        chapter_id = item.data(Qt.UserRole)
        title = item.text()
        confirm = QMessageBox.question(
            self,
            "Delete chapter",
            f"Delete \"{title}\"?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.store.delete_chapter(chapter_id)
        self._editing_chapter_id = None
        self.refresh_chapters()

    def _update_progress(self):
        total = self.chapter_list.count()
        if total == 0:
            self.progress_indicator.set_value(0)
            return
        done = sum(1 for i in range(total) if self.chapter_list.item(i).checkState() == Qt.Checked)
        percent = int((done / total) * 100)
        self.progress_indicator.set_value(percent)

    def _ensure_done_sound(self):
        try:
            base_path = base_assets_path()
            sound_path = base_path / "11l-victory_beat-1749704521130-358766.mp3"
            if not sound_path.exists():
                self.done_sound = None
                return
            audio_output = QAudioOutput()
            player = QMediaPlayer()
            player.setAudioOutput(audio_output)
            player.setSource(QUrl.fromLocalFile(str(sound_path)))
            audio_output.setVolume(0.35)
            self.done_sound = player
            self.done_audio_output = audio_output
        except Exception:
            self.done_sound = None

    def _play_done_sound(self):
        if self.done_sound:
            self.done_sound.setPosition(0)
            self.done_sound.play()
        else:
            pass
