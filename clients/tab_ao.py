"""Analog Output tab — shows state of all 4 AO channels from IOC."""
import os, threading, numpy as np
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QPushButton)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

BG="#1b1d23"; AXB="#22252d"; GC="#33363f"; TC="#b0b4bc"
COLORS=["#4fc3f7","#ffb74d","#ce93d8","#a5d6a7"]


class AOPlot(FigureCanvas):
    """Time-domain plot of all 4 AO channels from IOC waveform data."""
    def __init__(self):
        self.fig = Figure(figsize=(8,4), facecolor=BG)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(AXB)
        self.ax.tick_params(colors=TC, labelsize=8)
        for s in self.ax.spines.values(): s.set_color(GC)
        super().__init__(self.fig)
        self._channels = [None]*4
        self._enabled = [False]*4

    def update_channels(self, channels, enabled, running, loop_time):
        self._channels = channels
        self._enabled = enabled
        self.ax.clear()
        self.ax.set_facecolor(AXB)
        self.ax.tick_params(colors=TC, labelsize=8)
        for s in self.ax.spines.values(): s.set_color(GC)

        any_data = False
        for i, data in enumerate(channels):
            if data is not None and enabled[i]:
                any_data = True
                if loop_time and loop_time > 0:
                    t = np.linspace(0, loop_time, len(data), endpoint=False)
                else:
                    t = np.arange(len(data))
                self.ax.plot(t, data, lw=0.6, color=COLORS[i],
                    label=f"AO{i}" + (" (off)" if not enabled[i] else ""))

        if not any_data:
            self.ax.text(.5,.5,"No waveform data loaded",ha="center",va="center",
                transform=self.ax.transAxes,fontsize=11,color="#555a66")
        else:
            xl = "Time (s)" if loop_time and loop_time > 0 else "Sample"
            self.ax.set_xlabel(xl, color=TC, fontsize=9)
            self.ax.set_ylabel("Voltage (V)", color=TC, fontsize=9)
            self.ax.legend(fontsize=8, loc="upper right",
                facecolor=AXB, edgecolor=GC, labelcolor=TC)
            self.ax.grid(True, color=GC, alpha=.4, lw=.5)

        status = "RUNNING" if running else "STOPPED"
        color = "#00e676" if running else "#ef5350"
        self.ax.set_title(f"AO Channels [{status}]", color=color, fontsize=10,
                         fontweight="bold")
        self.fig.tight_layout(pad=1.5)
        self.draw()


class AOTab(QWidget):
    def __init__(self, worker):
        super().__init__()
        self.w = worker
        self._build()

    def _build(self):
        main = QHBoxLayout(self)
        main.setContentsMargins(4,4,4,4); main.setSpacing(6)

        # Left: channel status cards
        left = QWidget(); left.setMinimumWidth(200); left.setMaximumWidth(350)
        ll = QVBoxLayout(left); ll.setContentsMargins(0,0,0,0); ll.setSpacing(4)

        self.cards = []
        for i in range(4):
            card = QGroupBox(f"AO{i}")
            card.setStyleSheet(f"QGroupBox{{color:{COLORS[i]};}}")
            g = QGridLayout(); g.setSpacing(2); card.setLayout(g)

            en_l = QLabel("--"); en_l.setStyleSheet("font-weight:bold;")
            g.addWidget(QLabel("Status:"), 0, 0)
            g.addWidget(en_l, 0, 1)

            amp_l = QLabel("--")
            g.addWidget(QLabel("Scale:"), 1, 0)
            g.addWidget(amp_l, 1, 1)

            off_l = QLabel("--")
            g.addWidget(QLabel("Offset:"), 2, 0)
            g.addWidget(off_l, 2, 1)

            pts_l = QLabel("--")
            g.addWidget(QLabel("Points:"), 3, 0)
            g.addWidget(pts_l, 3, 1)

            self.cards.append({"group": card, "enable": en_l, "amp": amp_l,
                              "offset": off_l, "points": pts_l})
            ll.addWidget(card)

        # Global info
        ig = QGroupBox("Waveform Status")
        il = QGridLayout(); il.setSpacing(2); ig.setLayout(il)
        self.run_l = QLabel("--"); self.run_l.setFont(QFont("Consolas", 12))
        il.addWidget(QLabel("State:"), 0, 0); il.addWidget(self.run_l, 0, 1)
        self.freq_l = QLabel("--")
        il.addWidget(QLabel("Frequency:"), 1, 0); il.addWidget(self.freq_l, 1, 1)
        self.loop_l = QLabel("--")
        il.addWidget(QLabel("Loop time:"), 2, 0); il.addWidget(self.loop_l, 2, 1)
        self.npts_l = QLabel("--")
        il.addWidget(QLabel("Num points:"), 3, 0); il.addWidget(self.npts_l, 3, 1)
        ll.addWidget(ig)

        ll.addStretch()

        rb = QPushButton("Refresh")
        rb.clicked.connect(self.poll)
        ll.addWidget(rb)

        main.addWidget(left, stretch=1)

        # Right: plot
        self.plot = AOPlot()
        main.addWidget(self.plot, stretch=2)

    def poll(self):
        """Read IOC state in background and update display."""
        def _do():
            run = self.w._get("WaveGen:Run", as_string=True)
            freq = self.w._get("WaveGen:Frequency")
            npts = self.w._get("WaveGen:NumPoints")

            channels = []
            enabled = []
            for i in range(4):
                en = self.w._get(f"WaveGen:Ch{i}:Enable")
                amp = self.w._get(f"WaveGen:Ch{i}:Amplitude")
                off = self.w._get(f"WaveGen:Ch{i}:Offset")
                enabled.append(bool(en))

                # Read waveform data from IOC
                wf = self.w._get(f"WaveGen:Ch{i}:UserWF")
                if wf is not None and hasattr(wf, '__len__') and len(wf) > 0:
                    # Apply amplitude and offset as the IOC would
                    n = int(npts) if npts else len(wf)
                    data = np.array(wf[:n]) * float(amp or 1) + float(off or 0)
                    channels.append(data)
                else:
                    channels.append(None)

                # Update card labels (via main thread)
                card = self.cards[i]
                card["enable"].setText("Enabled" if en else "Disabled")
                card["enable"].setStyleSheet(
                    f"font-weight:bold;color:{'#66bb6a' if en else '#ef5350'};")
                card["amp"].setText(f"{float(amp or 0):.4f}")
                card["offset"].setText(f"{float(off or 0):.4f} V")
                pts = len(wf) if wf is not None and hasattr(wf, '__len__') else 0
                card["points"].setText(str(pts))

            is_running = (run == "Run")
            loop_time = 1.0/float(freq) if freq and float(freq) > 0 else 0

            self.run_l.setText(run or "--")
            self.run_l.setStyleSheet(
                f"font-weight:bold;color:{'#66bb6a' if is_running else '#ef5350'};")
            self.freq_l.setText(f"{float(freq or 0):.6f} Hz")
            self.loop_l.setText(f"{loop_time:.4f} s")
            self.npts_l.setText(str(int(npts or 0)))

            self.plot.update_channels(channels, enabled, is_running, loop_time)

        threading.Thread(target=_do, daemon=True).start()
