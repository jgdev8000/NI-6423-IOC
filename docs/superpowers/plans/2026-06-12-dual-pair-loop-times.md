# Independent loop times for AO0/1 and AO2/3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let AO0/1 and AO2/3 run at different effective loop times on the single shared AO clock by building one interleaved, integer-ratio-tiled buffer in the Python UI.

**Architecture:** A pure numpy module (`clients/dual_pair_buffer.py`) quantizes the slower pair's period to an integer multiple of the faster (base) period, tiles the faster pair and zero-order-holds the slower pair into a common-length buffer, and returns per-channel arrays plus `NumPoints`/`Frequency`. The UI's `_load`/`_validate_for_load` call it; the C++ driver and EPICS PVs are unchanged.

**Tech Stack:** Python 3, numpy 2.2, stdlib `unittest` (pytest not installed), PyQt6 UI, EPICS Channel Access (`pyepics`).

**Spec:** `docs/superpowers/specs/2026-06-12-dual-pair-loop-times-design.md`

**Test command:** from `clients/`: `python3 -m unittest test_dual_pair_buffer -v`

---

## File structure

- Create: `clients/dual_pair_buffer.py` — pure builder (`zoh_resample`, `build_dual_pair_buffers`, `DualPairResult`). No Qt/EPICS imports.
- Create: `clients/test_dual_pair_buffer.py` — unittest suite for the builder.
- Modify: `clients/tab_waveform.py` — import the builder; rewrite `_validate_for_load` (both-pairs branch) and `_load`.
- Modify: `README.md` — document the quantization/resolution behavior.
- Create: `clients/verify_dual_pair.py` — headless end-to-end check against the live IOC (caput + readback + log scan).

---

### Task 1: ZOH resample helper

**Files:**
- Create: `clients/dual_pair_buffer.py`
- Test: `clients/test_dual_pair_buffer.py`

- [ ] **Step 1: Write the failing test**

```python
# clients/test_dual_pair_buffer.py
import unittest
import numpy as np
from dual_pair_buffer import zoh_resample


class TestZohResample(unittest.TestCase):
    def test_identity_when_same_length(self):
        a = np.array([1.0, 2.0, 3.0])
        out = zoh_resample(a, 3)
        np.testing.assert_array_equal(out, a)

    def test_upsample_holds_each_sample(self):
        out = zoh_resample([10.0, 20.0], 4)
        np.testing.assert_array_equal(out, [10.0, 10.0, 20.0, 20.0])

    def test_downsample_decimates(self):
        out = zoh_resample([1.0, 2.0, 3.0, 4.0], 2)
        np.testing.assert_array_equal(out, [1.0, 3.0])

    def test_non_integer_ratio_uses_floor_index(self):
        out = zoh_resample([0.0, 1.0, 2.0], 5)  # idx = floor(j*3/5)
        np.testing.assert_array_equal(out, [0.0, 0.0, 1.0, 1.0, 2.0])

    def test_empty_input_raises(self):
        with self.assertRaises(ValueError):
            zoh_resample([], 4)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `clients/`): `python3 -m unittest test_dual_pair_buffer -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dual_pair_buffer'`.

- [ ] **Step 3: Write minimal implementation**

