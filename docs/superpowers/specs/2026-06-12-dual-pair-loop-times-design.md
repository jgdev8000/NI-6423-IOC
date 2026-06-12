# Independent loop times for AO0/1 and AO2/3 (integer-ratio buffer tiling)

**Date:** 2026-06-12
**Branch:** `feature/dual-pair-loop-times`
**Status:** Approved design

## Problem

The waveform UI exposes separate loop-time fields for the two AO pairs
(AO0/1 and AO2/3), but the IOC drives all four AO channels from a single
hardware AO sample clock. Today the UI forces both pairs to use the same
loop time and the same number of points (`tab_waveform.py` `_validate_for_load`),
so the two pairs cannot run at different periods.

The NI USB-6423 has **one** AO sample clock shared by AO0:3 — independent
hardware AO clocks / separate hardware-timed AO tasks are not possible. The
goal is to let the two pairs run at different *effective* loop periods on
that single shared clock, using integer-ratio quantization.

## Constraints / decisions

- **One continuous, regenerating hardware-timed AO task** with all four
  channels interleaved (AO0, AO1, AO2, AO3) — this is what the driver
  already does; no second task, no streaming thread.
- **Logic lives in the Python UI**, not the C++ driver. The driver already
  accepts an independent waveform per channel (`WaveGen:Ch{n}:UserWF`, up to
  `MAX_POINTS = 10000` each) and interleaves all enabled channels into one
  continuous AO task of length `NumPoints`. **No C++ changes, no new EPICS
  records/PVs, channel naming preserved.**
- **Minimum loop time = 0.1 s.** Timing resolution equals the base period;
  this is the effective resolution of the whole feature.
