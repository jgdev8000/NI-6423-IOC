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
    summary = (f"AO0/1: {eff0:.3f}s ({ticks0}x) | AO2/3: {eff1:.3f}s "
               f"({ticks1}x) | base {base:.3f}s | {L} pts")
    info = summary + ("  [" + "; ".join(warns) + "]" if warns else "")

    return DualPairResult(
        ok=True, channels=[ch0, ch1, ch2, ch3], num_points=L,
        frequency=frequency, sample_rate=sample_rate, base_period=base,
        eff_periods=(eff0, eff1), ticks=(ticks0, ticks1), info=info)