```python
# clients/dual_pair_buffer.py
"""Build interleaved AO buffers for two output pairs sharing one AO clock.

The USB-6423 has a single AO sample clock for AO0:3, so the two pairs cannot
have truly independent periods. Each pair's requested loop period is quantized
to an integer multiple of a shared base period (the faster of the two
requested periods, clamped to >= MIN_PERIOD). The faster pair's pattern is
tiled to repeat within the combined buffer; the slower pair's pattern is
stretched across the buffer with a zero-order hold (each native sample held
for an integer number of output ticks).

Effective timing resolution is the base period (>= 0.1 s). Slower periods are
quantized to multiples of the base period via round(period / base).
"""
import numpy as np

MIN_PERIOD = 0.1      # s, minimum allowed loop time and timing resolution
MAX_POINTS = 10000    # per-channel hardware buffer limit (IOC maxPoints)


def zoh_resample(arr, target_len):
    """Zero-order-hold resample a 1D array to target_len samples.

    Upsampling repeats (holds) samples; downsampling decimates. Output index j
    maps to source index floor(j * n / target_len).
    """
    a = np.asarray(arr, dtype=float)
    n = len(a)
    if n == 0:
        raise ValueError("zoh_resample: empty input")
    if target_len == n:
        return a.copy()
    idx = (np.arange(target_len) * n) // target_len
    return a[idx]
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `clients/`): `python3 -m unittest test_dual_pair_buffer -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add clients/dual_pair_buffer.py clients/test_dual_pair_buffer.py
git commit -m "feat(wavegen): add ZOH resample helper for dual-pair buffers"
```

---

### Task 2: Builder core — equal periods, integer ratios, output formulas

**Files:**
- Modify: `clients/dual_pair_buffer.py`
- Test: `clients/test_dual_pair_buffer.py`

- [ ] **Step 1: Write the failing tests**

Append to `clients/test_dual_pair_buffer.py` (after the `TestZohResample` class, before the `if __name__` block):

```python
from dual_pair_buffer import build_dual_pair_buffers, DualPairResult


def _ramp(n):
    return np.arange(n, dtype=float)


class TestBuildDualPair(unittest.TestCase):
    def test_equal_periods_identity(self):
        u0, v0 = _ramp(100), _ramp(100) + 1
        u1, v1 = _ramp(100) + 2, _ramp(100) + 3
        r = build_dual_pair_buffers(u0, v0, 0.1, u1, v1, 0.1)
        self.assertTrue(r.ok)
        self.assertEqual(r.num_points, 100)
        self.assertEqual(r.ticks, (1, 1))
        self.assertAlmostEqual(r.frequency, 10.0)
        self.assertAlmostEqual(r.sample_rate, 1000.0)
        np.testing.assert_array_equal(r.channels[0], u0)
        np.testing.assert_array_equal(r.channels[2], u1)

    def test_channel_order_is_u0_v0_u1_v1(self):
        u0, v0 = _ramp(10), _ramp(10) + 100
        u1, v1 = _ramp(10) + 200, _ramp(10) + 300
        r = build_dual_pair_buffers(u0, v0, 0.1, u1, v1, 0.1)
        np.testing.assert_array_equal(r.channels[0], u0)
        np.testing.assert_array_equal(r.channels[1], v0)
        np.testing.assert_array_equal(r.channels[2], u1)
        np.testing.assert_array_equal(r.channels[3], v1)

    def test_2x_ratio_pair1_slower(self):
        u0, v0 = _ramp(100), _ramp(100)
        u1, v1 = _ramp(100), _ramp(100)
        r = build_dual_pair_buffers(u0, v0, 0.1, u1, v1, 0.2)
        self.assertTrue(r.ok)
        self.assertEqual(r.ticks, (1, 2))
        self.assertEqual(r.num_points, 200)
        self.assertAlmostEqual(r.frequency, 5.0)
        self.assertAlmostEqual(r.sample_rate, 1000.0)
        # fast pair tiled twice
        np.testing.assert_array_equal(r.channels[0], np.tile(u0, 2))
        # slow pair zero-order-held to 200 (each sample doubled)
        np.testing.assert_array_equal(r.channels[2], zoh_resample(u1, 200))

    def test_2x_ratio_pair0_slower_symmetric(self):
        u0, v0 = _ramp(100), _ramp(100)
        u1, v1 = _ramp(100), _ramp(100)
        r = build_dual_pair_buffers(u0, v0, 0.2, u1, v1, 0.1)
        self.assertEqual(r.ticks, (2, 1))
        self.assertEqual(r.num_points, 200)
        np.testing.assert_array_equal(r.channels[2], np.tile(u1, 2))
        np.testing.assert_array_equal(r.channels[0], zoh_resample(u0, 200))

    def test_3x_ratio(self):
        u0 = _ramp(50)
        r = build_dual_pair_buffers(u0, u0, 0.1, u0, u0, 0.3)
        self.assertEqual(r.ticks, (1, 3))
        self.assertEqual(r.num_points, 150)
        self.assertAlmostEqual(r.frequency, 1.0 / 0.3)
        self.assertAlmostEqual(r.sample_rate, 500.0)

    def test_non_integer_ratio_rounds_half_up(self):
        u0 = _ramp(100)
        r = build_dual_pair_buffers(u0, u0, 0.1, u0, u0, 0.15)  # 1.5 -> 2
        self.assertEqual(r.ticks, (1, 2))
        self.assertAlmostEqual(r.eff_periods[1], 0.2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `clients/`): `python3 -m unittest test_dual_pair_buffer -v`
