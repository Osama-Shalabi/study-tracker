from PySide6.QtWidgets import QWidget, QPushButton


def apply_panel_style(widget: QWidget):
    widget.setStyleSheet(
        """
        QWidget {
          background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                       stop:0 rgba(255,255,255,0.05), stop:1 rgba(255,255,255,0.02));
          border: 1px solid rgba(255,255,255,0.10);
          border-radius: 14px;
        }
        """
    )


def apply_primary_button(btn: QPushButton):
    btn.setStyleSheet(
        """
        QPushButton {
          background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                       stop:0 #7ac7ff, stop:1 #c792ff);
          color: #0a0f1a;
          font-weight: 800;
          letter-spacing: 0.2px;
          padding: 11px 18px;
          border-radius: 12px;
          border: 1px solid rgba(255,255,255,0.16);
        }
        QPushButton:hover {
          border-color: #7ac7ff;
          background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                       stop:0 #8ed2ff, stop:1 #d4b3ff);
        }
        QPushButton:pressed {
          background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                       stop:0 #66b5ee, stop:1 #b07df6);
        }
        """
    )


def apply_secondary_button(btn: QPushButton):
    btn.setStyleSheet(
        """
        QPushButton {
          background: rgba(255,255,255,0.04);
          color: #e7ecf4;
          font-weight: 700;
          padding: 9px 14px;
          border-radius: 12px;
          border: 1px solid rgba(122,199,255,0.25);
        }
        QPushButton:hover {
          border-color: #7ac7ff;
          color: #7ac7ff;
          background: rgba(122,199,255,0.08);
        }
        """
    )
