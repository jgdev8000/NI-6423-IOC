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