Expected: FAIL — `ImportError: cannot import name 'build_dual_pair_buffers'`.

- [ ] **Step 3: Write the implementation**

Append to `clients/dual_pair_buffer.py`:

```python
from dataclasses import dataclass, field


@dataclass
class DualPairResult:
    ok: bool
    error: str = ""
    channels: list = field(default_factory=list)   # [ch0, ch1, ch2, ch3]
    num_points: int = 0
    frequency: float = 0.0
    sample_rate: float = 0.0
    base_period: float = 0.0
    eff_periods: tuple = (0.0, 0.0)                 # (pair0, pair1)
    ticks: tuple = (1, 1)                           # (pair0, pair1)
    info: str = ""


def build_dual_pair_buffers(u0, v0, p0, u1, v1, p1,
                            min_period=MIN_PERIOD, max_points=MAX_POINTS):
    """Build interleaved-ready per-channel buffers for both AO pairs.

    Returns a DualPairResult. On error (combined length exceeds max_points)
    returns ok=False with a populated .error and no channels.
    """
    u0 = np.asarray(u0, dtype=float); v0 = np.asarray(v0, dtype=float)
    u1 = np.asarray(u1, dtype=float); v1 = np.asarray(v1, dtype=float)

    warns = []
    pr0, pr1 = float(p0), float(p1)
    p0c, p1c = max(min_period, pr0), max(min_period, pr1)
    if p0c != pr0:
        warns.append(f"AO0/1 loop time raised to {p0c:.3f}s (min)")
    if p1c != pr1:
        warns.append(f"AO2/3 loop time raised to {p1c:.3f}s (min)")

    base = min(p0c, p1c)
    ticks0 = max(1, int(p0c / base + 0.5))   # round half up; faster pair -> 1
    ticks1 = max(1, int(p1c / base + 0.5))
    eff0, eff1 = ticks0 * base, ticks1 * base

    S = len(u0) if p0c <= p1c else len(u1)   # native length of faster pair
    kmax = max(ticks0, ticks1)
    L = kmax * S

    if L > max_points:
        return DualPairResult(
            ok=False,
            error=(f"Combined buffer needs {L} points (> {max_points}). "
                   f"Reduce the pattern point count or use a smaller loop-time "
                   f"ratio (current {kmax}x base, {S} pts/base)."))

    def _pair(u, v, ticks, label):
        target = ticks * S
        reps = kmax // ticks
        uu = np.tile(zoh_resample(u, target), reps)
        vv = np.tile(zoh_resample(v, target), reps)
        if len(u) != target:
            warns.append(f"{label} resampled {len(u)}->{target} pts (ZOH)")
        return uu, vv

    ch0, ch1 = _pair(u0, v0, ticks0, "AO0/1")
    ch2, ch3 = _pair(u1, v1, ticks1, "AO2/3")

    frequency = 1.0 / (kmax * base)
    sample_rate = L * frequency
    summary = (f"AO0/1: {eff0:.3f}s ({ticks0}x) | AO2/3: {eff1:.3f}s "
               f"({ticks1}x) | base {base:.3f}s | {L} pts")
    info = summary + ("  [" + "; ".join(warns) + "]" if warns else "")

    return DualPairResult(
        ok=True, channels=[ch0, ch1, ch2, ch3], num_points=L,
        frequency=frequency, sample_rate=sample_rate, base_period=base,
        eff_periods=(eff0, eff1), ticks=(ticks0, ticks1), info=info)
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `clients/`): `python3 -m unittest test_dual_pair_buffer -v`
Expected: PASS (all TestZohResample + TestBuildDualPair tests).

- [ ] **Step 5: Commit**

```bash
git add clients/dual_pair_buffer.py clients/test_dual_pair_buffer.py
git commit -m "feat(wavegen): integer-ratio dual-pair buffer builder"
```

---

### Task 3: Edge cases — reject over-limit, clamp min period, surfaced ZOH warning

**Files:**
- Test: `clients/test_dual_pair_buffer.py`
- (Implementation already present from Task 2; these tests pin the behavior.)

- [ ] **Step 1: Write the failing/﻿pinning tests**

Append a new class to `clients/test_dual_pair_buffer.py` (before the `if __name__` block):

```python
class TestBuildDualPairEdges(unittest.TestCase):
    def test_reject_when_exceeds_max_points(self):
        u0 = _ramp(4000)
        r = build_dual_pair_buffers(u0, u0, 0.1, u0, u0, 0.3)  # L = 3*4000
        self.assertFalse(r.ok)
        self.assertIn("12000", r.error)
        self.assertIn("10000", r.error)
        self.assertEqual(r.channels, [])

    def test_clamp_below_min_period(self):
        u0 = _ramp(100)
        r = build_dual_pair_buffers(u0, u0, 0.05, u0, u0, 0.05)
        self.assertTrue(r.ok)
        self.assertAlmostEqual(r.base_period, 0.1)
        self.assertEqual(r.ticks, (1, 1))
        self.assertIn("raised to 0.100s", r.info)

    def test_clamp_one_side_changes_ratio(self):
        u0 = _ramp(100)
        r = build_dual_pair_buffers(u0, u0, 0.05, u0, u0, 0.2)  # 0.05->0.1 base
        self.assertAlmostEqual(r.base_period, 0.1)
        self.assertEqual(r.ticks, (1, 2))

    def test_equal_period_unequal_points_resamples_and_warns(self):
        u0 = _ramp(100)
        u1 = _ramp(50)
        r = build_dual_pair_buffers(u0, u0, 0.1, u1, u1, 0.1)
        self.assertTrue(r.ok)
        self.assertEqual(r.num_points, 100)            # S = pair0 length
        self.assertEqual(len(r.channels[2]), 100)
        self.assertIn("AO2/3 resampled 50->100", r.info)
        np.testing.assert_array_equal(r.channels[2], zoh_resample(u1, 100))

    def test_at_limit_is_accepted(self):
        u0 = _ramp(5000)
        r = build_dual_pair_buffers(u0, u0, 0.1, u0, u0, 0.2)  # L = 2*5000
        self.assertTrue(r.ok)
        self.assertEqual(r.num_points, 10000)
