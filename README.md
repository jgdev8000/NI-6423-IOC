# MEMS Waveform Generator IOC

EPICS IOC for driving MEMS scanning mirrors via National Instruments DAQ hardware. Generates synchronized, hardware-timed analog output waveforms on two channels from arbitrary user-defined patterns.

Built for the SHARP (Scanning High-Aspect-Ratio Probe) project at Lawrence Berkeley National Laboratory.

## System Overview

```
┌─────────────────────────────────────────────────────────┐
│  Client Machine (Windows/Linux)                         │
│  ┌───────────────┐                                      │
│  │  mems_ui.py   │  PyQt6 GUI                           │
│  │  - Load CSV/MAT pattern files                        │
│  │  - Set loop time, scale, offset                      │
│  │  - Gaussian lowpass filter                           │
│  │  - Start/Stop control                                │
│  │  - XY pattern preview                                │
│  └───────┬───────┘                                      │
│          │ Channel Access (CA)                           │
└──────────┼──────────────────────────────────────────────┘
           │ network
┌──────────┼──────────────────────────────────────────────┐
│  IOC Machine (miist-dev1)                               │
│  ┌───────┴───────┐                                      │
│  │  EPICS IOC    │  /opt/iocs/nidaq                     │
│  │  drvNiDAQMEMS │  asynPortDriver                      │
│  └───────┬───────┘                                      │
│          │ NI-DAQmx API                                 │
│  ┌───────┴───────┐                                      │
│  │  NI USB-6423  │  Hardware-timed AO + AI              │
│  │  AO0,AO1      │──→ MEMS mirror X,Y                  │
│  │  DO port0/0   │──→ Loop sync marker                  │
│  │  AI0..AI15    │←── Sensor feedback                   │
│  └───────────────┘                                      │
└─────────────────────────────────────────────────────────┘
```

## Hardware

- **NI USB-6423**: 4 AO (±10V, 250 kS/s hardware-timed), 32 AI, DIO
- **Device name**: `Dev1` (NI-DAQmx)
- **AO0**: Mirror U axis
- **AO1**: Mirror V axis
- **DO port0/line0**: Loop synchronization marker pulse

## Quick Start

### Start the IOC

```bash
cd /opt/iocs/nidaq/iocBoot/iocnidaq
./st.cmd
```

### Start the GUI (from any networked machine)

```bash
# Set environment for network access
export EPICS_CA_ADDR_LIST=<ioc-machine-ip>
export EPICS_CA_AUTO_ADDR_LIST=NO
export EPICS_CA_MAX_ARRAY_BYTES=100000

# Run
python3 mems_ui.py
```

**Dependencies** (client machine): `pip install PyQt6 matplotlib pyepics numpy scipy`

### Command-line operation

```bash
cd /opt/iocs/nidaq/iocBoot/iocnidaq

# Load and start a pattern
./load_waveforms.sh --start ~/u.csv ~/v.csv --loop-time 1.0

# Change loop time on the fly
./set_loop_time.sh 0.5

# Check status
./load_waveforms.sh --status

# Stop
./load_waveforms.sh --stop
```

## Key Concepts

### Loop Time

The total time to play through all waveform points once. Typical SHARP range: **0.2–5.0 seconds**.

- 10,000 points at 1.0s loop time → 10 kHz sample rate, 100 µs per point
- 10,000 points at 0.2s loop time → 50 kHz sample rate, 20 µs per point

The hardware clock on the USB-6423 provides exact timing with zero jitter.

### Scale and Offset

Each output voltage is computed as:

```
voltage = waveform[i] * scale + offset
```

- **Scale**: multiplies the waveform values (for normalized patterns)
- **Offset**: shifts the waveform up/down in voltage (for mirror centering)
- Independent per channel (Scale AO0, Scale AO1, Offset AO0, Offset AO1)

### Waveform Filter

Gaussian lowpass filter in the frequency domain (ported from MATLAB `waveformfilter.m`). Pre-shapes the waveform to match the MEMS mirror's bandwidth.

- **Cutoff (Hz)**: frequency above which components are attenuated
- Interacts with loop time: effective filtering depends on `cutoff × loop_time`
- Applied client-side before sending data to the IOC
- Toggle on/off to compare filtered vs. unfiltered patterns in the preview

### Loop Marker

A digital output pulse on `port0/line0` at the start of each waveform cycle. Synchronized to the AO sample clock. Used for triggering external equipment (e.g., camera, scope).

- **Marker Enable**: on/off
- **Marker Width**: number of samples the pulse stays high (default: 10)

## File Formats

### CSV (one value per line)

```
1.20444228541204
1.2144252374828
1.22422384419678
...
```

Two separate files needed: one for AO0, one for AO1. Both must have the same number of lines.

### MATLAB .mat

A single file containing a 2-column array variable (column 0 = AO0, column 1 = AO1). The GUI's "Load .mat file" button handles this automatically.

## PV Reference

All PVs use the prefix `MEMS:` (configurable in `st.cmd`).

### Waveform Generator (Global)

| PV | Type | Description |
|----|------|-------------|
| `MEMS:WaveGen:Run` | bo (busy) | Start/Stop output |
| `MEMS:WaveGen:Frequency` | ao | Waveform repetition frequency (Hz) |
| `MEMS:WaveGen:Dwell` | ai | Time per sample point (s), read-only |
| `MEMS:WaveGen:TotalTime` | ai | Loop time (s), read-only |
| `MEMS:WaveGen:NumPoints` | longout | Number of waveform points |
| `MEMS:WaveGen:CurrentPoint` | longin | Current output position, read-only |
| `MEMS:WaveGen:Continuous` | bo | Continuous (repeat) or One-shot mode |
| `MEMS:WaveGen:MarkerEnable` | bo | Enable DO loop marker |
| `MEMS:WaveGen:MarkerWidth` | longout | Marker pulse width in samples |

