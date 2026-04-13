"""Digital I/O tab — 16 lines with direction and value control."""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QPushButton, QComboBox)
from PyQt6.QtCore import Qt

class DIOTab(QWidget):
    def __init__(self, worker):
        super().__init__()
        self.w = worker
        self.w.dio_update.connect(self._on_dio)
        self._build()

    def _build(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(4,4,4,4)

        g = QGroupBox("Digital I/O — Port 0 (16 lines)")
        grid = QGridLayout(); grid.setSpacing(4); g.setLayout(grid)

        # Header
        for col, label in enumerate(["Line", "Direction", "Output", "Input State"]):
            h = QLabel(label)
            h.setStyleSheet("font-weight:bold;color:#8bb4d9;")
            h.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(h, 0, col)

        self.dir_combos = []
        self.out_btns = []
        self.in_labels = []
        self.out_states = [0]*16

        for i in range(16):
            row = i + 1

            # Line number
            ln = QLabel(f"DIO:{i}")
            ln.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(ln, row, 0)

            # Direction
            dc = QComboBox()
            dc.addItems(["Input", "Output"])
            dc.setFixedWidth(80)
            idx = i
            dc.currentIndexChanged.connect(lambda val, line=idx: self._dir_changed(line, val))
            grid.addWidget(dc, row, 1)
            self.dir_combos.append(dc)

            # Output toggle
            ob = QPushButton("LOW")
            ob.setFixedWidth(70)
            ob.setCheckable(True)
            ob.setStyleSheet(
                "QPushButton{background:#2a2d36;color:#ef5350;border:1px solid #3d414d;border-radius:3px;padding:4px;}"
                "QPushButton:checked{background:#1b5e20;color:#66bb6a;border-color:#388e3c;}")
            ob.clicked.connect(lambda checked, line=idx: self._out_toggle(line, checked))
            grid.addWidget(ob, row, 2)
            self.out_btns.append(ob)

            # Input state indicator
            il = QLabel("LOW")
            il.setAlignment(Qt.AlignmentFlag.AlignCenter)
            il.setFixedWidth(70)
            il.setStyleSheet("color:#ef5350;background:#2a2d36;border:1px solid #3d414d;border-radius:3px;padding:4px;")
            grid.addWidget(il, row, 3)
            self.in_labels.append(il)

        main.addWidget(g)
        main.addStretch()

    def _dir_changed(self, line, val):
        self.w.send_dio_dir(line, val)

    def _out_toggle(self, line, checked):
        self.out_states[line] = 1 if checked else 0
        self.out_btns[line].setText("HIGH" if checked else "LOW")
        self.w.send_dio(line, self.out_states[line])

    def _on_dio(self, states):
        for i, s in enumerate(states):
            if i < 16:
                self.in_labels[i].setText("HIGH" if s else "LOW")
                self.in_labels[i].setStyleSheet(
                    f"color:{'#66bb6a' if s else '#ef5350'};background:#2a2d36;"
                    "border:1px solid #3d414d;border-radius:3px;padding:4px;")

    def poll(self):
        self.w.poll_dio()
