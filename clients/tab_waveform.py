"""Waveform Generator tab — 2 independent channel pairs, side by side."""
import os, json, numpy as np, threading
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
    QFileDialog, QMessageBox, QSplitter)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from waveform_filter import waveform_filter, load_mat_pattern

BG="#1b1d23"; AXB="#22252d"; GC="#33363f"; TC="#b0b4bc"
COLORS=["#4fc3f7","#ffb74d","#ce93d8","#a5d6a7"]
PATC=["#66bb6a","#ef5350"]; GLOWC="#00e676"


class XYPlot(FigureCanvas):
    """Single XY pattern plot."""
    def __init__(self, title="XY Pattern"):
        self.fig = Figure(figsize=(4,3.5), facecolor=BG)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(AXB)
        self.ax.tick_params(colors=TC, labelsize=8)
        for s in self.ax.spines.values(): s.set_color(GC)
        super().__init__(self.fig)
        self._title = title
        self.u=None; self.v=None; self.running=False; self.gp=0

    def set_data(self, u, v):
        self.u=u; self.v=v; self._redraw()

    def _redraw(self):
        self.ax.clear()
        self.ax.set_facecolor(AXB)
        self.ax.tick_params(colors=TC, labelsize=8)
        for s in self.ax.spines.values(): s.set_color(GC)
        self.ax.grid(True, color=GC, alpha=.4, lw=.5)

        if self.u is None or self.v is None:
            self.ax.text(.5,.5,"No data",ha="center",va="center",
                transform=self.ax.transAxes,fontsize=11,color="#555a66")
            self.ax.set_xlim(-1,1); self.ax.set_ylim(-1,1)
        elif self.running:
            a=.12+.08*np.sin(self.gp)
            self.ax.plot(self.u,self.v,lw=5,color=GLOWC,alpha=a,zorder=1)
            self.ax.plot(self.u,self.v,lw=.5,color="#81c784",zorder=2)
            self.ax.set_aspect("equal", adjustable="datalim")
        else:
            self.ax.plot(self.u,self.v,lw=.4,color=PATC[0])
            self.ax.set_aspect("equal", adjustable="datalim")

        title = self._title
        if self.running: title += "  [RUNNING]"
        self.ax.set_title(title, color=GLOWC if self.running else TC, fontsize=10,
                         fontweight="bold" if self.running else "normal")
        self.fig.tight_layout(pad=1.0)
        self.draw()

    def set_running(self, r):
        if r != self.running: self.running=r; self.gp=0; self._redraw()

    def pulse(self):
        if self.running and self.u is not None: self.gp+=.3; self._redraw()


