"""Analog Input tab — 32-channel live readings + acquisition."""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

class AITab(QWidget):
    def __init__(self, worker):
        super().__init__()
        self.w = worker
        self.w.ai_update.connect(self._on_ai)
        self._build()

    def _build(self):
        main = QHBoxLayout(self)
        main.setContentsMargins(4,4,4,4); main.setSpacing(6)

        # Left: AI table
        left = QVBoxLayout()
        tg = QGroupBox("AI Channels (32)")
        tl = QVBoxLayout(); tg.setLayout(tl)

        self.table = QTableWidget(32, 2)
        self.table.setHorizontalHeaderLabels(["Channel", "Voltage (V)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setStyleSheet("QTableWidget{background:#22252d;color:#d4d4d8;gridline-color:#33363f;}"
            "QHeaderView::section{background:#2a2d36;color:#8bb4d9;border:1px solid #33363f;padding:4px;}")

        for i in range(32):
            ch = QTableWidgetItem(f"AI:{i}")
            ch.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 0, ch)
            val = QTableWidgetItem("0.0000")
            val.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val.setFont(QFont("Consolas", 10))
            self.table.setItem(i, 1, val)
            self.table.setRowHeight(i, 22)

        tl.addWidget(self.table)
        left.addWidget(tg)
        main.addLayout(left, stretch=1)

        # Right: Acquisition controls
        right = QVBoxLayout()
        ag = QGroupBox("HW-Timed Acquisition")
        al = QGridLayout(); al.setSpacing(4); ag.setLayout(al)

        al.addWidget(QLabel("Rate (Hz):"), 0, 0)
        self.rate_e = QLineEdit("10000"); self.rate_e.setFixedWidth(80)
        al.addWidget(self.rate_e, 0, 1)

        al.addWidget(QLabel("Num Points:"), 1, 0)
        self.npts_e = QLineEdit("10000"); self.npts_e.setFixedWidth(80)
        al.addWidget(self.npts_e, 1, 1)

        al.addWidget(QLabel("Trigger:"), 2, 0)
        self.trig = QComboBox()
        self.trig.addItems(["Software", "AO StartTrigger", "PFI0", "PFI1"])
        al.addWidget(self.trig, 2, 1)

        al.addWidget(QLabel("Clock:"), 3, 0)
        self.clk = QComboBox()
        self.clk.addItems(["Internal", "AO SampleClock"])
        al.addWidget(self.clk, 3, 1)

        acq_btn = QPushButton("Acquire")
        acq_btn.setStyleSheet("font-weight:bold;padding:8px;")
        acq_btn.clicked.connect(self._acquire)
        al.addWidget(acq_btn, 4, 0, 1, 2)

        right.addWidget(ag)
        right.addStretch()
        main.addLayout(right)

    def _on_ai(self, vals):
        for i, v in enumerate(vals):
            if i < 32:
                item = self.table.item(i, 1)
                if item:
                    item.setText(f"{v:+.4f}")

    def _acquire(self):
        try:
            rate = float(self.rate_e.text())
            npts = int(self.npts_e.text())
        except: return
        self.w.send_ai_acq(rate, npts, self.trig.currentIndex(), self.clk.currentIndex())

    def poll(self):
        self.w.poll_ai()