```

- [ ] **Step 2: Run tests**

Run (from `clients/`): `python3 -m unittest test_dual_pair_buffer -v`
Expected: PASS (these exercise the Task 2 implementation; if any fail, fix the builder, not the test).

- [ ] **Step 3: Commit**

```bash
git add clients/test_dual_pair_buffer.py
git commit -m "test(wavegen): pin reject/clamp/resample edge cases"
```

---

### Task 4: Wire the builder into the UI (`_validate_for_load`, `_load`)

**Files:**
- Modify: `clients/tab_waveform.py` (import; `_validate_for_load` both-pairs branch ~`694-697`; `_load` ~`456-512`)

This task is Qt/EPICS-coupled, so verification is import-smoke + the live check in Task 6 (the math is already covered by Tasks 1-3).

- [ ] **Step 1: Add the import**

Near the top of `clients/tab_waveform.py`, next to `from waveform_filter import waveform_filter, load_mat_pattern` (line ~10), add:

```python
from dual_pair_buffer import build_dual_pair_buffers
```

- [ ] **Step 2: Replace the both-pairs branch of `_validate_for_load`**

Find this block (the two hard rejections):

```python
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
```

Replace it with:

```python
        if pair1_loaded:
            pair1_ok, pair1_msg = self._validate_pair(self.pair1)
            if not pair1_ok:
                return False, pair1_msg
            # Different loop times / point counts are allowed: the builder
            # quantizes the slower pair to an integer multiple of the faster
            # pair's period on the shared AO clock (ZOH). Reject only when the
            # combined buffer will not fit the hardware buffer.
            u0, v0, lt0 = self.pair0.get_output_data()
            u1, v1, lt1 = self.pair1.get_output_data()
            res = build_dual_pair_buffers(u0, v0, lt0, u1, v1, lt1)
            if not res.ok:
                return False, res.error
            return True, "Validation: " + res.info
