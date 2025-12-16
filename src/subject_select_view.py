from typing import Callable, List

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QAbstractItemView,
)

from .data_store import DataStore
from .theme import apply_panel_style, apply_primary_button, apply_secondary_button


class SubjectListWidget(QListWidget):
    """List that supports internal drag-and-drop reordering."""

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
            sid = self.item(i).data(Qt.UserRole)
            if sid is not None:
                ordered_ids.append(int(sid))
        self.orderChanged.emit(ordered_ids)


class SubjectSelectView(QWidget):
    def __init__(
        self,
        store: DataStore,
        on_choose: Callable[[int], None],
        to_home: Callable[[], None],
    ):
        super().__init__()
        self.store = store
        self.on_choose = on_choose
        self.to_home = to_home

        self.list_widget = SubjectListWidget()
        self.list_widget.setStyleSheet(
            """
            QListWidget {
              background: rgba(255,255,255,0.05);
              border: 1px solid rgba(255,255,255,0.08);
              border-radius: 14px;
              padding: 10px;
            }
            QListWidget::item {
              padding: 0px;
              margin: 12px 0;
              border-radius: 12px;
            }
            QListWidget::item:selected {
              background: transparent;
            }
            """
        )

        self.name_input = QLineEdit()
        self.color = "#7ac7ff"
        self._loading_subjects = False

        self._build_ui()

        self.list_widget.itemDoubleClicked.connect(self._choose_subject)
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self.list_widget.orderChanged.connect(self._persist_order)

        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Select a subject to study")
        title.setStyleSheet("color:#f3f6ff; font-size:20px; font-weight:700;")
        header.addWidget(title)
        header.addStretch()

        home_btn = QPushButton("← Home")
        apply_secondary_button(home_btn)
        home_btn.clicked.connect(self.to_home)
        header.addWidget(home_btn)

        root.addLayout(header)

        panel = QWidget()
        apply_panel_style(panel)
        panel_layout = QHBoxLayout(panel)
        panel_layout.setContentsMargins(12, 12, 12, 12)
        panel_layout.setSpacing(14)

        panel_layout.addWidget(self.list_widget, stretch=2)

        form_panel = QWidget()
        apply_panel_style(form_panel)
        form_layout = QFormLayout(form_panel)
        form_layout.setContentsMargins(12, 12, 12, 12)
        form_layout.setSpacing(8)

        self.name_input.setPlaceholderText("Subject name")
        form_layout.addRow("Name", self.name_input)

        color_btn = QPushButton("Pick color")
        apply_secondary_button(color_btn)
        color_btn.clicked.connect(self._pick_color)
        form_layout.addRow("Color", color_btn)

        add_btn = QPushButton("Create subject")
        apply_primary_button(add_btn)
        add_btn.clicked.connect(self._create_subject)
        form_layout.addRow(add_btn)

        rename_btn = QPushButton("Rename selected")
        apply_secondary_button(rename_btn)
        rename_btn.clicked.connect(self._rename_selected)
        form_layout.addRow(rename_btn)

        del_btn = QPushButton("Delete selected")
        apply_secondary_button(del_btn)
        del_btn.clicked.connect(self._delete_selected)
        form_layout.addRow(del_btn)

        panel_layout.addWidget(form_panel, stretch=1)
        root.addWidget(panel)

    def refresh(self):
        self._loading_subjects = True
        self.list_widget.clear()

        for row in self.store.list_subjects():
            item = QListWidgetItem()
            item.setData(Qt.UserRole, row["id"])
            item.setData(Qt.UserRole + 1, row["color"])
            item.setForeground(QColor("#f3f6ff"))

            row_widget = QWidget()
            row_widget.setAttribute(Qt.WA_StyledBackground, True)
            row_widget.setAutoFillBackground(True)

            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(12, 10, 12, 10)
            row_layout.setSpacing(12)

            swatch = QLabel()
            swatch.setFixedSize(32, 32)
            swatch.setStyleSheet(
                f"background:{row['color']}; border-radius:10px; border:1px solid rgba(122,199,255,0.45);"
            )

            name_label = QLabel(row["name"])
            name_label.setObjectName("subjectNameLabel")
            name_label.setStyleSheet("color:#e7ecf4; font-size:22px; font-weight:700; letter-spacing:0.2px;")

            row_layout.addWidget(swatch)
            row_layout.addWidget(name_label, 1)
            row_layout.addStretch()

            item.setSizeHint(row_widget.sizeHint().expandedTo(QSize(0, 90)))
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row_widget)

        self._update_row_styles()
        self._prefill_from_selection()
        self._loading_subjects = False

    def _update_row_styles(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            w = self.list_widget.itemWidget(item)
            if not w:
                continue
            color_hex = item.data(Qt.UserRole + 1) or "#7ac7ff"
            self._style_row_widget(w, QColor(color_hex), item.isSelected())

    def _style_row_widget(self, row_widget: QWidget, color_obj: QColor, selected: bool):
        r, g, b = color_obj.red(), color_obj.green(), color_obj.blue()

        if selected:
            row_widget.setStyleSheet(
                f"background: rgba({r},{g},{b},0.34);"
                f"border: 1px solid rgba({r},{g},{b},0.82);"
                "border-radius: 12px;"
            )
        else:
            row_widget.setStyleSheet(
                f"background: rgba({r},{g},{b},0.18);"
                f"border: 1px solid rgba({r},{g},{b},0.32);"
                "border-radius: 12px;"
            )

    def _on_selection_changed(self):
        self._update_row_styles()
        self._prefill_from_selection()

    def _prefill_from_selection(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        # Read from the label on the row widget since we removed item text
        row_widget = self.list_widget.itemWidget(item)
        if row_widget:
            label = row_widget.findChild(QLabel, "subjectNameLabel")
            if label:
                self.name_input.setText(label.text())

    def _pick_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.color = color.name()

    def _create_subject(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing name", "Please enter a subject name.")
            return
        try:
            self.store.create_subject(name, self.color)
            self.name_input.clear()
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _rename_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.information(self, "Select a subject", "Please select a subject to rename.")
            return
        new_name = self.name_input.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Missing name", "Enter a new name to rename the subject.")
            return
        subject_id = item.data(Qt.UserRole)
        try:
            self.store.rename_subject(subject_id, new_name)
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _delete_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        subject_id = item.data(Qt.UserRole)
        confirm = QMessageBox.question(self, "Delete?", "Delete this subject?")
        if confirm == QMessageBox.Yes:
            self.store.delete_subject(subject_id)
            self.refresh()

    def _choose_subject(self, item: QListWidgetItem):
        subject_id = item.data(Qt.UserRole)
        if subject_id:
            self.on_choose(subject_id)

    def _persist_order(self, ordered_ids: List[int]):
        if self._loading_subjects:
            return
        self.store.reorder_subjects(ordered_ids)
        self._update_row_styles()