- **Slower pair fill = zero-order hold (ZOH)** — each native sample of the
  slower pair is held/repeated to span its longer period ("repeat/hold
  previous values").
- **Integer-ratio quantization**: `ticks = round(period / base_period)`,
  minimum 1. Slower periods are quantized to integer multiples of the base
  (faster) period.

## IOC `Frequency` semantics (confirmed)

`Frequency` is the **waveform-cycle (buffer repeat) frequency**, NOT the
sample rate. Confirmed in `nidaqApp/src/drvNiDAQMEMS.cpp`:

- `requestedSampleRate = frequency * numPoints;` (line 368) →
  **sample_rate = NumPoints × Frequency**
- `actualFrequency = actualSampleRate / numPoints;` (line 462, readback)
- monitor thread `sampleRate = frequency * numPoints;` (line 516, drives `CurrentPoint`)

Therefore the UI sets `NumPoints = L` and `Frequency = 1/(kmax × base)`, and
the IOC reconstructs `effective sample rate R = NumPoints × Frequency = L × Frequency`.

## Algorithm (pure function)

Inputs: pair0 `(u0, v0, P0)`, pair1 `(u1, v1, P1)`; `MIN_PERIOD = 0.1`,
`MAX_POINTS = 10000`. `N0/N1` are the native point counts of each pair's
loaded pattern.

1. Clamp each period to ≥ `MIN_PERIOD` (0.1 s).
2. `base = min(P0, P1)` — the faster period (also ≥ 0.1 s).
3. `ticks_i = max(1, round(P_i / base))` — faster pair → 1, slower pair → k.
   **Effective period of pair i = `ticks_i × base`** (quantized; may differ
   from requested and is surfaced to the user).
4. `S` = native point count of the faster pair (the pair with `ticks == 1`;
   on a tie / equal periods, use pair0's `N0`).
5. `kmax = max(ticks0, ticks1)`.
6. **`L = kmax × S`** (combined buffer length, common to all four channels).
7. **If `L > MAX_POINTS`: reject** with an error message naming `L` and
   suggesting the user reduce the point count or use a smaller ratio. No
   silent downsampling. (Explicit opt-in downsampling may be a later feature.)
8. For each pair `i`:
   - `target_len = ticks_i × S` (one full playback length on the shared clock).
   - ZOH-resample the pair's native `(u, v)` from `N_i` to `target_len`
     (each native sample held an integer/near-integer number of output ticks).
   - Tile `kmax / ticks_i` times → length `L`. (Faster pair, ticks=1, tiles
     `kmax` times; slower pair, ticks=kmax, tiles once.) `kmax / ticks_i` is
     always an integer because the faster pair has `ticks == 1`, so
     `kmax` is a multiple of every `ticks_i` in the two-pair case.
9. Channel mapping: `ch0 = tiled u0`, `ch1 = tiled v0`, `ch2 = tiled u1`,
   `ch3 = tiled v1`, each length `L`.
10. Output parameters: `NumPoints = L`, `Frequency = 1/(kmax × base)`
    (= 1 / slowest-effective-period). Effective sample rate
    `R = L × Frequency = S / base`.

The function returns the four channel buffers, `NumPoints`, `Frequency`, the
two effective periods, the base period, and a human-readable info/warning
string (e.g. resample notices). On rejection it returns an error string and
no buffers.

### Worked examples

- **Equal periods** (P0=P1=0.1 s, N0=N1=100): base=0.1, ticks {1,1}, S=100,
  kmax=1, L=100, Frequency=10 Hz, R=1000 S/s. All four channels update
  together — identical to today's behavior.
- **2× ratio** (P0=0.1, P1=0.2, N0=N1=100): base=0.1, ticks {1,2}, S=100,
  kmax=2, L=200, Frequency=5 Hz, R=1000 S/s. AO0/1 plays its pattern twice
  per buffer; AO2/3 plays once with each native sample held 2×.
- **Equal periods, unequal points** (P0=P1=0.1, N0=100, N1=50): tie → S=N0=100;
  AO2/3 ZOH-resampled 50→100, surfaced in the validation label.
- **Exceeds limit** (S=4000, kmax=3 → L=12000 > 10000): rejected with message.

## UI changes (`clients/tab_waveform.py`)

- Keep both per-pair loop-time fields (already present).
- Clamp entered loop times to ≥ 0.1 s; note when a value was clamped.
- In `_validate_for_load`: **remove** the "same number of points" and "same
  loop time" rejections. Instead run the builder; reject only when the builder
  reports an error (e.g. `L > MAX_POINTS`).
- `_load()` (both pairs): call the builder, send the four channel buffers via
  the existing `WaveGen:Ch{0..3}:UserWF` PVs, set `NumPoints` and `Frequency`,
  `Continuous = 1`, then `Run`.
- Validation/status label shows **effective (quantized) periods**, the base
  resolution, and any resample warning, e.g.
  *"AO0/1: 0.100 s | AO2/3: 0.200 s (2× base) | base 0.100 s"* and
  *"AO2/3 resampled 50→100 pts to match AO0/1 (equal loop time)."*
- `_load_pair()` (single pair, disables the other pair) is unchanged in spirit:
  a single active pair has ticks=1 and behaves as today.

## New module + tests

- New `clients/dual_pair_buffer.py` containing the pure builder function
  (numpy only — no Qt, no EPICS), so it is unit-testable in isolation.
- Tests (TDD) cover: equal periods (identity / today's behavior), 2× and 3×
  ratios, sub-0.1 s clamping, `L > MAX_POINTS` rejection, ZOH correctness,
  channel mapping, and the equal-period/unequal-points ZOH-resample +
  surfaced warning.

## Documentation

- Docstring on the builder + a short note in the UI/README stating: timing
  resolution equals the base period (≥ 0.1 s); the slower pair's period is
  quantized to an integer multiple of the faster pair's period
  (`round(P/base)`), and slower-pair samples are zero-order-held. Truly
  independent / arbitrary periods are not possible (single shared AO clock).

## Out of scope (guardrails)

- No new EPICS records/PVs; no C++ driver changes.
- No second AO task; no software-streaming generation thread.
- No independent hardware AO clocks.
- Existing single-pair Start and stop/park behavior preserved.
- Opt-in downsampling for `L > MAX_POINTS` is explicitly deferred.