```

- [ ] **Step 3: Rewrite `_load` to build combined buffers**

Replace the entire `_load` method (from `def _load(self, auto_restart=False):` through the `threading.Thread(target=_send, daemon=True).start()` and `self._save_config()` lines) with:

```python
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

        # When both pairs are loaded they share one AO clock; build one
        # integer-ratio-tiled buffer (slower pair zero-order-held). A single
        # loaded pair keeps the simple one-rate path.
        both = u1 is not None and v1 is not None
        if both:
            res = build_dual_pair_buffers(u0, v0, lt0, u1, v1, lt1)
            if not res.ok:
                self.validation_l.setText(res.error)
                self.validation_l.setStyleSheet("color:#ef5350;")
                if not auto_restart:
                    QMessageBox.warning(self, "Invalid waveform setup", res.error)
                return
            chans = res.channels
            num_points = res.num_points
            freq = res.frequency
        else:
            num_points = len(u0)
            freq = 1.0 / lt0 if lt0 > 0 else 1.0

        def _send():
            with self.w._lock:
                ok = True
                self.w.load_done.emit("Stopping...")
                ok = self.w._put("WaveGen:Run", 0) and ok
                import time; time.sleep(0.3)

                ok = self.w._put("WaveGen:NumPoints", num_points) and ok
                ok = self.w._put("WaveGen:Frequency", freq) and ok
                ok = self.w._put("WaveGen:MarkerEnable", 1) and ok
                ok = self.w._put("WaveGen:MarkerWidth", 10) and ok

                if both:
                    self.w.load_done.emit(f"Sending AO0..3 ({num_points})...")
                    for ch in range(4):
                        ok = self.w._put(f"WaveGen:Ch{ch}:UserWF", chans[ch]) and ok
                        ok = self.w._put(f"WaveGen:Ch{ch}:Amplitude", 1.0) and ok
                        ok = self.w._put(f"WaveGen:Ch{ch}:Offset", 0.0) and ok
                        ok = self.w._put(f"WaveGen:Ch{ch}:Enable", 1) and ok
                else:
                    self.w.load_done.emit(f"Sending AO0/AO1 ({num_points})...")
                    ok = self.w._put("WaveGen:Ch0:UserWF", u0) and ok
                    ok = self.w._put("WaveGen:Ch0:Amplitude", 1.0) and ok
                    ok = self.w._put("WaveGen:Ch0:Offset", 0.0) and ok
                    ok = self.w._put("WaveGen:Ch0:Enable", 1) and ok
                    ok = self.w._put("WaveGen:Ch1:UserWF", v0) and ok
                    ok = self.w._put("WaveGen:Ch1:Amplitude", 1.0) and ok
                    ok = self.w._put("WaveGen:Ch1:Offset", 0.0) and ok
                    ok = self.w._put("WaveGen:Ch1:Enable", 1) and ok
                    ok = self.w._put("WaveGen:Ch2:Enable", 0) and ok
                    ok = self.w._put("WaveGen:Ch3:Enable", 0) and ok

                ok = self.w._put("WaveGen:TriggerSource", self.trig_src.currentIndex()) and ok
                ok = self.w._put("WaveGen:TriggerEdge", 0) and ok

                if auto_restart and self._is_running and ok:
                    ok = self.w._put("WaveGen:Continuous", 1) and ok
                    ok = self.w._put("WaveGen:Run", 1) and ok
                    self.w.load_done.emit(f"Running ({num_points} pts)" if ok else "Waveform load failed")
                else:
                    self.w.load_done.emit(f"Loaded {num_points} pts. Press Start." if ok else "Waveform load failed")
        threading.Thread(target=_send, daemon=True).start()

        # Save config after loading
        self._save_config()
