ANA_RENK = "#1f4e79"
VURGU = "#2e75b6"

STIL = f"""
* {{ font-family: 'Segoe UI', Arial; font-size: 10pt; }}
QMainWindow, QDialog {{ background: #f4f6f9; }}
#yanPanel {{ background: {ANA_RENK}; }}
#yanMenu {{ background: {ANA_RENK}; border: none; color: white; outline: 0;
           show-decoration-selected: 1; }}
#yanMenu::item {{ padding: 8px 10px; border-left: 3px solid transparent; border-radius: 0; }}
#yanMenu::item:selected {{ background: #2b5f91; border-left: 3px solid #ffc000; color: white; }}
#yanMenu::item:hover {{ background: #285a8a; }}
#yanMenu::branch {{ background: transparent; }}
#menuBaslik {{ background: #173b5c; color: #ffffff; }}
#menuBaslikYazi {{ color: #ffffff; font-weight: bold; font-size: 11pt; }}
QPushButton#menuDaralt {{ background: #1f4e79; color: white; border: 1px solid #3a6a9a;
                          border-radius: 4px; padding: 0; font-weight: 700; }}
QPushButton#menuDaralt:hover {{ background: #2e75b6; }}
#sayfaBaslik {{ font-size: 15pt; font-weight: 600; color: {ANA_RENK}; padding: 4px 0; }}
#sayfaAciklama {{ color: #555; padding-bottom: 6px; }}
#ustBar {{ background: white; border-bottom: 1px solid #d9dee5; }}
QPushButton {{ background: white; border: 1px solid #b8c2cf; border-radius: 4px; padding: 5px 12px; }}
QPushButton:hover {{ background: #eaf1f8; border-color: {VURGU}; }}
QPushButton:disabled {{ color: #999; background: #f0f0f0; }}
QPushButton#birincil {{ background: {VURGU}; color: white; border-color: {VURGU}; font-weight: 600; }}
QPushButton#birincil:hover {{ background: {ANA_RENK}; }}
QPushButton#tehlike {{ color: #b00020; border-color: #e8a19b; }}
QPushButton#tehlike:hover {{ background: #fdecea; }}
QTableWidget {{ background: white; gridline-color: #e3e7ec; selection-background-color: #cfe2f7;
               selection-color: black; alternate-background-color: #f8fafc; border: 1px solid #d0d7e0; }}
QHeaderView::section {{ background: #e8edf3; padding: 4px; border: none; border-right: 1px solid #d0d7e0;
                        border-bottom: 1px solid #d0d7e0; font-weight: 600; }}
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit, QTextEdit, QPlainTextEdit {{
    background: white; border: 1px solid #b8c2cf; border-radius: 3px; padding: 3px; }}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{ border-color: {VURGU}; }}
QGroupBox {{ border: 1px solid #cfd6df; border-radius: 5px; margin-top: 12px; background: white; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {ANA_RENK}; font-weight: 600; }}
QTabWidget::pane {{ border: 1px solid #cfd6df; background: white; }}
QTabBar::tab {{ padding: 6px 14px; background: #e8edf3; border: 1px solid #cfd6df; border-bottom: none; }}
QTabBar::tab:selected {{ background: white; color: {ANA_RENK}; font-weight: 600; }}
#kart {{ background: white; border: 1px solid #d6dde6; border-radius: 6px; }}
#kartBaslik {{ color: #5a6675; font-size: 9pt; }}
#kartDeger {{ color: {ANA_RENK}; font-size: 15pt; font-weight: 700; }}
#uyariKutusu {{ background: #fff4e5; border: 1px solid #f0b86e; border-radius: 4px; padding: 6px; color: #7a4b00; }}
#hataKutusu {{ background: #fdecea; border: 1px solid #e8a19b; border-radius: 4px; padding: 6px; color: #8a1c12; }}
#okKutusu {{ background: #e8f5e9; border: 1px solid #9ccc9f; border-radius: 4px; padding: 6px; color: #1b5e20; }}
"""
