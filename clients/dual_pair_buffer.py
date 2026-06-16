# clients/dual_pair_buffer.py
"""Build interleaved AO buffers for two output pairs sharing one AO clock.

The USB-6423 has a single AO sample clock for AO0:3, so the two pairs cannot
have truly independent periods. Each pair's requested loop period is quantized
to an integer multiple of a shared base period (the faster of the two
requested periods). The faster pair's pattern is tiled to repeat within the
combined buffer; the slower pair's pattern is stretched across the buffer with
a zero-order hold (each native sample held for an integer number of ticks).

The minimum loop time is set by the hardware AO sample rate, not a fixed
floor: a pair of N points cannot loop faster than N / MAX_AO_RATE seconds
(e.g. 1000 pts / 250 kS/s = 4 ms). A request faster than that is raised to the
hardware minimum and reported.
"""
import numpy as np
from dataclasses import dataclass, field

MAX_AO_RATE = 250000.0  # S/s - USB-6423 AO sample-clock max (all 4 AO channels share it)
MIN_PERIOD = 1.0 / MAX_AO_RATE  # s - absolute floor; real per-pair limit is points/MAX_AO_RATE
MAX_POINTS = 10000    # per-channel hardware buffer limit (IOC maxPoints)


def _fmt_period(p):
    """Human-friendly period string: ms below 1 s, else s."""
    return f"{p * 1000:.3f} ms" if p < 1.0 else f"{p:.4f} s"


def zoh_resample(arr, target_len):
    """Zero-order-hold resample a 1D array to target_len samples.

    Upsampling repeats (holds) samples; downsampling decimates. Output index j
    maps to source index floor(j * n / target_len). If target_len is 1, the
    first input sample is returned.
    """
    a = np.asarray(arr, dtype=float)
    n = len(a)
    if n == 0:
        raise ValueError("zoh_resample: empty input")
    if target_len <= 0:
        raise ValueError(f"zoh_resample: target_len must be positive, got {target_len}")
    if target_len == n:
        return a.copy()
    idx = (np.arange(target_len) * n) // target_len
    return a[idx]


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
                            max_points=MAX_POINTS, max_ao_rate=MAX_AO_RATE):
    """Build interleaved-ready per-channel buffers for both AO pairs.

    Returns a DualPairResult. On error (combined length exceeds max_points)
    returns ok=False with a populated .error and no channels.

    The minimum loop time per pair is N_points / max_ao_rate (the device can't
    output samples faster than its AO sample clock); faster requests are raised
    to that hardware minimum.
    """
    u0 = np.asarray(u0, dtype=float); v0 = np.asarray(v0, dtype=float)
    u1 = np.asarray(u1, dtype=float); v1 = np.asarray(v1, dtype=float)

    for nm, arr in (("u0", u0), ("v0", v0), ("u1", u1), ("v1", v1)):
        if len(arr) == 0:
            return DualPairResult(ok=False, error=f"{nm} is empty")

    warns = []
    pr0, pr1 = float(p0), float(p1)
    # Hardware minimum loop time per pair: N points cannot be output faster than
    # the device AO sample rate, i.e. loop_time >= N / max_ao_rate.
    hwmin0 = max(MIN_PERIOD, len(u0) / max_ao_rate)
    hwmin1 = max(MIN_PERIOD, len(u1) / max_ao_rate)
    p0c, p1c = max(hwmin0, pr0), max(hwmin1, pr1)
    if p0c > pr0:
        warns.append(f"AO0/1 loop time raised to {_fmt_period(p0c)} "
                     f"({len(u0)} pts @ max {max_ao_rate / 1000:.0f} kS/s)")
    if p1c > pr1:
        warns.append(f"AO2/3 loop time raised to {_fmt_period(p1c)} "
                     f"({len(u1)} pts @ max {max_ao_rate / 1000:.0f} kS/s)")

    base = min(p0c, p1c)
    ticks0 = max(1, int(p0c / base + 0.5 + 1e-9))   # round half up; faster pair -> 1
    ticks1 = max(1, int(p1c / base + 0.5 + 1e-9))
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
    summary = (f"AO0/1: {_fmt_period(eff0)} ({ticks0}x) | "
               f"AO2/3: {_fmt_period(eff1)} ({ticks1}x) | "
               f"base {_fmt_period(base)} | {L} pts @ {sample_rate / 1000:.1f} kS/s")
    info = summary + ("  [" + "; ".join(warns) + "]" if warns else "")

    return DualPairResult(
        ok=True, channels=[ch0, ch1, ch2, ch3], num_points=L,
        frequency=frequency, sample_rate=sample_rate, base_period=base,
        eff_periods=(eff0, eff1), ticks=(ticks0, ticks1), info=info)
