"""EPICS Channel Access worker — all CA calls in background threads."""
import os, threading
os.environ.setdefault("EPICS_CA_MAX_ARRAY_BYTES", "100000")

from PyQt6.QtCore import QObject, pyqtSignal

PREFIX = "MEMS:"

class EpicsWorker(QObject):
    status_update = pyqtSignal(str, bool, int)
    load_done = pyqtSignal(str)
    operation_error = pyqtSignal(str)
    ai_update = pyqtSignal(list)
    ao_state = pyqtSignal(dict)
    dio_update = pyqtSignal(dict)
    ctr_update = pyqtSignal(dict)
    wavegen_state = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._epics = None
        self._lock = threading.Lock()
        self._stopping = False
        threading.Thread(target=self._init, daemon=True).start()

    def _init(self):
        import epics
        self._epics = epics

    def _get(self, pv, **kw):
        if not self._epics: return None
        try: return self._epics.caget(f"{PREFIX}{pv}", timeout=1.0, **kw)
        except: return None

    def _put(self, pv, value):
        if not self._epics:
            self.operation_error.emit(f"Write failed: {PREFIX}{pv} (EPICS not initialized)")
            return False
        try:
            result = self._epics.caput(f"{PREFIX}{pv}", value, wait=True, timeout=5.0)
            if result is False or result is None:
                self.operation_error.emit(f"Write failed: {PREFIX}{pv}")
                return False
            return True
        except Exception as exc:
            self.operation_error.emit(f"Write failed: {PREFIX}{pv} ({exc})")
            return False

    def _bg(self, fn):
        if self._stopping:
            return
        threading.Thread(target=fn, daemon=True).start()

    def shutdown(self):
        self._stopping = True

    def poll_status(self):
        def _do():
            run = self._get("WaveGen:Run", as_string=True)
            freq = self._get("WaveGen:Frequency")
            dwell = self._get("WaveGen:Dwell")
            tt = self._get("WaveGen:TotalTime")
            npts = self._get("WaveGen:NumPoints")
            curpt = self._get("WaveGen:CurrentPoint")
            if run is None:
                self.status_update.emit("Not connected", False, 0)
                return
            loop = tt if tt and tt > 0 else (1.0/freq if freq and freq > 0 else 0)
            dwell_us = dwell*1e6 if dwell and dwell > 0 else (loop/npts*1e6 if npts and npts > 0 else 0)
            text = f"loop: {loop:.4f}s | {npts} pts | {dwell_us:.1f} us/pt"
            self.status_update.emit(text, run == "Run", int(curpt or 0))
        self._bg(_do)

    def poll_wavegen_state(self):
        def _do():
            state = {
                "frequency": self._get("WaveGen:Frequency"),
                "num_points": self._get("WaveGen:NumPoints"),
                "trigger_source": self._get("WaveGen:TriggerSource"),
                "trigger_edge": self._get("WaveGen:TriggerEdge"),
            }
            self.wavegen_state.emit(state)
        self._bg(_do)

    def poll_ai(self):
        def _do():
            vals = []
            for i in range(32):
                v = self._get(f"AI:{i}:Value")
                vals.append(v if v is not None else 0.0)
            self.ai_update.emit(vals)
        self._bg(_do)

    def poll_dio(self):
        def _do():
            state = {"inputs": [], "directions": [], "outputs": []}
            for i in range(16):
                d = self._get(f"DIO:{i}:In")
                direction = self._get(f"DIO:{i}:Direction")
                out = self._get(f"DIO:{i}:Out")
                state["inputs"].append(int(d) if d is not None else 0)
                state["directions"].append(int(direction) if direction is not None else 0)
                state["outputs"].append(int(out) if out is not None else 0)
            self.dio_update.emit(state)
        self._bg(_do)

    def poll_ctr(self):
        def _do():
            counters = []
            for ctr in range(4):
                count = self._get(f"Ctr:{ctr}:Count")
                freq = self._get(f"Ctr:{ctr}:Frequency")
                mode = self._get(f"Ctr:{ctr}:Mode")
                pulse_freq = self._get(f"Ctr:{ctr}:PulseFreq")
                pulse_duty = self._get(f"Ctr:{ctr}:PulseDuty")
                pulse_run = self._get(f"Ctr:{ctr}:PulseRun")
                counters.append({
                    "ctr": ctr,
                    "count": int(count or 0),
                    "freq": float(freq or 0.0),
                    "mode": int(mode or 0),
                    "pulse_freq": float(pulse_freq or 0.0),
                    "pulse_duty": float(pulse_duty or 0.0),
                    "pulse_run": bool(pulse_run),
                })
            self.ctr_update.emit({"counters": counters})
        self._bg(_do)

    def poll_ao(self):
        def _do():
            run = self._get("WaveGen:Run", as_string=True)
            freq = self._get("WaveGen:Frequency")
            npts = self._get("WaveGen:NumPoints")
            channels = []
            enabled = []
            cards = []

            for i in range(4):
                en = self._get(f"WaveGen:Ch{i}:Enable")
                amp = self._get(f"WaveGen:Ch{i}:Amplitude")
                off = self._get(f"WaveGen:Ch{i}:Offset")
                wf = self._get(f"WaveGen:Ch{i}:UserWF")
                enabled_flag = bool(en)
                enabled.append(enabled_flag)
                channels.append(wf)
                cards.append({
                    "enable": enabled_flag,
                    "amplitude": float(amp or 0.0),
                    "offset": float(off or 0.0),
                    "points": len(wf) if wf is not None and hasattr(wf, "__len__") else 0,
                })

            self.ao_state.emit({
                "run": run or "--",
                "frequency": float(freq or 0.0),
                "num_points": int(npts or 0),
                "channels": channels,
                "enabled": enabled,
                "cards": cards,
            })
        self._bg(_do)

    def send_start(self):
        self._bg(lambda: (self._put("WaveGen:Continuous", 1), self._put("WaveGen:Run", 1)))

    def send_stop(self):
        self._bg(lambda: self._put("WaveGen:Run", 0))

    def send_loop_time(self, freq):
        def _do():
            was = self._get("WaveGen:Run")
            if was: self._put("WaveGen:Run", 0)
            self._put("WaveGen:Frequency", freq)
            if was: self._put("WaveGen:Run", 1)
        self._bg(_do)

    def send_waveforms(self, u, v, su, sv, ou, ov, freq, me, mw, restart=False):
        def _do():
            with self._lock:
                self.load_done.emit("Stopping...")
                self._put("WaveGen:Run", 0)
                import time; time.sleep(0.3)
                self._put("WaveGen:Ch0:Amplitude", su)
                self._put("WaveGen:Ch1:Amplitude", sv)
                self._put("WaveGen:Ch0:Offset", ou)
                self._put("WaveGen:Ch1:Offset", ov)
                self._put("WaveGen:Frequency", freq)
                self._put("WaveGen:MarkerEnable", int(me))
                self._put("WaveGen:MarkerWidth", int(mw))
                n = len(u)
                self._put("WaveGen:NumPoints", n)
                self.load_done.emit(f"Sending AO0 ({n})...")
                self._put("WaveGen:Ch0:UserWF", u)
                self.load_done.emit(f"Sending AO1 ({n})...")
                self._put("WaveGen:Ch1:UserWF", v)
                if restart:
                    self._put("WaveGen:Continuous", 1)
                    self._put("WaveGen:Run", 1)
                    self.load_done.emit(f"Running ({n} pts)")
                else:
                    self.load_done.emit(f"Loaded {n} pts. Press Start.")
        self._bg(_do)

    def send_settings(self, su, sv, ou, ov, freq, me, mw):
        def _do():
            self._put("WaveGen:Ch0:Amplitude", su)
            self._put("WaveGen:Ch1:Amplitude", sv)
            self._put("WaveGen:Ch0:Offset", ou)
            self._put("WaveGen:Ch1:Offset", ov)
            self._put("WaveGen:Frequency", freq)
            self._put("WaveGen:MarkerEnable", int(me))
            self._put("WaveGen:MarkerWidth", int(mw))
        self._bg(_do)

    def send_dio(self, line, value):
        self._bg(lambda: self._put(f"DIO:{line}:Out", int(value)))

    def send_dio_dir(self, line, direction):
        self._bg(lambda: self._put(f"DIO:{line}:Direction", int(direction)))

    def send_ctr_mode(self, ctr, mode):
        self._bg(lambda: self._put(f"Ctr:{ctr}:Mode", mode))

    def send_ctr_reset(self, ctr):
        self._bg(lambda: self._put(f"Ctr:{ctr}:Reset", 1))

    def send_ctr_pulse(self, ctr, freq, duty, run):
        def _do():
            self._put(f"Ctr:{ctr}:PulseFreq", freq)
            self._put(f"Ctr:{ctr}:PulseDuty", duty)
            self._put(f"Ctr:{ctr}:PulseRun", int(run))
        self._bg(_do)

    def send_ai_acq(self, rate, npts, trig, clk):
        def _do():
            self._put("AIAcq:Rate", rate)
            self._put("AIAcq:NumPoints", npts)
            self._put("AIAcq:TriggerSource", trig)
            self._put("AIAcq:ClockSource", clk)
            self._put("AIAcq:Run", 1)
        self._bg(_do)

    def send_trigger(self, src, edge):
        def _do():
            self._put("WaveGen:TriggerSource", src)
            self._put("WaveGen:TriggerEdge", edge)
        self._bg(_do)
