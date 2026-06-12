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
