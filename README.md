# NI-DAQmx EPICS IOC

EPICS IOC for a National Instruments DAQ exposed through an `asynPortDriver` in `/opt/iocs/nidaq`.

The current IOC is built around `drvNiDAQMEMS.cpp` and the boot script [`iocBoot/iocnidaq/st.cmd`](/opt/iocs/nidaq/iocBoot/iocnidaq/st.cmd). Despite the historical `MEMS:` prefix and some legacy filenames, the IOC now exposes more than the original 2-channel MEMS waveform generator:

- 4 analog output waveform channels
- 32 scalar analog input channels
- 32 hardware-timed analog input waveform channels
- 16 digital I/O lines
- 4 counters

## What Is Actually Loaded

The default startup script configures:

- Prefix: `MEMS:`
- asyn port: `MEMS1`
- DAQmx device: `Dev1`
- maximum waveform/acquisition length: `10000` points

`st.cmd` loads these record groups:

- `WaveGen` global controls
- `WaveGen:Ch0` through `WaveGen:Ch3`
- `AI:0` through `AI:31`
- `AIAcq` plus `AIAcq:0` through `AIAcq:31`
- `DIO:0` through `DIO:15`
- `Ctr:0` through `Ctr:3`

A simulation boot script is also present:

```bash
cd /opt/iocs/nidaq/iocBoot/iocnidaq
./st_sim.cmd
```

That script uses `drvNiDAQMEMSConfigure("MEMS1", "SIM", 10000)`.

## Build And Run

Build:

```bash
cd /opt/iocs/nidaq
make
```

Start the real IOC:

```bash
cd /opt/iocs/nidaq/iocBoot/iocnidaq
./st.cmd
```

The built binary is `bin/linux-x86_64/nidaq`.

## Dependencies

From [`configure/RELEASE`](/opt/iocs/nidaq/configure/RELEASE):

- EPICS base: `/opt/epics/base`
- `asyn`: `/opt/epics/synApps/support/asyn-R4-42`
- `autosave`: `/opt/epics/synApps/support/autosave-R5-10-2`
- `busy`: `/opt/epics/synApps/support/busy-R1-7-3`

The IOC links against `libnidaqmx` via:

```make
nidaq_SYS_LIBS += nidaqmx
```

## Driver Summary

The active driver is [`nidaqApp/src/drvNiDAQMEMS.cpp`](/opt/iocs/nidaq/nidaqApp/src/drvNiDAQMEMS.cpp).

Implemented parameter groups:

- waveform generation
- scalar analog input
- hardware-timed analog input acquisition
- digital I/O
- counters

Important implementation notes:

- AO waveform generation supports up to 4 channels and starts whichever channels are enabled.
- Scalar AI is created for all 32 channels at startup and is updated by a polling thread.
- Hardware-timed AI acquisition is finite-shot and reads all 32 AI channels into per-channel waveform PVs.
- DIO direction, scalar input polling, and counter monitoring are implemented in the active driver.

## Waveform Generation PVs

Global PVs under `MEMS:WaveGen:`:

- `Run`
- `Frequency`
- `Dwell`
- `TotalTime`
- `NumPoints`
- `CurrentPoint`
- `Continuous`
- `MarkerEnable`
- `MarkerWidth`
- `TriggerSource`
- `TriggerEdge`

Per-channel PVs under `MEMS:WaveGen:Ch0:` through `Ch3:`:

- `UserWF`
- `Enable`
- `Amplitude`
- `Offset`

Behavior:

- `Frequency` is the waveform repetition rate in Hz.
- Sample rate is `Frequency * NumPoints`.
- `Dwell` and `TotalTime` are derived from `Frequency` and `NumPoints`.
- `TriggerSource` supports `Software` and `PFI0` through `PFI7`.
- `TriggerEdge` supports `Rising` and `Falling`.
- Marker output uses `port0/line0` and is clocked from the AO sample clock.

## Analog Input PVs

Scalar AI PVs under `MEMS:AI:<n>:` for `0..31`:

- `Value`
- `Range`

`Range` currently exposes:

- `+/- 10V`
- `+/- 5V`
- `+/- 0.5V`
- `+/- 0.05V`

The startup script also defines:

```text
AI_SCAN_PERIOD = 0.1
```

but the current driver initializes the scan-period parameter internally and does not read that IOC shell variable.

## Hardware-Timed AI Acquisition PVs

Global acquisition PVs under `MEMS:AIAcq:`:

- `Run`
- `Rate`
- `NumPoints`
- `TriggerSource`
- `ClockSource`
- `NumAcquired`

Per-channel waveform PVs under `MEMS:AIAcq:<n>:Data` for `0..31`.

Current behavior from the driver:

- acquisition is finite-shot, not continuous
- all 32 channels are acquired together
- `TriggerSource` supports `Software`, `AO StartTrigger`, `PFI0`, and `PFI1`
- `ClockSource` supports `Internal` and `AO SampleClock`
- polled scalar AI is stopped during acquisition and restarted after it completes

## Digital I/O PVs

Per-line PVs under `MEMS:DIO:<n>:` for `0..15`:

- `Out`
- `In`
- `Direction`

## Counter PVs

Per-counter PVs under `MEMS:Ctr:<n>:` for `0..3`:

- `Mode`
- `Count`
- `Reset`
- `Frequency`
- `PulseFreq`
- `PulseDuty`
- `PulseRun`

Supported modes in the driver:

- `Disabled`
- `Edge Count`
- `Freq Measure`
- `Pulse Gen`

## Client Programs

The maintained UI entry point is [`clients/nidaq_ui.py`](/opt/iocs/nidaq/clients/nidaq_ui.py):

```bash
cd /opt/iocs/nidaq/clients
python3 nidaq_ui.py
```

[`clients/mems_ui.py`](/opt/iocs/nidaq/clients/mems_ui.py) is now just a legacy wrapper that imports `nidaq_ui.main()`.

The GUI contains tabs for:

- waveform generation
- analog output
- analog input
- digital I/O
- counters

Current UI behavior:

- the waveform tab supports two AO pairs: `AO0/AO1` and `AO2/AO3`
- loading one pair through the per-pair controls disables the other pair
- the AO, DIO, and counter tabs poll IOC state and sync their controls from live PV values
- Channel Access write failures are surfaced in the main window status bar

Client-side Python dependencies, based on the checked-in UI code:

- `PyQt6`
- `pyepics`
- `numpy`
- `scipy`
- `matplotlib`

Set CA environment as needed before launching a client from another machine:

```bash
export EPICS_CA_ADDR_LIST=<ioc-host>
export EPICS_CA_AUTO_ADDR_LIST=NO
export EPICS_CA_MAX_ARRAY_BYTES=100000
```

## Helper Scripts

Two shell helpers are present in [`iocBoot/iocnidaq`](/opt/iocs/nidaq/iocBoot/iocnidaq):

- [`load_waveforms.sh`](/opt/iocs/nidaq/iocBoot/iocnidaq/load_waveforms.sh)
- [`set_loop_time.sh`](/opt/iocs/nidaq/iocBoot/iocnidaq/set_loop_time.sh)

These scripts are still focused on the original 2-channel use case:

- they load only `WaveGen:Ch0` and `WaveGen:Ch1`
- they treat `Frequency` as `1 / loop_time`
- `load_waveforms.sh --filter` is accepted but not implemented

## Autosave

Autosave is configured in [`iocBoot/iocnidaq/st.cmd`](/opt/iocs/nidaq/iocBoot/iocnidaq/st.cmd) and the request file is [`iocBoot/iocnidaq/autosave.req`](/opt/iocs/nidaq/iocBoot/iocnidaq/autosave.req).

Persisted settings include:

- waveform generator global settings
- channel amplitude, offset, and enable state for all 4 AO channels
- AI acquisition settings
- counter mode and pulse settings
- DIO directions

Waveform arrays themselves are not autosaved.

## Directory Map

```text
/opt/iocs/nidaq/
├── configure/
├── clients/
├── db/
├── dbd/
├── nidaqApp/
│   ├── Db/
│   └── src/
└── iocBoot/iocnidaq/
```

Most relevant files:

- [`nidaqApp/src/drvNiDAQMEMS.cpp`](/opt/iocs/nidaq/nidaqApp/src/drvNiDAQMEMS.cpp)
- [`nidaqApp/src/drvNiDAQMEMS.h`](/opt/iocs/nidaq/nidaqApp/src/drvNiDAQMEMS.h)
- [`nidaqApp/src/Makefile`](/opt/iocs/nidaq/nidaqApp/src/Makefile)
- [`iocBoot/iocnidaq/st.cmd`](/opt/iocs/nidaq/iocBoot/iocnidaq/st.cmd)
- [`iocBoot/iocnidaq/st_sim.cmd`](/opt/iocs/nidaq/iocBoot/iocnidaq/st_sim.cmd)