```

> Note: `get_output_data()` already applies per-pair scale/offset/filter, so amplitude/offset stay 1.0/0.0 (the data is pre-baked), exactly as before.

- [ ] **Step 4: Smoke-check the import compiles**

Run (from `clients/`): `python3 -c "import ast; ast.parse(open('tab_waveform.py').read()); print('syntax ok')"`
Expected: `syntax ok`.

(A full `import tab_waveform` pulls in PyQt6/pyepics; the byte-compile check below is the headless gate.)

Run: `python3 -m py_compile clients/tab_waveform.py && echo compiled`
Expected: `compiled`.

- [ ] **Step 5: Commit**

```bash
git add clients/tab_waveform.py
git commit -m "feat(wavegen): UI builds dual-pair integer-ratio AO buffer on load"
```

---

### Task 5: Document the behavior in the README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a subsection**

Add the following near the waveform-generator section of `README.md` (append to the end of the file if no such section exists):

```markdown
### AO0/1 and AO2/3 loop times

AO0:3 share a single hardware sample clock, so the two pairs cannot run at
arbitrary independent periods. The UI quantizes them to an integer ratio:

- The faster of the two requested loop times becomes the **base period**
  (minimum 0.1 s, which is also the timing resolution).
- The slower pair's period is rounded to the nearest integer multiple of the
  base period: `ticks = round(period / base)` (minimum 1). Its effective
  period is `ticks x base` and is shown in the validation label.
- The faster pair's pattern is tiled to repeat within the combined buffer; the
  slower pair's pattern is stretched across it with a **zero-order hold** (each
  native sample held for `ticks` output samples).
- If the combined buffer would exceed 10000 points the load is rejected; reduce
  the point count or use a smaller ratio.

Equal loop times update all four channels together (original behavior).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: explain AO0/1 vs AO2/3 integer-ratio loop times"
```

---

### Task 6: Live end-to-end verification against the IOC

**Files:**
- Create: `clients/verify_dual_pair.py`

Verifies a 2x-ratio load over Channel Access: pushes builder output to the IOC,
starts it, confirms `NumPoints`/`Frequency` readback and that no `-200802` (or
other) DAQmx error appears in the IOC log. Requires the IOC running (procServ)
and `caput`/`caget` on PATH (`/opt/epics/base/bin/linux-x86_64`).

- [ ] **Step 1: Create the verification script**

```python
# clients/verify_dual_pair.py
"""Live IOC check for dual-pair integer-ratio loading. Run with the IOC up."""
import subprocess, sys, time, os
import numpy as np
from dual_pair_buffer import build_dual_pair_buffers

PREFIX = "MEMS:"
LOG = "/var/log/iocs/nidaq.log"
CAPUT = "/opt/epics/base/bin/linux-x86_64/caput"
CAGET = "/opt/epics/base/bin/linux-x86_64/caget"


