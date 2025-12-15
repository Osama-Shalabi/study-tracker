from datetime import datetime, timedelta
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from .data_store import DataStore
from .theme import apply_panel_style, apply_primary_button, apply_secondary_button


class HomeView(QWidget):
    def __init__(self, store: DataStore, to_subjects: Callable[[], None], to_home: Callable[[], None]):
        super().__init__()
        self.store = store
        self.to_subjects = to_subjects
        self.to_home = to_home

        self.day_label = QLabel()
        self.week_label = QLabel()
        self.prev_month_label = QLabel()

        self.figure = Figure(figsize=(5, 2.5), tight_layout=True, facecolor="#0f1116")
        self.canvas = FigureCanvas(self.figure)
        self.month_cards_layout: QVBoxLayout | None = None

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Study Dashboard")
        title_font = QFont("Inter", 22)
        title_font.setBold(True)
        title.setFont(title_font)
        header.addWidget(title, alignment=Qt.AlignLeft)
        header.addStretch()

        start_btn = QPushButton("Start studying")
        apply_primary_button(start_btn)
        start_btn.clicked.connect(self.to_subjects)
        header.addWidget(start_btn, alignment=Qt.AlignRight)

        root.addLayout(header)

        cards = QHBoxLayout()
        for title_text, label_widget, name_attr in (
            ("Today", self.day_label, "day_title_label"),
            ("This week", self.week_label, "week_title_label"),
        ):
            box = self._metric_card(title_text, label_widget, name_attr=name_attr)
            cards.addWidget(box)
        # Monthly stacked cards next to metrics
        month_panel = QWidget()
        apply_panel_style(month_panel)
        month_layout = QVBoxLayout(month_panel)
        month_layout.setContentsMargins(14, 12, 14, 12)
        month_layout.setSpacing(8)
        title = QLabel("Monthly totals")
        title.setStyleSheet("color:#f3f6ff; font-weight:700;")
        month_layout.addWidget(title)

        cards_container = QWidget()
        self.month_cards_layout = QVBoxLayout(cards_container)
        self.month_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.month_cards_layout.setSpacing(8)
        month_layout.addWidget(cards_container)

        cards.addWidget(month_panel, stretch=1)
        root.addLayout(cards)

        chart_panel = QWidget()
        apply_panel_style(chart_panel)
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(14, 12, 14, 12)
        chart_title = QLabel("Daily hours (last 7 days)")
        chart_title.setStyleSheet("color: #f3f6ff; font-weight: 700;")
        chart_layout.addWidget(chart_title)
        chart_layout.addWidget(self.canvas)

        root.addWidget(chart_panel)

    def _metric_card(self, title: str, label: QLabel, name_attr: str | None = None) -> QWidget:
        panel = QWidget()
        apply_panel_style(panel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        name = QLabel(title)
        if name_attr:
            setattr(self, name_attr, name)
        name_font = QFont("Inter", 18)
        name_font.setBold(True)
        name.setFont(name_font)
        name.setStyleSheet("color:#c3c9d6; letter-spacing:1px; text-transform:uppercase;")
        value_font = QFont("Inter", 16)
        value_font.setBold(True)
        label.setFont(value_font)
        label.setStyleSheet(
            "color:#f3f6ff; padding:60px 8px 6px 8px; border-radius:6px;"
        )
        label.setAlignment(Qt.AlignHCenter)
        layout.addWidget(name)
        layout.addWidget(label)
        return panel

    def refresh(self):
        stats = self.store.get_stats()
        now = datetime.now()
        day_start = datetime(now.year, now.month, now.day)
        week_start = day_start - timedelta(days=(day_start.weekday() + 1) % 7)
        week_end = week_start + timedelta(days=6)

        def fmt_minutes(minutes: int) -> str:
            return f"{minutes} min"

        today_text = now.strftime("%d %b")
        week_range = f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b')}"
        month_name = now.strftime("%B")

        if hasattr(self, "day_title_label"):
            self.day_title_label.setText(f"{today_text} Today")
        self.day_label.setText(f"{fmt_minutes(stats['day'])}")
        if hasattr(self, "week_title_label"):
            self.week_title_label.setText(f"This week ({week_range})")
        self.week_label.setText(f"{fmt_minutes(stats['week'])}")
        self._render_month_cards(stats.get("month_cards", []))
        # Update chart
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        labels = [l for l, _ in stats["bars"]]
        # Cap daily minutes at 600 (10 hours) for display consistency
        values = [min(v, 600) for _, v in stats["bars"]]
        bars = ax.bar(labels, values, color="#7ac7ff")
        ax.set_facecolor("#0a0f1a")
        ax.tick_params(colors="#c3c9d6")
        ax.spines["bottom"].set_color("#c3c9d6")
        ax.spines["left"].set_color("#c3c9d6")
        ax.set_ylabel("Minutes", color="#c3c9d6")
        ax.set_ylim(0, 600)
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                val,
                f"{val}",
                ha="center",
                va="bottom",
                color="#f3f6ff",
                fontsize=9,
            )
        self.canvas.draw()

    def _render_month_cards(self, cards):
        if not self.month_cards_layout:
            return
        # clear existing
        while self.month_cards_layout.count():
            item = self.month_cards_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        palette = ["#7ac7ff", "#c792ff", "#6ee7b7"]

        def parse_rgb(hex_color: str):
            hex_color = hex_color.lstrip("#")
            return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

        for idx, (label, minutes) in enumerate(reversed(cards)):
            r, g, b = parse_rgb(palette[idx % len(palette)])
            card = QWidget()
            card.setStyleSheet(
                """
                QWidget {{
                  background: rgba({r},{g},{b},0.16);
                  border: 1px solid rgba({r},{g},{b},0.45);
                  border-radius: 12px;
                }}
                """.format(r=r, g=g, b=b)
            )
            layout = QVBoxLayout(card)
            layout.setContentsMargins(12, 10, 12, 10)
            title = QLabel(f"{label}")
            title.setStyleSheet("color:#f3f6ff; font-size:16px; font-weight:700;")
            total = QLabel(f"{minutes} min")
            total.setStyleSheet("color:#c3c9d6; font-size:14px;")
            layout.addWidget(title)
            layout.addWidget(total)
            self.month_cards_layout.addWidget(card)
