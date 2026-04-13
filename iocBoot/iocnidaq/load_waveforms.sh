#!/bin/bash
# Load CSV waveform pairs into the MEMS IOC
#
# Usage:
#   ./load_waveforms.sh <ch0.csv> <ch1.csv> [options]
#   ./load_waveforms.sh --stop
#   ./load_waveforms.sh --status
#
# Options:
#   --loop-time <seconds>   Loop time in seconds (default: 1.0, typical: 0.2-5.0)
#   --scale <factor>        Scale factor applied to both channels (default: 1.0)
#   --offset-u <volts>      DC offset for Ch0/U (default: 0.0)
#   --offset-v <volts>      DC offset for Ch1/V (default: 0.0)
#   --filter <file>         Apply frequency-domain filter kernel (not yet implemented)
#   --start                 Start output immediately after loading
#
# Examples:
#   ./load_waveforms.sh ~/u.csv ~/v.csv --loop-time 1.0
#   ./load_waveforms.sh --start ~/u.csv ~/v.csv --loop-time 0.5 --scale 2.0
#   ./load_waveforms.sh ~/u.csv ~/v.csv --loop-time 0.2 --offset-u 1.5 --offset-v -0.5
#   ./load_waveforms.sh --stop

export EPICS_CA_MAX_ARRAY_BYTES=100000
export EPICS_CA_AUTO_ADDR_LIST=YES
export LD_LIBRARY_PATH=/opt/epics/base/lib/linux-x86_64
export PATH=/opt/epics/base/bin/linux-x86_64:$PATH

PREFIX="MEMS:"

# --- Handle --stop / --status early ---
case "$1" in
    --stop)
        caput ${PREFIX}WaveGen:Run 0
        exit 0
        ;;
    --status)
        RUN=$(caget -t ${PREFIX}WaveGen:Run 2>/dev/null)
        FREQ=$(caget -t ${PREFIX}WaveGen:Frequency 2>/dev/null)
        NPTS=$(caget -t ${PREFIX}WaveGen:NumPoints 2>/dev/null)
        CURPT=$(caget -t ${PREFIX}WaveGen:CurrentPoint 2>/dev/null)
        CONT=$(caget -t ${PREFIX}WaveGen:Continuous 2>/dev/null)
        AMP0=$(caget -t ${PREFIX}WaveGen:Ch0:Amplitude 2>/dev/null)
        OFF0=$(caget -t ${PREFIX}WaveGen:Ch0:Offset 2>/dev/null)
        AMP1=$(caget -t ${PREFIX}WaveGen:Ch1:Amplitude 2>/dev/null)
        OFF1=$(caget -t ${PREFIX}WaveGen:Ch1:Offset 2>/dev/null)

        python3 -c "
freq = $FREQ
npts = $NPTS
loop = 1.0/freq if freq > 0 else float('inf')
dwell_us = loop/npts * 1e6 if npts > 0 else 0
print(f'State:      $RUN')
print(f'Loop time:  {loop:.4f} s')
print(f'Points:     {npts}')
print(f'Dwell:      {dwell_us:.1f} us/pt')
print(f'Mode:       $CONT')
print(f'Current pt: $CURPT')
print(f'Ch0 (U):    scale=$AMP0  offset=$OFF0 V')
print(f'Ch1 (V):    scale=$AMP1  offset=$OFF1 V')
" 2>/dev/null
        exit 0
        ;;
esac

# --- Parse arguments ---
AUTOSTART=0
LOOP_TIME="1.0"
SCALE="1.0"
OFFSET_U="0.0"
OFFSET_V="0.0"
FILTER=""
CH0_FILE=""
CH1_FILE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --start)      AUTOSTART=1; shift ;;
        --loop-time)  LOOP_TIME="$2"; shift 2 ;;
        --scale)      SCALE="$2"; shift 2 ;;
        --offset-u)   OFFSET_U="$2"; shift 2 ;;
        --offset-v)   OFFSET_V="$2"; shift 2 ;;
        --filter)     FILTER="$2"; shift 2 ;;
        -*)           echo "Unknown option: $1"; exit 1 ;;
        *)
            if [ -z "$CH0_FILE" ]; then
                CH0_FILE="$1"
            elif [ -z "$CH1_FILE" ]; then
                CH1_FILE="$1"
            else
                echo "Error: unexpected argument '$1'"
                exit 1
            fi
            shift
            ;;
    esac
done

if [ -z "$CH0_FILE" ] || [ -z "$CH1_FILE" ]; then
    echo "Usage: $0 [--start] <ch0.csv> <ch1.csv> [--loop-time <s>] [--scale <f>] [--offset-u <V>] [--offset-v <V>]"
    echo "       $0 --stop"
    echo "       $0 --status"
    exit 1
fi

if [ ! -f "$CH0_FILE" ]; then echo "Error: $CH0_FILE not found"; exit 1; fi
if [ ! -f "$CH1_FILE" ]; then echo "Error: $CH1_FILE not found"; exit 1; fi

N0=$(wc -l < "$CH0_FILE")
N1=$(wc -l < "$CH1_FILE")
if [ "$N0" -ne "$N1" ]; then
    echo "Error: files have different lengths ($N0 vs $N1 points)"
    exit 1
fi
NPOINTS=$N0

FREQ=$(python3 -c "print(1.0 / $LOOP_TIME)")
DWELL_US=$(python3 -c "print(f'{$LOOP_TIME / $NPOINTS * 1e6:.1f}')")

echo "Loading $NPOINTS points"
echo "  Ch0 (U): $CH0_FILE"
echo "  Ch1 (V): $CH1_FILE"
echo "  Loop time: ${LOOP_TIME} s  (freq=${FREQ} Hz, dwell=${DWELL_US} us/pt)"
echo "  Scale: ${SCALE}  Offset U: ${OFFSET_U} V  Offset V: ${OFFSET_V} V"

if [ -n "$FILTER" ]; then
    echo "  Filter: $FILTER (not yet implemented — loading unfiltered)"
    # TODO: apply_filter.py --filter "$FILTER" "$CH0_FILE" "$CH1_FILE"
    #       produces filtered temp files, load those instead
fi

# --- Stop if running ---
caput -s ${PREFIX}WaveGen:Run 0 2>/dev/null

# --- Apply settings ---
caput ${PREFIX}WaveGen:NumPoints "$NPOINTS"
caput ${PREFIX}WaveGen:Ch0:Amplitude "$SCALE"
caput ${PREFIX}WaveGen:Ch0:Offset "$OFFSET_U"
caput ${PREFIX}WaveGen:Ch1:Amplitude "$SCALE"
caput ${PREFIX}WaveGen:Ch1:Offset "$OFFSET_V"
caput ${PREFIX}WaveGen:Frequency "$FREQ"

# --- Load waveform data ---
echo "Loading Ch0..."
caput -a ${PREFIX}WaveGen:Ch0:UserWF "$NPOINTS" $(tr '\n' ' ' < "$CH0_FILE")
echo "Loading Ch1..."
caput -a ${PREFIX}WaveGen:Ch1:UserWF "$NPOINTS" $(tr '\n' ' ' < "$CH1_FILE")

echo "Done."

if [ "$AUTOSTART" = "1" ]; then
    caput ${PREFIX}WaveGen:Run 1
    echo "Running."
else
    echo "Start with: caput ${PREFIX}WaveGen:Run 1"
    echo "  or: $0 --start $CH0_FILE $CH1_FILE --loop-time $LOOP_TIME"
fi