def caput(pv, val, array=False):
    args = [CAPUT, "-w", "6"]
    if array:
        args += ["-a", PREFIX + pv, str(len(val))] + [repr(float(x)) for x in val]
    else:
        args += [PREFIX + pv, str(val)]
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)


def caget(pv):
    out = subprocess.check_output([CAGET, "-t", PREFIX + pv]).decode().strip()
    return out


def errcount():
    if not os.path.exists(LOG):
        return 0
    return sum(1 for ln in open(LOG, errors="ignore") if "200802" in ln)


def main():
    u = np.sin(np.linspace(0, 2 * np.pi, 100, endpoint=False))
    r = build_dual_pair_buffers(u, u, 0.1, u, u, 0.2)
    assert r.ok, r.error
    assert r.num_points == 200 and abs(r.frequency - 5.0) < 1e-9, r.info

    before = errcount()
    caput("WaveGen:Run", 0); time.sleep(0.3)
    caput("WaveGen:NumPoints", r.num_points)
    caput("WaveGen:Frequency", r.frequency)
    for ch in range(4):
        caput(f"WaveGen:Ch{ch}:UserWF", r.channels[ch], array=True)
        caput(f"WaveGen:Ch{ch}:Enable", 1)
    caput("WaveGen:Continuous", 1)
    caput("WaveGen:Run", 1)
    time.sleep(0.5)

    run = caget("WaveGen:Run")
    npts = caget("WaveGen:NumPoints")
    after = errcount()
    caput("WaveGen:Run", 0)

    print(f"info       : {r.info}")
    print(f"Run        : {run}")
    print(f"NumPoints  : {npts} (expect 200)")
    print(f"-200802 new: {after - before} (expect 0)")
    ok = (run == "Run" and npts == "200" and after == before)
    print("RESULT     :", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it against the live IOC**

Run (from `clients/`): `python3 verify_dual_pair.py`
Expected: `RESULT     : PASS` (Run=Run, NumPoints=200, 0 new -200802 errors).

- [ ] **Step 3: Commit**

```bash
git add clients/verify_dual_pair.py
git commit -m "test(wavegen): live IOC verification for dual-pair load"
```

---

## Self-review

**Spec coverage:**
- Separate loop-time fields kept → Task 4 (fields untouched; validation/load updated). ✓
- Min loop time 0.1 s → Task 2 clamp + Task 3 tests. ✓
- Equal loop times update together → Task 2 `test_equal_periods_identity`. ✓
- Differing loop times: faster base, slower repeated/held → Task 2 ratio tests, ZOH in Task 1. ✓
- Integer-ratio `round(period/base)`, min 1 tick → Task 2 (`int(x+0.5)`), `test_non_integer_ratio_rounds_half_up`. ✓
- One continuous AO task, interleaved AO0:3 → unchanged driver; Task 4 sends 4 channels + `Continuous=1`. ✓
- No independent clocks / no second task → guardrails; no driver/PV changes. ✓
- `Frequency = 1/(kmax*base)`, `NumPoints = L`, `sample_rate = L*Frequency` → Task 2 formulas + tests. ✓
- Reject `L > MAX_POINTS` → Task 2 + `test_reject_when_exceeds_max_points`. ✓
- Surfaced ZOH for equal-period/unequal-points → Task 3 `test_equal_period_unequal_points_resamples_and_warns`. ✓
- Document 0.1 s resolution + quantization → Task 5. ✓
- Preserve EPICS/channel naming + single-pair behavior → Task 4 keeps single-pair path and PV names. ✓

**Placeholder scan:** none — all steps contain runnable code/commands.

**Type/name consistency:** `build_dual_pair_buffers`, `zoh_resample`, `DualPairResult` and its fields (`ok`, `error`, `channels`, `num_points`, `frequency`, `sample_rate`, `base_period`, `eff_periods`, `ticks`, `info`) are used identically across Tasks 1-6.