### Waveform Generator (Per-Channel)

Replace `N` with `Ch0` or `Ch1`.

| PV | Type | Description |
|----|------|-------------|
| `MEMS:WaveGen:ChN:UserWF` | waveform (DOUBLE) | Waveform data array (up to 10,000 points) |
| `MEMS:WaveGen:ChN:Enable` | bo | Enable this channel |
| `MEMS:WaveGen:ChN:Amplitude` | ao | Scale factor |
| `MEMS:WaveGen:ChN:Offset` | ao | DC offset (V) |

### Analog Input (Per-Channel)

Replace `N` with 0–15.

| PV | Type | Description |
|----|------|-------------|
| `MEMS:AI:N:Value` | ai | Voltage reading (V), I/O Intr scan |
| `MEMS:AI:N:Range` | mbbo | Input range selection |

## Directory Structure

```
/opt/iocs/nidaq/
├── configure/
│   └── RELEASE                         # EPICS base + synApps module paths
├── nidaqApp/
│   ├── src/
│   │   ├── drvNiDAQMEMS.h              # Driver header (active)
│   │   ├── drvNiDAQMEMS.cpp            # Driver: NI-DAQmx, hardware-timed AO
│   │   ├── drvComediMEMS.h             # Legacy driver header (comedi, unused)
│   │   ├── drvComediMEMS.cpp           # Legacy driver (comedi, unused)
│   │   ├── nidaqMain.cpp               # IOC main()
│   │   ├── nidaqSupport.dbd            # Driver registrar
│   │   └── Makefile                    # Builds driver + IOC binary
│   └── Db/
│       ├── comediMEMS_WaveGen.template  # Global waveform gen records
│       ├── comediMEMS_WaveGenN.template # Per-channel waveform records
│       └── comediMEMS_AI.template       # Per-channel AI records
├── iocBoot/iocnidaq/
│   ├── st.cmd                          # IOC startup script
│   ├── autosave.req                    # Autosave request file
│   ├── autosave/                       # Autosave data directory
│   ├── load_waveforms.sh              # CLI: load CSV + start
│   └── set_loop_time.sh               # CLI: change loop time on the fly
├── clients/
│   ├── mems_ui.py                     # PyQt6 GUI application
│   ├── waveform_filter.py            # Gaussian lowpass filter (from MATLAB)
│   └── mems_settings.json            # Saved UI settings + recent patterns
└── bin/linux-x86_64/
    └── nidaq                          # Compiled IOC binary
```

## Driver Architecture (drvNiDAQMEMS)

The driver is an `asynPortDriver` subclass that manages three NI-DAQmx tasks:

### AO Task (`memsAO`)

- Created fresh on each `startWaveGen()` call
- Channels: `Dev1/ao0:1` (both AO channels in one task for synchronization)
- Timing: `DAQmxCfgSampClkTiming()` with hardware sample clock
- Data: `DAQmxWriteAnalogF64()` writes the entire waveform buffer before starting
- Mode: continuous (`DAQmx_Val_ContSamps`) — hardware loops the buffer indefinitely
- If the waveform fits in the onboard buffer, regeneration mode is used for zero-jitter output
- For larger waveforms, USB transfer size is increased to minimize jitter

### DO Task (`memsMarker`)

- Synchronized to AO via `ao/SampleClock` and `ao/StartTrigger`
- Outputs a pulse on `port0/line0` at the start of each waveform cycle
- Pulse width configurable via `MarkerWidth` PV

### AI Task (`memsAI`)

- Created once at startup, runs continuously
- On-demand reads (no sample clock) — polls all 16 channels every 100ms
- Values published via `AI_VALUE` parameter with `callParamCallbacks(ch)` per channel

### AO Monitor Thread

- Polls `DAQmxGetWriteTotalSampPerChanGenerated()` every 50ms
- Updates `CurrentPoint` PV with the current position in the waveform cycle
- Detects completion of finite (one-shot) outputs

## Settings Persistence

### IOC Side (EPICS autosave)

Saved every 10 seconds to `iocBoot/iocnidaq/autosave/autosave_mems.sav`. Restored on IOC reboot. Covers: Frequency, NumPoints, Continuous, MarkerEnable, MarkerWidth, per-channel Amplitude/Offset/Enable.

### Client Side (JSON)

Saved to `mems_settings.json` on UI close. Restored on next launch. Covers: loop time, scale, offsets, filter enable/cutoff, marker settings, last loaded pattern files, recent patterns list.

**Note**: Waveform data arrays are NOT persisted. After IOC reboot, patterns must be reloaded via the GUI or command-line scripts.

## Dependencies

### IOC (Linux)

- EPICS base 7.0.5: `/opt/epics/base`
- synApps modules: asyn R4-42, autosave R5-10-2, busy R1-7-3
- NI-DAQmx runtime: `libnidaqmx.so` (`apt install ni-daqmx libnidaqmx libnidaqmx-devel`)
- Build tools: gcc, make

### Client (Windows/Linux/Mac)

- Python 3.10+
- PyQt6, matplotlib, numpy, scipy, pyepics

## Building

```bash
cd /opt/iocs/nidaq
make clean
make
```

The binary is installed to `bin/linux-x86_64/nidaq`.