class PairControls(QWidget):
    """Controls for one channel pair: files, scale, offset, loop time, filter. No plot."""
    def __init__(self, ch_a, ch_b, color_a, color_b, worker, parent_tab):
        super().__init__()
        self.ch_a=ch_a; self.ch_b=ch_b; self.w=worker; self.tab=parent_tab
        self.u_data=None; self.v_data=None; self._u_path=""; self._v_path=""
        self.plot = None  # set by WaveformTab after construction
        self.setMinimumWidth(180)
        self.setMaximumWidth(300)
        self._build(color_a, color_b)

        self._patterns = []
        self._pattern_folder = ""

    def _build(self, ca, cb):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0); layout.setSpacing(3)

        # Pattern library
        pg = QGroupBox("Pattern Library")
        pl = QVBoxLayout(); pl.setSpacing(2); pg.setLayout(pl)

        # Folder selector
        frow = QHBoxLayout(); frow.setSpacing(2)
        self.folder_l = QLabel("(no folder)"); self.folder_l.setStyleSheet("font-size:9px;color:#7a8a9a;")
        frow.addWidget(self.folder_l, stretch=1)
        fb = QPushButton("Folder..."); fb.setStyleSheet("font-size:10px;padding:2px;")
        fb.clicked.connect(self._browse_folder); frow.addWidget(fb)
        pl.addLayout(frow)

        # Pattern dropdown
        self.pattern_combo = QComboBox(); self.pattern_combo.setStyleSheet("font-size:10px;")
        self.pattern_combo.currentIndexChanged.connect(self._on_pattern_selected)
        pl.addWidget(self.pattern_combo)
        layout.addWidget(pg, stretch=1)

        # Manual file browse (fallback)
        fg = QGroupBox(f"AO{self.ch_a} / AO{self.ch_b}")
        g = QGridLayout(); g.setSpacing(2); fg.setLayout(g)

        g.addWidget(QLabel(f"AO{self.ch_a}:"), 0, 0)
        self.ul = QLabel("(none)"); self.ul.setStyleSheet(f"color:{ca};font-size:10px;")
        g.addWidget(self.ul, 0, 1)
        b = QPushButton("..."); b.setFixedWidth(28); b.clicked.connect(self._browse_u)
        g.addWidget(b, 0, 2)

        g.addWidget(QLabel(f"AO{self.ch_b}:"), 1, 0)
        self.vl = QLabel("(none)"); self.vl.setStyleSheet(f"color:{cb};font-size:10px;")
        g.addWidget(self.vl, 1, 1)
        b2 = QPushButton("..."); b2.setFixedWidth(28); b2.clicked.connect(self._browse_v)
        g.addWidget(b2, 1, 2)

        mb = QPushButton("Load .mat"); mb.setStyleSheet("font-size:10px;padding:2px;")
        mb.clicked.connect(self._browse_mat); g.addWidget(mb, 2, 0, 1, 3)
        layout.addWidget(fg, stretch=1)

        # Scale/offset
        sg = QGroupBox("Scale / Offset")
        sl = QGridLayout(); sl.setSpacing(2); sg.setLayout(sl)
        ha = QLabel(f"AO{self.ch_a}"); ha.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ha.setStyleSheet(f"font-weight:bold;color:{ca};font-size:9px;")
        hb = QLabel(f"AO{self.ch_b}"); hb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hb.setStyleSheet(f"font-weight:bold;color:{cb};font-size:9px;")
        sl.addWidget(ha, 0, 1); sl.addWidget(hb, 0, 2)
        sl.addWidget(QLabel("Scale:"), 1, 0)
        self.su = QLineEdit("1.0"); self.su.setMinimumWidth(35); sl.addWidget(self.su, 1, 1)
        self.sv = QLineEdit("1.0"); self.sv.setMinimumWidth(35); sl.addWidget(self.sv, 1, 2)
        sl.addWidget(QLabel("Offset:"), 2, 0)
        self.ou = QLineEdit("0.0"); self.ou.setMinimumWidth(35); sl.addWidget(self.ou, 2, 1)
        self.ov = QLineEdit("0.0"); self.ov.setMinimumWidth(35); sl.addWidget(self.ov, 2, 2)
        ap = QPushButton("Apply"); ap.setStyleSheet("font-size:10px;padding:2px;")
        ap.clicked.connect(self._apply); sl.addWidget(ap, 3, 0, 1, 3)
        layout.addWidget(sg, stretch=1)

        # Timing + filter
        tg = QGroupBox("Timing / Filter")
        tl = QGridLayout(); tl.setSpacing(2); tg.setLayout(tl)
        tl.addWidget(QLabel("Loop (s):"), 0, 0)
        self.loop_e = QLineEdit("1.0"); self.loop_e.setMinimumWidth(40)
        tl.addWidget(self.loop_e, 0, 1, 1, 2)
        self.filt_en = QCheckBox("Filter")
        self.filt_en.stateChanged.connect(self._preview)
        tl.addWidget(self.filt_en, 1, 0)
        tl.addWidget(QLabel("Cut:"), 1, 1)
        self.cut_e = QLineEdit("1000"); self.cut_e.setMinimumWidth(40)
        self.cut_e.editingFinished.connect(self._preview)
        tl.addWidget(self.cut_e, 1, 2)
        fa = QPushButton("Apply"); fa.setStyleSheet("font-size:10px;padding:2px;")
        fa.clicked.connect(self._apply)
        tl.addWidget(fa, 2, 0, 1, 3)
        layout.addWidget(tg, stretch=1)

        # Per-pair start/stop
        rg = QGroupBox("Output")
        rl = QVBoxLayout(); rl.setSpacing(2); rg.setLayout(rl)
        st = QPushButton("Start")
        st.setStyleSheet("QPushButton{background:#1565c0;color:#e3f2fd;font-weight:bold;"
            "padding:5px;font-size:11px;border:1px solid #1976d2;border-radius:3px;}"
            "QPushButton:hover{background:#1976d2;}")
        st.clicked.connect(self._start_pair); rl.addWidget(st)
        sp = QPushButton("Stop")
        sp.setStyleSheet("QPushButton{background:#6a1b9a;color:#f3e5f5;font-weight:bold;"
            "padding:5px;font-size:11px;border:1px solid #7b1fa2;border-radius:3px;}"
            "QPushButton:hover{background:#7b1fa2;}")
        sp.clicked.connect(self._stop_pair); rl.addWidget(sp)
        layout.addWidget(rg, stretch=1)

    def _start_pair(self):
        """Load this pair's data and start."""
        if not self.tab._outputs_active:
            QMessageBox.warning(self, "Outputs disabled",
                "Turn on 'Outputs ON' before starting.")
            return
        self.tab._load_pair(self, restart_if_running=False)

    def _stop_pair(self):
        self.tab._stop()

    # --- Pattern library ---
    def _scan_folder(self, folder):
        """Scan folder for *X.csv/*Y.csv pairs and .mat files."""
        self._patterns = []
        self._pattern_folder = folder
        if not folder or not os.path.isdir(folder):
            return
        files = os.listdir(folder)

        # Find *X.csv / *Y.csv pairs
        x_files = sorted([f for f in files if f.endswith('X.csv')])
        for xf in x_files:
            name = xf[:-5]  # strip 'X.csv'
            yf = name + 'Y.csv'
            if yf in files:
                self._patterns.append({
                    "name": name,
                    "ao0": os.path.join(folder, xf),
                    "ao1": os.path.join(folder, yf),
                    "type": "csv"
                })

        # Find .mat files
        for f in sorted(files):
            if f.endswith('.mat'):
                self._patterns.append({
                    "name": f[:-4],
                    "ao0": os.path.join(folder, f),
                    "ao1": os.path.join(folder, f),
                    "type": "mat"
                })

        self._refresh_pattern_combo()

    def _refresh_pattern_combo(self):
        self.pattern_combo.blockSignals(True)
        self.pattern_combo.clear()
        self.pattern_combo.addItem("(select pattern)")
        for p in self._patterns:
            pts_label = ""
            self.pattern_combo.addItem(p["name"])
        self.pattern_combo.setCurrentIndex(0)
        self.pattern_combo.blockSignals(False)

    def _browse_folder(self):
        self.tab._dialog_open = True
        try:
            folder = QFileDialog.getExistingDirectory(self, "Select Pattern Folder")
        finally:
            self.tab._dialog_open = False
        if folder:
            self.folder_l.setText(os.path.basename(folder))
            self._scan_folder(folder)
            self.tab._save_config()

    def _on_pattern_selected(self, idx):
        if idx <= 0 or idx > len(self._patterns): return
        p = self._patterns[idx - 1]
        if p["type"] == "mat":
            try:
                self.u_data, self.v_data = load_mat_pattern(p["ao0"])
                self._u_path = self._v_path = p["ao0"]
                self.ul.setText(p["name"] + " [X]")
                self.vl.setText(p["name"] + " [Y]")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e)); return
        else:
            self._u_path = p["ao0"]; self._v_path = p["ao1"]
            self.u_data = np.loadtxt(p["ao0"]); self.v_data = np.loadtxt(p["ao1"])
            self.ul.setText(os.path.basename(p["ao0"]))
            self.vl.setText(os.path.basename(p["ao1"]))
        self._preview()

    def set_folder(self, folder):
        """Set pattern folder (called from restore)."""
        if folder and os.path.isdir(folder):
            self._pattern_folder = folder
            self.folder_l.setText(os.path.basename(folder))
            self._scan_folder(folder)

    def _dlg(self, title, filt="CSV (*.csv);;All (*)"):
        self.tab._dialog_open = True
        try: p, _ = QFileDialog.getOpenFileName(self, title, "", filt)
        finally: self.tab._dialog_open = False
        return p

    def _browse_u(self):
        p = self._dlg(f"Select AO{self.ch_a} CSV")
        if p:
            self._u_path=p; self.ul.setText(os.path.basename(p))
            self.u_data=np.loadtxt(p); self._preview()

    def _browse_v(self):
        p = self._dlg(f"Select AO{self.ch_b} CSV")
        if p:
            self._v_path=p; self.vl.setText(os.path.basename(p))
            self.v_data=np.loadtxt(p); self._preview()

    def _browse_mat(self):
        p = self._dlg("Select .mat", "MAT (*.mat);;All (*)")
        if not p: return
        try:
            a, b = load_mat_pattern(p)
            self._u_path=self._v_path=p; self.u_data=a; self.v_data=b
            self.ul.setText(os.path.basename(p)+" [0]")
            self.vl.setText(os.path.basename(p)+" [1]")
            self.tab._save_config()
            self._preview()
        except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def _apply(self):
        self._preview()
        # Reload data to IOC with new settings, restart if was running
        if self.tab._outputs_active:
            self.tab._load_pair(self, restart_if_running=True)

    def _get_params(self):
        try: su=float(self.su.text() or 1)
        except: su=1
        try: sv=float(self.sv.text() or 1)
        except: sv=1
        try: ou=float(self.ou.text() or 0)
        except: ou=0
        try: ov=float(self.ov.text() or 0)
        except: ov=0
        try: lt=float(self.loop_e.text() or 1)
        except: lt=1
        try: cut=float(self.cut_e.text() or 1000)
        except: cut=1000
        return su, sv, ou, ov, lt, cut

    def get_output_data(self):
        """Returns filtered, scaled data ready to send to IOC, plus loop time."""
        if self.u_data is None or self.v_data is None:
            return None, None, 1.0
        su, sv, ou, ov, lt, cut = self._get_params()
        u = self.u_data * su + ou
        v = self.v_data * sv + ov
        if self.filt_en.isChecked() and cut > 0 and lt > 0:
            u = waveform_filter(u, lt, cut)
            v = waveform_filter(v, lt, cut)
        return u, v, lt

    def _preview(self):
        u, v, _ = self.get_output_data()
        if self.plot: self.plot.set_data(u, v)


