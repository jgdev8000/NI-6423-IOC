"""Counters tab — 4 counters with mode selection."""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton, QComboBox, QStackedWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

class CounterPanel(QWidget):
    def __init__(self, ctr_id, worker):
        super().__init__()
        self.ctr = ctr_id
        self.w = worker
        self._build()

    def _build(self):
        g = QGroupBox(f"Counter {self.ctr}")
        gl = QGridLayout(); gl.setSpacing(4); g.setLayout(gl)

        gl.addWidget(QLabel("Mode:"), 0, 0)
        self.mode = QComboBox()
        self.mode.addItems(["Disabled", "Edge Count", "Freq Measure", "Pulse Gen"])
        self.mode.currentIndexChanged.connect(self._mode_changed)
        gl.addWidget(self.mode, 0, 1, 1, 2)

        # Edge count
        gl.addWidget(QLabel("Count:"), 1, 0)
        self.count_l = QLabel("0")
        self.count_l.setFont(QFont("Consolas", 14))
        self.count_l.setStyleSheet("color:#4fc3f7;")
        gl.addWidget(self.count_l, 1, 1)
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(lambda: self.w.send_ctr_reset(self.ctr))
        gl.addWidget(self.reset_btn, 1, 2)

        # Freq measure
        gl.addWidget(QLabel("Frequency:"), 2, 0)
        self.freq_l = QLabel("0.000 Hz")
        self.freq_l.setFont(QFont("Consolas", 14))
        self.freq_l.setStyleSheet("color:#ffb74d;")
        gl.addWidget(self.freq_l, 2, 1, 1, 2)

        # Pulse gen
        gl.addWidget(QLabel("Pulse Freq (Hz):"), 3, 0)
        self.pfreq = QLineEdit("1000"); self.pfreq.setFixedWidth(80)
        gl.addWidget(self.pfreq, 3, 1)

        gl.addWidget(QLabel("Duty Cycle:"), 4, 0)
        self.pduty = QLineEdit("0.5"); self.pduty.setFixedWidth(80)
        gl.addWidget(self.pduty, 4, 1)

        self.pulse_btn = QPushButton("Start Pulse")
        self.pulse_btn.setCheckable(True)
        self.pulse_btn.setStyleSheet(
            "QPushButton{padding:6px;}"
            "QPushButton:checked{background:#1b5e20;color:#66bb6a;border-color:#388e3c;}")
        self.pulse_btn.clicked.connect(self._pulse_toggle)
        gl.addWidget(self.pulse_btn, 3, 2, 2, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(g)

    def _mode_changed(self, idx):
        self.w.send_ctr_mode(self.ctr, idx)

    def _pulse_toggle(self, checked):
        try:
            f = float(self.pfreq.text())
            d = float(self.pduty.text())
        except: f, d = 1000, 0.5
        self.pulse_btn.setText("Stop Pulse" if checked else "Start Pulse")
        self.w.send_ctr_pulse(self.ctr, f, d, checked)

    def update_values(self, count, freq):
        self.count_l.setText(str(count))
        self.freq_l.setText(f"{freq:.3f} Hz")


class CountersTab(QWidget):
    def __init__(self, worker):
        super().__init__()
        self.w = worker
        self.w.ctr_update.connect(self._on_ctr)
        self.panels = []
        self._build()

    def _build(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(4,4,4,4); main.setSpacing(4)

        grid = QHBoxLayout()
        for i in range(4):
            p = CounterPanel(i, self.w)
            self.panels.append(p)
            grid.addWidget(p)
        main.addLayout(grid)
        main.addStretch()

    def _on_ctr(self, ctr, count, freq):
        if 0 <= ctr < 4:
            self.panels[ctr].update_values(count, freq)

    def poll(self):
        for i in range(4):
            self.w.poll_ctr(i)
