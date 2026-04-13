#!/bin/bash
# Change loop time without reloading waveforms
#
# Usage: ./set_loop_time.sh <seconds>
#
# Examples:
#   ./set_loop_time.sh 0.2    # fast scan
#   ./set_loop_time.sh 1.0    # 1 second loop
#   ./set_loop_time.sh 5.0    # slow scan

export EPICS_CA_MAX_ARRAY_BYTES=100000
export EPICS_CA_AUTO_ADDR_LIST=YES
export LD_LIBRARY_PATH=/opt/epics/base/lib/linux-x86_64
export PATH=/opt/epics/base/bin/linux-x86_64:$PATH

PREFIX="MEMS:"

if [ $# -lt 1 ]; then
    echo "Usage: $0 <loop_time_seconds>"
    echo "  Typical SHARP range: 0.2 - 5.0 s"
    exit 1
fi

LOOP_TIME="$1"
FREQ=$(python3 -c "print(1.0 / $LOOP_TIME)")
NPOINTS=$(caget -t ${PREFIX}WaveGen:NumPoints 2>/dev/null)
DWELL_US=$(python3 -c "print(f'{$LOOP_TIME / ${NPOINTS:-1} * 1e6:.1f}')")

WAS_RUNNING=$(caget -t ${PREFIX}WaveGen:Run 2>/dev/null)

# Stop, change, restart
if [ "$WAS_RUNNING" = "Run" ]; then
    caput ${PREFIX}WaveGen:Run 0 >/dev/null
fi

caput ${PREFIX}WaveGen:Frequency "$FREQ" >/dev/null

if [ "$WAS_RUNNING" = "Run" ]; then
    caput ${PREFIX}WaveGen:Run 1 >/dev/null
fi

echo "Loop time: ${LOOP_TIME} s  ($NPOINTS pts, ${DWELL_US} us/pt)"