class WaveformTab(QWidget):
    def __init__(self, worker, config_path):
        super().__init__()
        self.w = worker
        self.cfg_path = config_path
        self._dialog_open = False; self._is_running = False
        self._build()
        self._restore()
        self.w.status_update.connect(self._on_status)
        self.w.load_done.connect(self._on_load_done)
        self.w.wavegen_state.connect(self._on_wavegen_state)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4,4,4,4); outer.setSpacing(4)

        # Top bar: activate toggle + trigger
        top = QHBoxLayout(); top.setSpacing(6)

        self.activate_btn = QPushButton("Outputs OFF")
        self.activate_btn.setCheckable(True)
        self.activate_btn.setChecked(False)
        self._outputs_active = False
        self.activate_btn.setStyleSheet(
            "QPushButton{background:#b71c1c;color:#ffcdd2;font-weight:bold;"
            "padding:6px 16px;font-size:12px;border:1px solid #c62828;border-radius:4px;}"
            "QPushButton:checked{background:#1b5e20;color:#c8e6c9;border-color:#2e7d32;}")
        self.activate_btn.clicked.connect(self._toggle_activate)
        top.addWidget(self.activate_btn)

        top.addStretch()
        top.addWidget(QLabel("Trigger:"))
        self.trig_src = QComboBox()
        self.trig_src.addItems(["Software","PFI0","PFI1","PFI2","PFI3","PFI4","PFI5","PFI6","PFI7"])
        top.addWidget(self.trig_src)
        outer.addLayout(top)

        sg = QGroupBox("IOC State")
        sgl = QGridLayout(); sgl.setSpacing(4); sg.setLayout(sgl)
        self.state_run = QLabel("--")
        self.state_channels = QLabel("--")
        self.state_trigger = QLabel("--")
        self.state_marker = QLabel("--")
        self.state_patterns = QLabel("--")
        self.validation_l = QLabel("Validation: ready")
        self.validation_l.setStyleSheet("color:#7a8a9a;")
        self.validation_l.setWordWrap(True)
        sgl.addWidget(QLabel("Run:"), 0, 0); sgl.addWidget(self.state_run, 0, 1)
        sgl.addWidget(QLabel("Enabled AO:"), 0, 2); sgl.addWidget(self.state_channels, 0, 3)
        sgl.addWidget(QLabel("Trigger:"), 1, 0); sgl.addWidget(self.state_trigger, 1, 1)
        sgl.addWidget(QLabel("Marker:"), 1, 2); sgl.addWidget(self.state_marker, 1, 3)
        sgl.addWidget(QLabel("Patterns:"), 2, 0); sgl.addWidget(self.state_patterns, 2, 1, 1, 3)
        sgl.addWidget(self.validation_l, 3, 0, 1, 4)
        outer.addWidget(sg)

        # Main: [controls0] [plot0] [plot1] [controls1]
        main = QHBoxLayout(); main.setSpacing(4)

        self.pair0 = PairControls(0, 1, COLORS[0], COLORS[1], self.w, self)
        self.plot0 = XYPlot("AO0 vs AO1")
        self.plot1 = XYPlot("AO2 vs AO3")
        self.pair1 = PairControls(2, 3, COLORS[2], COLORS[3], self.w, self)

        self.pair0.plot = self.plot0
        self.pair1.plot = self.plot1

        main.addWidget(self.pair0, stretch=1)
        main.addWidget(self.plot0, stretch=2)
        main.addWidget(self.plot1, stretch=2)
        main.addWidget(self.pair1, stretch=1)

        outer.addLayout(main, stretch=1)

        # Status bar
        self.status_l = QLabel("Ready")
        self.status_l.setFont(QFont("Consolas", 8))
        self.status_l.setStyleSheet("color:#7a8a9a;padding:2px;")
        outer.addWidget(self.status_l)

    def _toggle_activate(self, checked):
        if checked:
            valid, message = self._validate_for_load(require_pair0=False)
            if not valid:
                self.activate_btn.setChecked(False)
                self.validation_l.setText(message)
                self.validation_l.setStyleSheet("color:#ef5350;")
                return
            # Activate outputs
            self._outputs_active = True
            self.activate_btn.setText("Outputs ON")
            self.status_l.setText("Outputs activated — ready")
        else:
            # Deactivate: stop and center
            self._outputs_active = False
            self.activate_btn.setText("Outputs OFF")
            self._stop()

    def _preview(self):
        u0, v0, _ = self.pair0.get_output_data()
        u1, v1, _ = self.pair1.get_output_data()
        self.plot0.set_data(u0, v0)
        self.plot1.set_data(u1, v1)

    def _load(self, auto_restart=False):
        u0, v0, lt0 = self.pair0.get_output_data()
        u1, v1, lt1 = self.pair1.get_output_data()

        if u0 is None or v0 is None:
            if not auto_restart:
                QMessageBox.warning(self, "Missing", "Load AO0/AO1 pattern first.")
            return

        valid, message = self._validate_for_load(require_pair0=True)
        self.validation_l.setText(message)
        self.validation_l.setStyleSheet("color:#66bb6a;" if valid else "color:#ef5350;")
        if not valid:
            if not auto_restart:
                QMessageBox.warning(self, "Invalid waveform setup", message)
            return

        # Use pair0's loop time for the hardware clock (all channels share one clock)
        freq = 1.0 / lt0 if lt0 > 0 else 1.0

        def _send():
            with self.w._lock:
                ok = True
                self.w.load_done.emit("Stopping...")
                ok = self.w._put("WaveGen:Run", 0) and ok
                import time; time.sleep(0.3)

                n = len(u0)
                ok = self.w._put("WaveGen:NumPoints", n) and ok
                ok = self.w._put("WaveGen:Frequency", freq) and ok
                ok = self.w._put("WaveGen:MarkerEnable", 1) and ok
                ok = self.w._put("WaveGen:MarkerWidth", 10) and ok

                self.w.load_done.emit(f"Sending AO0 ({n})...")
                ok = self.w._put("WaveGen:Ch0:UserWF", u0) and ok
                ok = self.w._put("WaveGen:Ch0:Amplitude", 1.0) and ok
                ok = self.w._put("WaveGen:Ch0:Offset", 0.0) and ok
                ok = self.w._put("WaveGen:Ch0:Enable", 1) and ok

                self.w.load_done.emit(f"Sending AO1 ({n})...")
                ok = self.w._put("WaveGen:Ch1:UserWF", v0) and ok
                ok = self.w._put("WaveGen:Ch1:Amplitude", 1.0) and ok
                ok = self.w._put("WaveGen:Ch1:Offset", 0.0) and ok
                ok = self.w._put("WaveGen:Ch1:Enable", 1) and ok

                if u1 is not None and v1 is not None:
                    self.w.load_done.emit("Sending AO2/AO3...")
                    ok = self.w._put("WaveGen:Ch2:UserWF", u1) and ok
                    ok = self.w._put("WaveGen:Ch2:Amplitude", 1.0) and ok
                    ok = self.w._put("WaveGen:Ch2:Offset", 0.0) and ok
                    ok = self.w._put("WaveGen:Ch2:Enable", 1) and ok
                    ok = self.w._put("WaveGen:Ch3:UserWF", v1) and ok
                    ok = self.w._put("WaveGen:Ch3:Amplitude", 1.0) and ok
                    ok = self.w._put("WaveGen:Ch3:Offset", 0.0) and ok
                    ok = self.w._put("WaveGen:Ch3:Enable", 1) and ok
                else:
                    ok = self.w._put("WaveGen:Ch2:Enable", 0) and ok
                    ok = self.w._put("WaveGen:Ch3:Enable", 0) and ok

                ok = self.w._put("WaveGen:TriggerSource", self.trig_src.currentIndex()) and ok
                ok = self.w._put("WaveGen:TriggerEdge", 0) and ok

                if auto_restart and self._is_running and ok:
                    ok = self.w._put("WaveGen:Continuous", 1) and ok
                    ok = self.w._put("WaveGen:Run", 1) and ok
                    self.w.load_done.emit(f"Running ({n} pts)" if ok else "Waveform load failed")
                else:
                    self.w.load_done.emit(f"Loaded {n} pts. Press Start." if ok else "Waveform load failed")
        threading.Thread(target=_send, daemon=True).start()

        # Save config after loading
        self._save_config()

    def _load_pair(self, pair, restart_if_running=False):
        """Load a single pair's data to IOC. Optionally restart if was running."""
        u, v, lt = pair.get_output_data()
        if u is None or v is None:
            if not restart_if_running:
                QMessageBox.warning(self, "Missing", f"Load AO{pair.ch_a}/AO{pair.ch_b} pattern first.")
            return
        valid, message = self._validate_pair(pair)
        self.validation_l.setText(message)
        self.validation_l.setStyleSheet("color:#66bb6a;" if valid else "color:#ef5350;")
        if not valid:
            if not restart_if_running:
                QMessageBox.warning(self, "Invalid waveform setup", message)
            return
        freq = 1.0 / lt if lt > 0 else 1.0
        was_running = self._is_running
        always_start = not restart_if_running  # Start button always starts
        should_restart = always_start or (restart_if_running and was_running)

        def _send():
            with self.w._lock:
                ok = True
                self.w.load_done.emit("Stopping...")
                ok = self.w._put("WaveGen:Run", 0) and ok
                import time; time.sleep(0.3)
                n = len(u)
                ok = self.w._put("WaveGen:NumPoints", n) and ok
                ok = self.w._put("WaveGen:Frequency", freq) and ok

                self.w.load_done.emit(f"Sending AO{pair.ch_a} ({n})...")
                ok = self.w._put(f"WaveGen:Ch{pair.ch_a}:UserWF", u) and ok
                ok = self.w._put(f"WaveGen:Ch{pair.ch_a}:Amplitude", 1.0) and ok
                ok = self.w._put(f"WaveGen:Ch{pair.ch_a}:Offset", 0.0) and ok
                ok = self.w._put(f"WaveGen:Ch{pair.ch_a}:Enable", 1) and ok

                self.w.load_done.emit(f"Sending AO{pair.ch_b} ({n})...")
                ok = self.w._put(f"WaveGen:Ch{pair.ch_b}:UserWF", v) and ok
                ok = self.w._put(f"WaveGen:Ch{pair.ch_b}:Amplitude", 1.0) and ok
                ok = self.w._put(f"WaveGen:Ch{pair.ch_b}:Offset", 0.0) and ok
                ok = self.w._put(f"WaveGen:Ch{pair.ch_b}:Enable", 1) and ok

                other_channels = [ch for ch in range(4) if ch not in (pair.ch_a, pair.ch_b)]
                for ch in other_channels:
                    ok = self.w._put(f"WaveGen:Ch{ch}:Enable", 0) and ok

                ok = self.w._put("WaveGen:TriggerSource", self.trig_src.currentIndex()) and ok
                ok = self.w._put("WaveGen:TriggerEdge", 0) and ok

                if should_restart and ok:
                    ok = self.w._put("WaveGen:Continuous", 1) and ok
                    ok = self.w._put("WaveGen:Run", 1) and ok
                    self.w.load_done.emit(
                        f"Running AO{pair.ch_a}/AO{pair.ch_b} ({n} pts)" if ok else "Waveform load failed")
                else:
                    self.w.load_done.emit(f"Loaded {n} pts. Press Start." if ok else "Waveform load failed")
        threading.Thread(target=_send, daemon=True).start()

    def _stop(self):
        """Stop output and return all AO channels to 0V (center)."""
        def _do():
            ok = self.w._put("WaveGen:Run", 0)
            import time; time.sleep(0.2)
            # Write single-point zero waveform to park at center
            import numpy as np
            zero = np.array([0.0], dtype=np.float64)
            ok = self.w._put("WaveGen:NumPoints", 1) and ok
            for ch in range(4):
                ok = self.w._put(f"WaveGen:Ch{ch}:UserWF", zero) and ok
                ok = self.w._put(f"WaveGen:Ch{ch}:Amplitude", 1.0) and ok
                ok = self.w._put(f"WaveGen:Ch{ch}:Offset", 0.0) and ok
            # Run once to output the zero value, then stop
            ok = self.w._put("WaveGen:Continuous", 0) and ok
            ok = self.w._put("WaveGen:Run", 1) and ok
            time.sleep(0.1)
            ok = self.w._put("WaveGen:Run", 0) and ok
            self.w.load_done.emit("Stopped — centered at 0V" if ok else "Stop/center failed")
        import threading
        threading.Thread(target=_do, daemon=True).start()

    def _on_status(self, text, running, curpt):
        self.status_l.setText(text); self._is_running = running
        self.plot0.set_running(running)
        self.plot1.set_running(running)
        self.w.poll_wavegen_state()

    def _on_load_done(self, msg): self.status_l.setText(msg)

    def _on_wavegen_state(self, state):
        run = state.get("run") or "--"
        enabled = state.get("enabled", [])
        trigger_idx = int(state.get("trigger_source") or 0)
        trigger_names = ["Software","PFI0","PFI1","PFI2","PFI3","PFI4","PFI5","PFI6","PFI7"]
        trigger = trigger_names[trigger_idx] if 0 <= trigger_idx < len(trigger_names) else str(trigger_idx)
        marker = "On" if state.get("marker_enable") else "Off"
        if state.get("marker_enable"):
            marker += f" ({int(state.get('marker_width') or 0)} samples)"

        enabled_labels = [f"AO{i}" for i, en in enumerate(enabled) if en]
        self.state_run.setText(run)
        self.state_run.setStyleSheet(
            f"font-weight:bold;color:{'#66bb6a' if run == 'Run' else '#ef5350'};")
        self.state_channels.setText(", ".join(enabled_labels) if enabled_labels else "none")
        self.state_trigger.setText(trigger)
        self.state_marker.setText(marker)
        self.state_patterns.setText(
            f"AO0/1: {self._pair_summary(self.pair0)} | AO2/3: {self._pair_summary(self.pair1)}")

    def _pair_summary(self, pair):
        if pair.u_data is None or pair.v_data is None:
            return "none"
        src = os.path.basename(pair._u_path) if pair._u_path else "loaded"
        return f"{src} ({len(pair.u_data)} pts)"

    def _validate_voltage_range(self, u, v, pair):
        peak = max(float(np.max(np.abs(u))), float(np.max(np.abs(v))))
        if peak > 10.0:
            return False, f"AO{pair.ch_a}/AO{pair.ch_b} exceeds +/-10 V after scale/filter ({peak:.3f} V peak)."
        return True, f"AO{pair.ch_a}/AO{pair.ch_b} validated ({peak:.3f} V peak)."

    def _validate_pair(self, pair):
        u, v, lt = pair.get_output_data()
        if u is None or v is None:
            return False, f"Load AO{pair.ch_a}/AO{pair.ch_b} pattern first."
        if len(u) != len(v):
            return False, f"AO{pair.ch_a}/AO{pair.ch_b} X/Y lengths differ."
        if len(u) < 1 or len(u) > 10000:
            return False, f"AO{pair.ch_a}/AO{pair.ch_b} must contain 1..10000 points."
        if lt <= 0:
            return False, f"AO{pair.ch_a}/AO{pair.ch_b} loop time must be > 0."
        return self._validate_voltage_range(u, v, pair)

    def _validate_for_load(self, require_pair0=True):
        pair0_ok, pair0_msg = self._validate_pair(self.pair0)
        pair1_loaded = self.pair1.u_data is not None and self.pair1.v_data is not None

        if require_pair0 and not pair0_ok:
            return False, pair0_msg

        if pair1_loaded:
            pair1_ok, pair1_msg = self._validate_pair(self.pair1)
            if not pair1_ok:
                return False, pair1_msg
            if len(self.pair0.get_output_data()[0]) != len(self.pair1.get_output_data()[0]):
                return False, "AO0/1 and AO2/3 must have the same number of points when loaded together."
            lt0 = self.pair0.get_output_data()[2]
            lt1 = self.pair1.get_output_data()[2]
            if abs(lt0 - lt1) > 1e-9:
                return False, "AO0/1 and AO2/3 must use the same loop time when loaded together."

        if pair0_ok and pair1_loaded:
            return True, "Validation: both AO pairs are consistent and within range."
        if pair0_ok:
            return True, "Validation: AO0/1 is ready."
        return True, "Validation: outputs can be activated; load a pair before starting."

    def pulse_glow(self):
        if not self._dialog_open and self._is_running:
            self.plot0.pulse(); self.plot1.pulse()

    # --- Config ---

    def _save_config(self):
        try:
            try:
                with open(self.cfg_path) as f: cfg=json.load(f)
            except: cfg={}
            cfg["settings"]={
                "pattern_folder_0":self.pair0._pattern_folder,
                "pattern_folder_1":self.pair1._pattern_folder,
                "loop_time_0":self.pair0.loop_e.text(),
                "loop_time_1":self.pair1.loop_e.text(),
                "trigger_source":self.trig_src.currentIndex(),
                "scale_u0":self.pair0.su.text(),"scale_v0":self.pair0.sv.text(),
                "offset_u0":self.pair0.ou.text(),"offset_v0":self.pair0.ov.text(),
                "filter_enable_0":self.pair0.filt_en.isChecked(),
                "cutoff_0":self.pair0.cut_e.text(),
                "scale_u1":self.pair1.su.text(),"scale_v1":self.pair1.sv.text(),
                "offset_u1":self.pair1.ou.text(),"offset_v1":self.pair1.ov.text(),
                "filter_enable_1":self.pair1.filt_en.isChecked(),
                "cutoff_1":self.pair1.cut_e.text(),
                "last_u0":self.pair0._u_path,"last_v0":self.pair0._v_path,
                "last_u1":self.pair1._u_path,"last_v1":self.pair1._v_path}
            with open(self.cfg_path,"w") as f: json.dump(cfg,f,indent=2)
        except: pass

    def _restore(self):
        try:
            with open(self.cfg_path) as f: cfg = json.load(f)
        except: cfg = {}
        s = cfg.get("settings", {})
        if not s: return
        # Restore pattern folders
        self.pair0.set_folder(s.get("pattern_folder_0", ""))
        self.pair1.set_folder(s.get("pattern_folder_1", ""))
        self.pair0.loop_e.setText(s.get("loop_time_0", s.get("loop_time","1.0")))
        self.pair1.loop_e.setText(s.get("loop_time_1","1.0"))
        self.trig_src.setCurrentIndex(int(s.get("trigger_source",0)))
        self.pair0.su.setText(s.get("scale_u0",s.get("scale_u","1.0")))
        self.pair0.sv.setText(s.get("scale_v0",s.get("scale_v","1.0")))
        self.pair0.ou.setText(s.get("offset_u0",s.get("offset_u","0.0")))
        self.pair0.ov.setText(s.get("offset_v0",s.get("offset_v","0.0")))
        self.pair0.filt_en.setChecked(s.get("filter_enable_0",s.get("filter_enable",False)))
        self.pair0.cut_e.setText(s.get("cutoff_0",s.get("cutoff","1000")))
        self.pair1.su.setText(s.get("scale_u1","1.0"))
        self.pair1.sv.setText(s.get("scale_v1","1.0"))
        self.pair1.ou.setText(s.get("offset_u1","0.0"))
        self.pair1.ov.setText(s.get("offset_v1","0.0"))
        self.pair1.filt_en.setChecked(s.get("filter_enable_1",False))
        self.pair1.cut_e.setText(s.get("cutoff_1","1000"))

        # Load pair0 files
        up=s.get("last_u0",s.get("last_u_path","")); vp=s.get("last_v0",s.get("last_v_path",""))
        if up and os.path.isfile(up):
            self.pair0._u_path=up
            if up.endswith('.mat'):
                try: self.pair0.u_data, self.pair0.v_data = load_mat_pattern(up)
                except: pass
                self.pair0._v_path=up
                self.pair0.ul.setText(os.path.basename(up)+" [0]")
                self.pair0.vl.setText(os.path.basename(up)+" [1]")
            else:
                self.pair0.ul.setText(os.path.basename(up))
                try: self.pair0.u_data=np.loadtxt(up)
                except: pass
                if vp and os.path.isfile(vp):
                    self.pair0._v_path=vp; self.pair0.vl.setText(os.path.basename(vp))
                    try: self.pair0.v_data=np.loadtxt(vp)
                    except: pass

        # Load pair1 files
        up1=s.get("last_u1",""); vp1=s.get("last_v1","")
        if up1 and os.path.isfile(up1):
            self.pair1._u_path=up1
            if up1.endswith('.mat'):
                try: self.pair1.u_data, self.pair1.v_data = load_mat_pattern(up1)
                except: pass
                self.pair1._v_path=up1
                self.pair1.ul.setText(os.path.basename(up1)+" [0]")
                self.pair1.vl.setText(os.path.basename(up1)+" [1]")
            else:
                self.pair1.ul.setText(os.path.basename(up1))
                try: self.pair1.u_data=np.loadtxt(up1)
                except: pass
                if vp1 and os.path.isfile(vp1):
                    self.pair1._v_path=vp1; self.pair1.vl.setText(os.path.basename(vp1))
                    try: self.pair1.v_data=np.loadtxt(vp1)
                    except: pass

        self.pair0._preview()
        self.pair1._preview()

    def save_settings(self):
        self._save_config()
