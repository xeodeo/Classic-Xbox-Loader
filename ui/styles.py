DARK_STYLE = """
QMainWindow, QDialog {
    background-color: #121212;
    color: #ffffff;
}
QWidget {
    background-color: #121212;
    color: #ffffff;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}
QFrame#sidebar {
    background-color: #1a1a1a;
    border-right: 1px solid #2a2a2a;
}
QPushButton[nav_btn="true"] {
    background-color: transparent;
    color: #cccccc;
    border: none;
    border-radius: 0px;
    padding: 12px 20px;
    text-align: left;
    font-size: 13px;
}
QPushButton[nav_btn="true"]:hover {
    background-color: #252525;
    color: #ffffff;
}
QPushButton[nav_btn="true"]:checked {
    background-color: #107c10;
    color: #ffffff;
    font-weight: bold;
}
QPushButton {
    background-color: #2a2a2a;
    color: #ffffff;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 7px 16px;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #353535;
    border-color: #107c10;
}
QPushButton:pressed {
    background-color: #0a5c0a;
}
QPushButton:disabled {
    background-color: #1e1e1e;
    color: #555555;
    border-color: #2a2a2a;
}
QPushButton[accent="true"] {
    background-color: #107c10;
    color: #ffffff;
    border: none;
}
QPushButton[accent="true"]:hover { background-color: #13a10e; }
QPushButton[accent="true"]:pressed { background-color: #0a5c0a; }
QPushButton[danger="true"] {
    background-color: #c42b1c;
    color: #ffffff;
    border: none;
}
QPushButton[danger="true"]:hover { background-color: #e81123; }
QLineEdit {
    background-color: #2a2a2a;
    color: #ffffff;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 7px 10px;
    selection-background-color: #107c10;
}
QLineEdit:focus { border: 1px solid #107c10; background-color: #2e2e2e; }
QLineEdit:disabled { background-color: #1e1e1e; color: #555555; }
QTableWidget {
    background-color: #1e1e1e;
    alternate-background-color: #1a1a1a;
    color: #ffffff;
    gridline-color: #2a2a2a;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    selection-background-color: #107c10;
    selection-color: #ffffff;
}
QTableWidget::item { padding: 6px; border: none; }
QTableWidget::item:hover { background-color: #252525; }
QHeaderView::section {
    background-color: #252525;
    color: #9e9e9e;
    border: none;
    border-bottom: 1px solid #333333;
    padding: 8px;
    font-weight: 600;
    font-size: 12px;
}
QHeaderView { background-color: #252525; }
QListWidget {
    background-color: #1e1e1e;
    alternate-background-color: #1a1a1a;
    color: #ffffff;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    outline: none;
}
QListWidget::item { padding: 8px 12px; }
QListWidget::item:hover { background-color: #252525; }
QListWidget::item:selected { background-color: #107c10; color: #ffffff; }
QScrollBar:vertical {
    background-color: #1a1a1a;
    width: 10px;
    border-radius: 5px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background-color: #3a3a3a;
    border-radius: 5px;
    min-height: 32px;
}
QScrollBar::handle:vertical:hover { background-color: #107c10; }
QScrollBar::handle:vertical:pressed { background-color: #0a5c0a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px; background: none; border: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}
QScrollBar:horizontal {
    background-color: #1a1a1a;
    height: 10px;
    border-radius: 5px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background-color: #3a3a3a;
    border-radius: 5px;
    min-width: 32px;
}
QScrollBar::handle:horizontal:hover { background-color: #107c10; }
QScrollBar::handle:horizontal:pressed { background-color: #0a5c0a; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px; background: none; border: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}
QProgressBar {
    background-color: #2a2a2a;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: #ffffff;
    font-size: 11px;
    height: 18px;
}
QProgressBar::chunk { background-color: #107c10; border-radius: 4px; }
QComboBox {
    background-color: #2a2a2a;
    color: #ffffff;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 6px 10px;
    min-width: 80px;
}
QComboBox:hover { border-color: #107c10; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background-color: #2a2a2a;
    color: #ffffff;
    selection-background-color: #107c10;
    border: 1px solid #3a3a3a;
}
QSpinBox, QDoubleSpinBox {
    background-color: #2a2a2a;
    color: #ffffff;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 5px 8px;
}
QSpinBox:focus, QDoubleSpinBox:focus { border-color: #107c10; }
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background-color: #3a3a3a;
    border: none;
    width: 18px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #107c10;
}
QGroupBox {
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px 8px 8px 8px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    top: -6px;
    padding: 0 6px;
    color: #9e9e9e;
    font-size: 12px;
    background-color: #121212;
}
QTextEdit {
    background-color: #1a1a1a;
    color: #cccccc;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    padding: 6px;
}
QLabel[title="true"] { font-size: 20px; font-weight: bold; color: #ffffff; }
QLabel[section_title="true"] {
    font-size: 12px;
    color: #9e9e9e;
    font-weight: 600;
}
QCheckBox { color: #ffffff; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    background-color: #2a2a2a;
}
QCheckBox::indicator:checked { background-color: #107c10; border-color: #107c10; }
QSplitter::handle { background-color: #2a2a2a; width: 1px; }
QScrollArea { border: none; background-color: transparent; }
QFrame[frameShape="4"] { background-color: #2a2a2a; max-height: 1px; }
QFrame[frameShape="5"] { background-color: #2a2a2a; max-width: 1px; }
QToolTip {
    background-color: #252525;
    color: #ffffff;
    border: 1px solid #107c10;
    padding: 4px 8px;
    border-radius: 4px;
}
"""
