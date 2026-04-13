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

        self._recent = []
        self._recent_key = f"recent_{self.ch_a}_{self.ch_b}"

    def _build(self, ca, cb):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0); layout.setSpacing(3)

        # Recent
        rg = QGroupBox("Recent")
        rl = QHBoxLayout(); rl.setSpacing(2); rg.setLayout(rl)
        self.combo = QComboBox(); self.combo.setStyleSheet("font-size:10px;")
        self.combo.currentIndexChanged.connect(self._on_recent)
        rl.addWidget(self.combo)
        db = QPushButton("X"); db.setFixedSize(20, 20)
        db.setStyleSheet("font-size:9px;padding:0;font-weight:bold;color:#ef5350;")
        db.clicked.connect(self._del_recent); rl.addWidget(db)
        layout.addWidget(rg, stretch=1)

        # Files
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
        self.tab._load_pair(self, restart_if_running=False)

    def _stop_pair(self):
        self.tab._stop()

    # --- Recent pattern management (per-pair) ---
    def load_recent_list(self, recent_list):
        self._recent = recent_list
        self._refresh_combo()

    def _refresh_combo(self):
        self.combo.blockSignals(True); self.combo.clear()
        self.combo.addItem("(select)")
        for e in self._recent: self.combo.addItem(e.get("name","?"))
        self.combo.setCurrentIndex(0); self.combo.blockSignals(False)

    def _on_recent(self, idx):
        if idx <= 0: return
        e = self._recent[idx-1]; a=e["ao0"]; b=e["ao1"]
        if not os.path.isfile(a):
            QMessageBox.warning(self,"Not found",a); return
        self._u_path=a; self._v_path=b
        if a.endswith('.mat'):
            try: self.u_data, self.v_data = load_mat_pattern(a)
            except: return
            self.ul.setText(os.path.basename(a)+" [0]")
            self.vl.setText(os.path.basename(a)+" [1]")
        else:
            if not os.path.isfile(b): return
            self.ul.setText(os.path.basename(a))
            self.vl.setText(os.path.basename(b))
            self.u_data=np.loadtxt(a); self.v_data=np.loadtxt(b)
        self._preview()

    def _del_recent(self):
        i = self.combo.currentIndex()
        if i <= 0: return
        del self._recent[i-1]
        self.tab._save_config(); self._refresh_combo()

    def add_recent(self, ao0, ao1):
        name = f"{os.path.basename(ao0)} + {os.path.basename(ao1)}"
        self._recent = [e for e in self._recent if not(e["ao0"]==ao0 and e["ao1"]==ao1)]
        self._recent.insert(0, {"name":name,"ao0":ao0,"ao1":ao1})
        self._recent = self._recent[:20]
        self.tab._save_config(); self._refresh_combo()

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
            self.add_recent(p, p)
            self._preview()
        except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def _apply(self):
        self._preview()
        # Reload data to IOC with new settings, restart if was running
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

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4,4,4,4); outer.setSpacing(4)

        # Top bar: trigger
        top = QHBoxLayout(); top.setSpacing(6)
        top.addStretch()
        top.addWidget(QLabel("Trigger:"))
        self.trig_src = QComboBox()
        self.trig_src.addItems(["Software","PFI0","PFI1","PFI2","PFI3","PFI4","PFI5","PFI6","PFI7"])
        top.addWidget(self.trig_src)
        outer.addLayout(top)

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

        # Use pair0's loop time for the hardware clock (all channels share one clock)
        freq = 1.0 / lt0 if lt0 > 0 else 1.0

        def _send():
            with self.w._lock:
                self.w.load_done.emit("Stopping...")
                self.w._put("WaveGen:Run", 0)
                import time; time.sleep(0.3)

                n = len(u0)
                self.w._put("WaveGen:NumPoints", n)
                self.w._put("WaveGen:Frequency", freq)
                self.w._put("WaveGen:MarkerEnable", 1)
                self.w._put("WaveGen:MarkerWidth", 10)

                self.w.load_done.emit(f"Sending AO0 ({n})...")
                self.w._put("WaveGen:Ch0:UserWF", u0)
                self.w._put("WaveGen:Ch0:Amplitude", 1.0)
                self.w._put("WaveGen:Ch0:Offset", 0.0)
                self.w._put("WaveGen:Ch0:Enable", 1)

                self.w.load_done.emit(f"Sending AO1 ({n})...")
                self.w._put("WaveGen:Ch1:UserWF", v0)
                self.w._put("WaveGen:Ch1:Amplitude", 1.0)
                self.w._put("WaveGen:Ch1:Offset", 0.0)
                self.w._put("WaveGen:Ch1:Enable", 1)

                if u1 is not None and v1 is not None:
                    self.w.load_done.emit("Sending AO2/AO3...")
                    self.w._put("WaveGen:Ch2:UserWF", u1)
                    self.w._put("WaveGen:Ch2:Amplitude", 1.0)
                    self.w._put("WaveGen:Ch2:Offset", 0.0)
                    self.w._put("WaveGen:Ch2:Enable", 1)
                    self.w._put("WaveGen:Ch3:UserWF", v1)
                    self.w._put("WaveGen:Ch3:Amplitude", 1.0)
                    self.w._put("WaveGen:Ch3:Offset", 0.0)
                    self.w._put("WaveGen:Ch3:Enable", 1)
                else:
                    self.w._put("WaveGen:Ch2:Enable", 0)
                    self.w._put("WaveGen:Ch3:Enable", 0)

                self.w._put("WaveGen:TriggerSource", self.trig_src.currentIndex())
                self.w._put("WaveGen:TriggerEdge", 0)

                if auto_restart and self._is_running:
                    self.w._put("WaveGen:Continuous", 1)
                    self.w._put("WaveGen:Run", 1)
                    self.w.load_done.emit(f"Running ({n} pts)")
                else:
                    self.w.load_done.emit(f"Loaded {n} pts. Press Start.")
        threading.Thread(target=_send, daemon=True).start()

        if self.pair0._u_path and self.pair0._v_path:
            self.pair0.add_recent(self.pair0._u_path, self.pair0._v_path)
        if self.pair1._u_path and self.pair1._v_path:
            self.pair1.add_recent(self.pair1._u_path, self.pair1._v_path)

    def _load_pair(self, pair, restart_if_running=False):
        """Load a single pair's data to IOC. Optionally restart if was running."""
        u, v, lt = pair.get_output_data()
        if u is None or v is None:
            if not restart_if_running:
                QMessageBox.warning(self, "Missing", f"Load AO{pair.ch_a}/AO{pair.ch_b} pattern first.")
            return
        freq = 1.0 / lt if lt > 0 else 1.0
        was_running = self._is_running
        always_start = not restart_if_running  # Start button always starts
        should_restart = always_start or (restart_if_running and was_running)

        def _send():
            with self.w._lock:
                self.w.load_done.emit("Stopping...")
                self.w._put("WaveGen:Run", 0)
                import time; time.sleep(0.3)
                n = len(u)
                self.w._put("WaveGen:NumPoints", n)
                self.w._put("WaveGen:Frequency", freq)

                self.w.load_done.emit(f"Sending AO{pair.ch_a} ({n})...")
                self.w._put(f"WaveGen:Ch{pair.ch_a}:UserWF", u)
                self.w._put(f"WaveGen:Ch{pair.ch_a}:Amplitude", 1.0)
                self.w._put(f"WaveGen:Ch{pair.ch_a}:Offset", 0.0)
                self.w._put(f"WaveGen:Ch{pair.ch_a}:Enable", 1)

                self.w.load_done.emit(f"Sending AO{pair.ch_b} ({n})...")
                self.w._put(f"WaveGen:Ch{pair.ch_b}:UserWF", v)
                self.w._put(f"WaveGen:Ch{pair.ch_b}:Amplitude", 1.0)
                self.w._put(f"WaveGen:Ch{pair.ch_b}:Offset", 0.0)
                self.w._put(f"WaveGen:Ch{pair.ch_b}:Enable", 1)

                self.w._put("WaveGen:TriggerSource", self.trig_src.currentIndex())

                if should_restart:
                    self.w._put("WaveGen:Continuous", 1)
                    self.w._put("WaveGen:Run", 1)
                    self.w.load_done.emit(f"Running AO{pair.ch_a}/AO{pair.ch_b} ({n} pts)")
                else:
                    self.w.load_done.emit(f"Loaded {n} pts. Press Start.")
        threading.Thread(target=_send, daemon=True).start()

    def _stop(self): self.w.send_stop()

    def _on_status(self, text, running, curpt):
        self.status_l.setText(text); self._is_running = running
        self.plot0.set_running(running)
        self.plot1.set_running(running)

    def _on_load_done(self, msg): self.status_l.setText(msg)

    def pulse_glow(self):
        if not self._dialog_open and self._is_running:
            self.plot0.pulse(); self.plot1.pulse()

    # --- Config ---

    def _save_config(self):
        try:
            try:
                with open(self.cfg_path) as f: cfg=json.load(f)
            except: cfg={}
            cfg["recent_0_1"]=self.pair0._recent
            cfg["recent_2_3"]=self.pair1._recent
            cfg["settings"]={
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
        # Load recent lists for each pair
        self.pair0.load_recent_list(cfg.get("recent_0_1", cfg.get("recent", [])))
        self.pair1.load_recent_list(cfg.get("recent_2_3", []))
        s = cfg.get("settings", {})
        if not s: return
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
