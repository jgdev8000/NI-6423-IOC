#!/usr/bin/env python3
"""
NI USB-6423 Full Control UI

Usage:
    python3 nidaq_ui.py

Environment:
    EPICS_CA_ADDR_LIST=<ioc-ip>
    EPICS_CA_AUTO_ADDR_LIST=NO
    EPICS_CA_MAX_ARRAY_BYTES=100000
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget
from PyQt6.QtCore import QTimer

from nidaq_worker import EpicsWorker
from tab_waveform import WaveformTab
from tab_ao import AOTab
from tab_ai import AITab
from tab_dio import DIOTab
from tab_counters import CountersTab

DARK_STYLE = """
QMainWindow, QWidget { background-color: #1b1d23; color: #d4d4d8;
    font-family: "Segoe UI", "Helvetica Neue", sans-serif; font-size: 12px; }
QTabWidget::pane { border: 1px solid #33363f; background: #1b1d23; }
QTabBar::tab { background: #23262e; color: #8bb4d9; border: 1px solid #33363f;
    padding: 8px 18px; margin-right: 2px; border-top-left-radius: 4px;
    border-top-right-radius: 4px; }
QTabBar::tab:selected { background: #2a2d36; color: #e8e8ec;
    border-bottom-color: #2a2d36; }
QTabBar::tab:hover { background: #2f323c; }
QGroupBox { background-color: #23262e; border: 1px solid #33363f;
    border-radius: 6px; margin-top: 14px; padding: 12px 8px 8px 8px;
    font-weight: bold; color: #8bb4d9; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #8bb4d9; }
QLabel { color: #b0b4bc; background: transparent; }
QLineEdit { background-color: #2a2d36; border: 1px solid #3d414d; border-radius: 3px;
    padding: 4px 6px; color: #e8e8ec; selection-background-color: #4a90d9; }
QLineEdit:focus { border-color: #5a9fd4; }
QComboBox { background-color: #2a2d36; border: 1px solid #3d414d; border-radius: 3px;
    padding: 4px 6px; color: #e8e8ec; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView { background-color: #2a2d36; color: #e8e8ec;
    border: 1px solid #3d414d; selection-background-color: #4a90d9; }
QPushButton { background-color: #2f323c; border: 1px solid #3d414d; border-radius: 4px;
    padding: 5px 12px; color: #d4d4d8; }
QPushButton:hover { background-color: #383c48; border-color: #5a9fd4; }
QPushButton:pressed { background-color: #4a90d9; color: white; }
QCheckBox { color: #b0b4bc; spacing: 6px; background: transparent; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #3d414d;
    border-radius: 3px; background-color: #2a2d36; }
QCheckBox::indicator:checked { background-color: #4a90d9; border-color: #5a9fd4; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NI USB-6423 DAQ Control")
        self.setMinimumSize(1100, 600)
        self.resize(1250, 700)

        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mems_settings.json")

        self.worker = EpicsWorker()

        # Stop any running output on startup
        self.worker.send_stop()

        tabs = QTabWidget()
        self.wf_tab = WaveformTab(self.worker, cfg_path)
        self.ao_tab = AOTab(self.worker)
        self.ai_tab = AITab(self.worker)
        self.dio_tab = DIOTab(self.worker)
        self.ctr_tab = CountersTab(self.worker)

        tabs.addTab(self.wf_tab, "Waveform Gen")
        tabs.addTab(self.ao_tab, "Analog Output")
        tabs.addTab(self.ai_tab, "Analog Input")
        tabs.addTab(self.dio_tab, "Digital I/O")
        tabs.addTab(self.ctr_tab, "Counters")

        self.setCentralWidget(tabs)
        self._tabs = tabs

        # Status poll
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self._poll)
        self.poll_timer.start(1000)

        # Glow animation
        self.glow_timer = QTimer()
        self.glow_timer.timeout.connect(self.wf_tab.pulse_glow)
        self.glow_timer.start(150)

    def _poll(self):
        self.worker.poll_status()
        idx = self._tabs.currentIndex()
        if idx == 1: self.ao_tab.poll()
        elif idx == 2: self.ai_tab.poll()
        elif idx == 3: self.dio_tab.poll()
        elif idx == 4: self.ctr_tab.poll()

    def closeEvent(self, event):
        self.poll_timer.stop()
        self.glow_timer.stop()
        # Stop output on close
        self.worker.send_stop()
        self.wf_tab.save_settings()
        self.worker.shutdown()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
