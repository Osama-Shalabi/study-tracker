import sys
from pathlib import Path
from PySide6.QtCore import QLoggingCategory

from PySide6.QtWidgets import QApplication, QStackedWidget
from PySide6.QtGui import QIcon

from src.data_store import DataStore
from src.home_view import HomeView
from src.subject_select_view import SubjectSelectView
from src.study_view import StudyView


def app_base_path() -> Path:
    """Return the folder where bundled assets live (supports PyInstaller)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def load_app_icon(base_path: Path) -> QIcon | None:
    """Load the application icon if present."""
    icon_path = base_path / "app-icon.png"
    if icon_path.exists():
        return QIcon(str(icon_path))
    return None


class MainWindow(QStackedWidget):
    def __init__(self, store: DataStore):
        super().__init__()
        self.store = store

        self.home = HomeView(store, self.navigate_to_subjects, self.navigate_to_home)
        self.subjects = SubjectSelectView(store, self.navigate_to_study, self.navigate_to_home)
        self.study = StudyView(store, self.navigate_to_home, self.navigate_to_subjects)

        self.addWidget(self.home)      # index 0
        self.addWidget(self.subjects)  # index 1
        self.addWidget(self.study)     # index 2

        self.setCurrentWidget(self.home)

    def navigate_to_home(self):
        self.home.refresh()
        self.setCurrentWidget(self.home)

    def navigate_to_subjects(self):
        self.subjects.refresh()
        self.setCurrentWidget(self.subjects)

    def navigate_to_study(self, subject_id: int):
        self.study.load_subject(subject_id)
        self.setCurrentWidget(self.study)


def main():
    # Silence verbose Qt multimedia/FFmpeg logs
    QLoggingCategory.setFilterRules("qt.multimedia.*=false")

    app = QApplication(sys.argv)
    base_path = app_base_path()
    app_icon = load_app_icon(base_path)
    if app_icon:
        app.setWindowIcon(app_icon)
    app.setStyleSheet(
        """
        * { font-family: 'Inter', 'SF Pro Display', 'Segoe UI', sans-serif; }
        QWidget { background: #0a0f1a; color: #e7ecf4; }
        QLabel { color: #e7ecf4; }
        QLineEdit, QTextEdit, QListWidget, QSpinBox {
            background: rgba(255,255,255,0.04);
            color: #e7ecf4;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 10px;
            selection-background-color: #7ac7ff;
            selection-color: #0a0f1a;
        }
        QLineEdit::placeholder, QTextEdit::placeholder {
            color: rgba(231,236,244,0.6);
        }
        QListWidget::item { padding: 10px; border-radius: 10px; }
        QListWidget::item:selected {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                         stop:0 rgba(122,199,255,0.25), stop:1 rgba(199,146,255,0.25));
        }
        QPushButton { color: #e7ecf4; }
        QScrollBar:vertical {
            background: transparent;
            width: 12px;
            margin: 6px;
        }
        QScrollBar::handle:vertical {
            background: rgba(255,255,255,0.16);
            border-radius: 6px;
            min-height: 28px;
        }
        QScrollBar::handle:vertical:hover { background: rgba(122,199,255,0.35); }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """
    )

    store = DataStore(base_path / "data.db")
    store.ensure_schema()

    window = MainWindow(store)
    window.setWindowTitle("Study Tracker")
    if app_icon:
        window.setWindowIcon(app_icon)
    window.resize(1100, 800)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
