"""Analog Input tab — 32-channel live readings + acquisition."""
import csv
import os
import numpy as np
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

BG="#1b1d23"; AXB="#22252d"; GC="#33363f"; TC="#b0b4bc"


class AIAcqPlot(FigureCanvas):
    def __init__(self):
        self.fig = Figure(figsize=(7, 4), facecolor=BG)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(AXB)
        self.ax.tick_params(colors=TC, labelsize=8)
        for s in self.ax.spines.values():
            s.set_color(GC)
        super().__init__(self.fig)

    def update_trace(self, data, rate, channel, acquired):
        self.ax.clear()
        self.ax.set_facecolor(AXB)
        self.ax.tick_params(colors=TC, labelsize=8)
        for s in self.ax.spines.values():
            s.set_color(GC)
        self.ax.grid(True, color=GC, alpha=.4, lw=.5)

        if data is None or len(data) == 0:
            self.ax.text(.5, .5, "No acquisition data", ha="center", va="center",
                transform=self.ax.transAxes, fontsize=11, color="#555a66")
        else:
            arr = np.asarray(data, dtype=float)
            if rate and rate > 0:
                x = np.arange(len(arr)) / rate
                self.ax.set_xlabel("Time (s)", color=TC, fontsize=9)
            else:
                x = np.arange(len(arr))
                self.ax.set_xlabel("Sample", color=TC, fontsize=9)
            self.ax.plot(x, arr, lw=0.8, color="#4fc3f7")
            self.ax.set_ylabel("Voltage (V)", color=TC, fontsize=9)

        self.ax.set_title(
            f"AI Acquisition — Channel {channel} ({acquired} samples)",
            color=TC, fontsize=10, fontweight="bold")
        self.fig.tight_layout(pad=1.2)
        self.draw()

class AITab(QWidget):
    def __init__(self, worker):
        super().__init__()
        self.w = worker
        self.w.ai_update.connect(self._on_ai)
        self.w.ai_acq_update.connect(self._on_ai_acq)
        self._acq_data = {"channels": [[] for _ in range(32)], "rate": 0.0, "num_acquired": 0}
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

        al.addWidget(QLabel("Display Ch:"), 5, 0)
        self.display_ch = QComboBox()
        self.display_ch.addItems([str(i) for i in range(32)])
        self.display_ch.currentIndexChanged.connect(self._refresh_plot)
        al.addWidget(self.display_ch, 5, 1)

        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        al.addWidget(export_btn, 6, 0, 1, 2)

        self.acq_status = QLabel("No acquisition captured")
        self.acq_status.setStyleSheet("color:#7a8a9a;")
        al.addWidget(self.acq_status, 7, 0, 1, 2)

        right.addWidget(ag)
        self.plot = AIAcqPlot()
        right.addWidget(self.plot, stretch=1)
        right.addStretch()
        main.addLayout(right, stretch=1)

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
        self.acq_status.setText("Acquiring...")
        self.w.send_ai_acq(rate, npts, self.trig.currentIndex(), self.clk.currentIndex())

    def _on_ai_acq(self, state):
        self._acq_data = state
        self.acq_status.setText(
            f"Captured {state['num_acquired']} samples/ch at {state['rate']:.1f} Hz")
        self._refresh_plot()

    def _refresh_plot(self):
        ch = self.display_ch.currentIndex()
        channels = self._acq_data.get("channels", [])
        trace = channels[ch] if 0 <= ch < len(channels) else []
        self.plot.update_trace(trace, self._acq_data.get("rate", 0.0), ch,
                               self._acq_data.get("num_acquired", 0))

    def _export_csv(self):
        channels = self._acq_data.get("channels", [])
        acquired = self._acq_data.get("num_acquired", 0)
        if acquired <= 0 or not any(len(ch) for ch in channels):
            self.acq_status.setText("No acquisition data to export")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Export AI Acquisition", "", "CSV (*.csv)")
        if not path:
            return

        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["sample"] + [f"AI{i}" for i in range(32)])
            for idx in range(acquired):
                row = [idx]
                for ch in range(32):
                    vals = channels[ch] if ch < len(channels) else []
                    row.append(vals[idx] if idx < len(vals) else "")
                writer.writerow(row)
        self.acq_status.setText(f"Exported acquisition to {os.path.basename(path)}")

    def poll(self):
        self.w.poll_ai()
