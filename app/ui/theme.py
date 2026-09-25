"""Тема Majestic (#3B82F6 / #22D3EE) — тёмный QSS."""

BG = "#0B1220"
PANEL = "#111C33"
PANEL_2 = "#16223D"
BORDER = "#24365E"
TEXT = "#E6EDF7"
MUTED = "#8FA3C4"
PRIMARY = "#3B82F6"
ACCENT = "#22D3EE"
DANGER = "#EF4444"
OK = "#34D399"


def build_qss() -> str:
    return f"""
QWidget {{ background: {BG}; color: {TEXT}; font-size: 13px; }}
QLabel {{ background: transparent; }}
QLabel#appTitle {{ font-size: 16px; font-weight: 700; color: {TEXT}; }}
QLabel#appSub {{ color: {MUTED}; font-size: 11px; }}
QLabel#sectionTitle {{ font-size: 13px; font-weight: 700; color: {ACCENT}; }}
QLabel#hint {{ color: {MUTED}; font-size: 11px; }}
QLabel#cardTitle {{ font-weight: 700; color: {TEXT}; }}
QLabel#cardText {{ color: {MUTED}; }}
QLabel#chipRow {{ color: {MUTED}; }}

QFrame#titleBar {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
QFrame#section {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QTimeEdit, QComboBox {{
  background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 8px;
  padding: 6px 8px; color: {TEXT}; selection-background-color: {PRIMARY};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QTimeEdit:focus {{
  border: 1px solid {PRIMARY};
}}
QComboBox QAbstractItemView {{ background: {PANEL_2}; color: {TEXT};
  selection-background-color: {PRIMARY}; border: 1px solid {BORDER}; }}

QPushButton {{
  background: {PANEL_2}; color: {TEXT}; border: 1px solid {BORDER};
  border-radius: 8px; padding: 7px 14px;
}}
QPushButton:hover {{ border-color: {PRIMARY}; background: #1B2A4A; }}
QPushButton:pressed {{ background: {PRIMARY}; }}
QPushButton#primary {{ background: {PRIMARY}; border: none; font-weight: 700; }}
QPushButton#primary:hover {{ background: #2F74E8; }}
QPushButton#accent {{ background: {ACCENT}; color: #06283A; border: none; font-weight: 700; }}
QPushButton#accent:hover {{ background: #1FC2DE; }}
QPushButton#danger {{ color: #FFC9C9; border-color: #7F1D1D; background: #2A1215; }}
QPushButton#danger:hover {{ border-color: {DANGER}; }}
QPushButton#chip {{
  background: {PANEL_2}; color: {MUTED}; border: 1px solid {BORDER};
  border-radius: 14px; padding: 5px 12px; font-size: 12px;
}}
QPushButton#chip:hover {{ color: {TEXT}; border-color: {PRIMARY}; }}
QPushButton#chip:checked {{ background: {PRIMARY}; color: white; border-color: {PRIMARY}; font-weight: 600; }}
QPushButton#ghost {{ background: transparent; border: 1px solid {BORDER}; color: {MUTED}; }}
QPushButton#ghost:hover {{ color: {TEXT}; border-color: {PRIMARY}; }}
QPushButton#tbBtn {{ background: transparent; border: none; color: {MUTED}; padding: 6px 10px; font-size: 14px; }}
QPushButton#tbBtn:hover {{ background: {PANEL_2}; color: {TEXT}; border-radius: 8px; }}
QPushButton#navBtn {{ background: transparent; border: none; color: {MUTED};
  padding: 7px 14px; font-weight: 600; border-radius: 8px; }}
QPushButton#navBtn:hover {{ color: {TEXT}; background: {PANEL_2}; }}
QPushButton#navBtn:checked {{ color: white; background: {PRIMARY}; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {BORDER};
  border-radius: 4px; background: {PANEL_2}; }}
QCheckBox::indicator:checked {{ background: {PRIMARY}; border-color: {PRIMARY}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {PRIMARY}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QMenu {{ background: {PANEL_2}; border: 1px solid {BORDER}; padding: 6px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: {PRIMARY}; color: white; }}

QToolTip {{ background: {PANEL_2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QToast {{
  background: #0E7490; color: white; border-radius: 10px;
  padding: 10px 16px; font-weight: 600;
}}
"""
