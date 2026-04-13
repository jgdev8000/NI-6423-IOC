"""
Waveform filter for MEMS scan patterns.
Python port of waveformfilter.m

Applies a Gaussian lowpass filter in the frequency domain.
"""

import numpy as np


def waveform_filter(wf, loop_time, cutoff_hz):
    """
    Lowpass filter for scan patterns.

    Args:
        wf: 1D array of waveform values
        loop_time: loop time in seconds
        cutoff_hz: cutoff frequency in Hz

    Returns:
        Filtered waveform array
    """
    n = len(wf)
    wf_shifted = wf + 10.0

    limit = cutoff_hz * loop_time

    t = np.arange(1, n + 1) - (n / 2)
    t = 1.7 * t / limit

    filt = np.exp(-t ** 2)
    # Swap halves to match FFT frequency ordering
    filt = np.concatenate([filt[n // 2:], filt[:n // 2]])

    fs = np.fft.fft(wf_shifted) * filt
    wff = np.abs(np.fft.ifft(fs)) - 10.0

    return wff


def load_mat_pattern(filepath):
    """
    Load a .mat file containing a scan pattern.
    Expects a 2-column array (x, y) as the first non-system variable.

    Returns:
        (ao0_data, ao1_data) as 1D numpy arrays
    """
    import scipy.io
    data = scipy.io.loadmat(filepath)
    for key, val in data.items():
        if key.startswith('_'):
            continue
        if hasattr(val, 'shape') and len(val.shape) == 2 and val.shape[1] >= 2:
            return val[:, 0].astype(np.float64), val[:, 1].astype(np.float64)
    raise ValueError(f"No 2-column array found in {filepath}")
