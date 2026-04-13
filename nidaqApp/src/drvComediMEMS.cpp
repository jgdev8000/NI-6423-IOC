/*
 * drvComediMEMS.cpp
 *
 * EPICS asynPortDriver for NI PCI-6036E via comedi.
 * Hardware-timed AO waveform generation + polled AI readback.
 */

#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <math.h>
#include <errno.h>
#include <time.h>

#include <epicsExport.h>
#include <iocsh.h>
#include <epicsThread.h>
#include <epicsEvent.h>
#include <epicsTime.h>

#include "drvComediMEMS.h"

static const char *driverName = "drvComediMEMS";

/* -------------------------------------------------------------------- */
/*  Constructor                                                          */
/* -------------------------------------------------------------------- */

drvComediMEMS::drvComediMEMS(const char *portName, const char *comediDevice,
                             int maxPoints)
    : asynPortDriver(portName,
                     MAX_ADDR,    /* maxAddr (0..15 covers both AO and AI) */
                     asynInt32Mask | asynFloat64Mask | asynFloat64ArrayMask |
                     asynDrvUserMask,
                     asynInt32Mask | asynFloat64Mask | asynFloat64ArrayMask,
                     ASYN_MULTIDEVICE | ASYN_CANBLOCK,
                     1,  /* autoConnect */
                     0,  /* priority */
                     0), /* stackSize */
      dev_(NULL),
      comedi_fd_(-1),
      aoSubdev_(1),
      aiSubdev_(0),
      aoMaxdata_(0),
      aiMaxdata_(0),
      maxPoints_(maxPoints),
      aoBuffer_(NULL),
      aoBufferSize_(0),
      waveGenRunning_(0),
      waveGenNumChans_(0),
      waveGenThreadId_(0),
      waveGenStopEvent_(NULL),
      aiThreadId_(0),
      aiRunning_(1)
{
    static const char *functionName = "drvComediMEMS";

    /* Create asyn parameters */
    createParam(P_WaveGenRunString,          asynParamInt32,        &P_WaveGenRun);
    createParam(P_WaveGenFrequencyString,    asynParamFloat64,      &P_WaveGenFrequency);
    createParam(P_WaveGenDwellString,        asynParamFloat64,      &P_WaveGenDwell);
    createParam(P_WaveGenTotalTimeString,    asynParamFloat64,      &P_WaveGenTotalTime);
    createParam(P_WaveGenNumPointsString,    asynParamInt32,        &P_WaveGenNumPoints);
    createParam(P_WaveGenCurrentPointString, asynParamInt32,        &P_WaveGenCurrentPoint);
    createParam(P_WaveGenContinuousString,   asynParamInt32,        &P_WaveGenContinuous);
    createParam(P_WaveGenEnableString,       asynParamInt32,        &P_WaveGenEnable);
    createParam(P_WaveGenAmplitudeString,    asynParamFloat64,      &P_WaveGenAmplitude);
    createParam(P_WaveGenOffsetString,       asynParamFloat64,      &P_WaveGenOffset);
    createParam(P_WaveGenUserWFString,       asynParamFloat64Array, &P_WaveGenUserWF);
    createParam(P_AIValueString,             asynParamFloat64,      &P_AIValue);
    createParam(P_AIRangeString,             asynParamInt32,        &P_AIRange);
    createParam(P_AIScanPeriodString,        asynParamFloat64,      &P_AIScanPeriod);

    /* Set defaults */
    setIntegerParam(P_WaveGenRun, 0);
    setDoubleParam(P_WaveGenFrequency, 1000.0);
    setDoubleParam(P_WaveGenDwell, 0.0);
    setDoubleParam(P_WaveGenTotalTime, 0.0);
    setIntegerParam(P_WaveGenNumPoints, 100);
    setIntegerParam(P_WaveGenCurrentPoint, 0);
    setIntegerParam(P_WaveGenContinuous, 1);
    setDoubleParam(P_AIScanPeriod, 0.1);

    for (int i = 0; i < MAX_AO_CHANNELS; i++) {
        setIntegerParam(i, P_WaveGenEnable, 1);
        setDoubleParam(i, P_WaveGenAmplitude, 1.0);
        setDoubleParam(i, P_WaveGenOffset, 0.0);
        userWF_[i] = (epicsFloat64 *)calloc(maxPoints_, sizeof(epicsFloat64));
    }

    for (int i = 0; i < MAX_AI_CHANNELS; i++) {
        setDoubleParam(i, P_AIValue, 0.0);
        setIntegerParam(i, P_AIRange, 0);
        aiRange_[i] = NULL;
    }

    /* Open comedi device */
    dev_ = comedi_open(comediDevice);
    if (!dev_) {
        asynPrint(pasynUserSelf, ASYN_TRACE_ERROR,
            "%s:%s: ERROR: comedi_open(%s) failed\n",
            driverName, functionName, comediDevice);
        return;
    }
    comedi_fd_ = comedi_fileno(dev_);

    /* Get AO info */
    aoMaxdata_ = comedi_get_maxdata(dev_, aoSubdev_, 0);
    aoRange_ = comedi_get_range(dev_, aoSubdev_, 0, 0); /* range 0: +-10V */

    /* Get AI info */
    aiMaxdata_ = comedi_get_maxdata(dev_, aiSubdev_, 0);
    for (int i = 0; i < MAX_AI_CHANNELS; i++) {
        int rng = 0;
        getIntegerParam(i, P_AIRange, &rng);
        aiRange_[i] = comedi_get_range(dev_, aiSubdev_, i, rng);
    }

    asynPrint(pasynUserSelf, ASYN_TRACE_FLOW,
        "%s:%s: opened %s, AO maxdata=%u, AI maxdata=%u\n",
        driverName, functionName, comediDevice,
        (unsigned)aoMaxdata_, (unsigned)aiMaxdata_);

    /* Allocate AO buffer (interleaved, 2 channels) */
    aoBufferSize_ = maxPoints_ * MAX_AO_CHANNELS * sizeof(lsampl_t);
    aoBuffer_ = (lsampl_t *)calloc(maxPoints_ * MAX_AO_CHANNELS, sizeof(lsampl_t));

    /* Create stop event */
    waveGenStopEvent_ = epicsEventCreate(epicsEventEmpty);

    /* Start AI polling thread */
    aiThreadId_ = epicsThreadCreate("comediAI",
        epicsThreadPriorityMedium,
        epicsThreadGetStackSize(epicsThreadStackMedium),
        aiThreadC, this);

    for (int i = 0; i < MAX_ADDR; i++) {
        callParamCallbacks(i);
    }
}

drvComediMEMS::~drvComediMEMS()
{
    aiRunning_ = 0;
    stopWaveGen();

    if (dev_) {
        comedi_close(dev_);
        dev_ = NULL;
    }
    for (int i = 0; i < MAX_AO_CHANNELS; i++) {
        free(userWF_[i]);
    }
    free(aoBuffer_);
    epicsEventDestroy(waveGenStopEvent_);
}

/* -------------------------------------------------------------------- */
/*  AO Waveform Generation                                              */
/* -------------------------------------------------------------------- */

void drvComediMEMS::buildAOBuffer(int numPoints, int numChans)
{
    /* Build interleaved 16-bit sample buffer from user waveform data.
     * Applies per-channel amplitude and offset, converts volts to DAC codes. */

    for (int ch = 0; ch < numChans; ch++) {
        epicsFloat64 amplitude, offset;
        getDoubleParam(ch, P_WaveGenAmplitude, &amplitude);
        getDoubleParam(ch, P_WaveGenOffset, &offset);

        for (int j = 0; j < numPoints; j++) {
            double volts = userWF_[ch][j] * amplitude + offset;
            lsampl_t raw = comedi_from_phys(volts, aoRange_, aoMaxdata_);
            aoBuffer_[j * numChans + ch] = raw;
        }
    }
}

int drvComediMEMS::startWaveGen()
{
    static const char *functionName = "startWaveGen";
    int numPoints;
    int continuous;
    double frequency;

    if (waveGenRunning_) {
        stopWaveGen();
    }

    getIntegerParam(P_WaveGenNumPoints, &numPoints);
    getDoubleParam(P_WaveGenFrequency, &frequency);
    getIntegerParam(P_WaveGenContinuous, &continuous);

    if (numPoints < 1 || numPoints > maxPoints_) {
        asynPrint(pasynUserSelf, ASYN_TRACE_ERROR,
            "%s:%s: invalid numPoints=%d (max=%d)\n",
            driverName, functionName, numPoints, maxPoints_);
        return -1;
    }

    if (frequency <= 0.0) {
        asynPrint(pasynUserSelf, ASYN_TRACE_ERROR,
            "%s:%s: invalid frequency=%f\n",
            driverName, functionName, frequency);
        return -1;
    }

    /* Determine which channels are enabled */
    int numChans = 0;
    for (int i = 0; i < MAX_AO_CHANNELS; i++) {
        int enable;
        getIntegerParam(i, P_WaveGenEnable, &enable);
        if (enable) {
            aoChanlist_[numChans] = i; /* store actual channel number */
            numChans++;
        }
    }

    if (numChans == 0) {
        asynPrint(pasynUserSelf, ASYN_TRACE_ERROR,
            "%s:%s: no channels enabled\n", driverName, functionName);
        return -1;
    }

    /* Compute dwell time */
    double dwell = 1.0 / (frequency * numPoints);

    /* Build the output buffer (stores lsampl_t values per channel per point) */
    buildAOBuffer(numPoints, numChans);

    /* Update readbacks */
    setDoubleParam(P_WaveGenDwell, dwell);
    setDoubleParam(P_WaveGenFrequency, frequency);
    setDoubleParam(P_WaveGenTotalTime, dwell * numPoints);

    /* Store params for the waveform thread */
    waveGenNumChans_ = numChans;

    waveGenRunning_ = 1;
    setIntegerParam(P_WaveGenRun, 1);
    callParamCallbacks();

    /* Start the software-timed output thread */
    epicsEventTryWait(waveGenStopEvent_); /* clear any pending signal */
    waveGenThreadId_ = epicsThreadCreate("comediWaveGen",
        epicsThreadPriorityHigh,
        epicsThreadGetStackSize(epicsThreadStackMedium),
        waveGenThreadC, this);

    asynPrint(pasynUserSelf, ASYN_TRACE_FLOW,
        "%s:%s: started waveGen (software-timed), %d chans, %d points, "
        "freq=%.1f Hz, dwell=%.3f us\n",
        driverName, functionName, numChans, numPoints,
        frequency, dwell * 1e6);

    return 0;
}

int drvComediMEMS::stopWaveGen()
{
    if (!waveGenRunning_) return 0;

    waveGenRunning_ = 0;

    /* Signal the refill thread to stop */
    epicsEventSignal(waveGenStopEvent_);

    /* Wait briefly for thread to exit */
    if (waveGenThreadId_) {
        epicsThreadSleep(0.1);
        waveGenThreadId_ = 0;
    }

    comedi_cancel(dev_, aoSubdev_);

    setIntegerParam(P_WaveGenRun, 0);
    callParamCallbacks();

    asynPrint(pasynUserSelf, ASYN_TRACE_FLOW,
        "%s: stopped waveGen\n", driverName);

    return 0;
}

void drvComediMEMS::waveGenThreadC(void *drvPvt)
{
    ((drvComediMEMS *)drvPvt)->waveGenThread();
}

void drvComediMEMS::waveGenThread()
{
    static const char *functionName = "waveGenThread";
    int numPoints, continuous;
    double dwell;

    getIntegerParam(P_WaveGenNumPoints, &numPoints);
    getIntegerParam(P_WaveGenContinuous, &continuous);
    getDoubleParam(P_WaveGenDwell, &dwell);

    int numChans = waveGenNumChans_;

    asynPrint(pasynUserSelf, ASYN_TRACE_FLOW,
        "%s:%s: software-timed output started, %d chans, %d points, dwell=%.1f us\n",
        driverName, functionName, numChans, numPoints, dwell * 1e6);

    /* Software-timed waveform output loop.
     * Uses clock_nanosleep for precise timing. Writes both AO channels
     * per step, updates CurrentPoint and checks stop only periodically
     * to minimize overhead. */

    struct timespec next_time;
    clock_gettime(CLOCK_MONOTONIC, &next_time);
    long dwell_ns = (long)(dwell * 1e9 + 0.5);
    /* Update PV and check stop every ~10ms or every point if dwell >= 10ms */
    int update_interval = (dwell >= 0.01) ? 1 : (int)(0.01 / dwell);
    if (update_interval < 1) update_interval = 1;
    if (update_interval > numPoints) update_interval = numPoints;

    do {
        for (int j = 0; j < numPoints && waveGenRunning_; j++) {
            /* Write all enabled channels for this time step */
            for (int c = 0; c < numChans; c++) {
                comedi_data_write(dev_, aoSubdev_, aoChanlist_[c], 0,
                                  AREF_GROUND, aoBuffer_[j * numChans + c]);
            }

            /* Advance to next time slot */
            next_time.tv_nsec += dwell_ns;
            while (next_time.tv_nsec >= 1000000000L) {
                next_time.tv_nsec -= 1000000000L;
                next_time.tv_sec++;
            }
            clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next_time, NULL);

            /* Periodic housekeeping: update PV, check stop */
            if ((j % update_interval) == 0) {
                setIntegerParam(P_WaveGenCurrentPoint, j);
                epicsEventWaitStatus evStatus = epicsEventWaitWithTimeout(
                    waveGenStopEvent_, 0.0);
                if (evStatus == epicsEventWaitOK) {
                    waveGenRunning_ = 0;
                    break;
                }
            }
        }

        /* Re-sync clock at cycle boundary to prevent drift accumulation */
        clock_gettime(CLOCK_MONOTONIC, &next_time);
    } while (continuous && waveGenRunning_);

    /* Update state */
    lock();
    waveGenRunning_ = 0;
    setIntegerParam(P_WaveGenRun, 0);
    callParamCallbacks();
    unlock();

    asynPrint(pasynUserSelf, ASYN_TRACE_FLOW,
        "%s:%s: thread exiting\n", driverName, functionName);
}

/* -------------------------------------------------------------------- */
/*  AI Polling Thread                                                    */
/* -------------------------------------------------------------------- */

void drvComediMEMS::aiThreadC(void *drvPvt)
{
    ((drvComediMEMS *)drvPvt)->aiThread();
}

void drvComediMEMS::aiThread()
{
    static const char *functionName = "aiThread";

    asynPrint(pasynUserSelf, ASYN_TRACE_FLOW,
        "%s:%s: AI polling thread started\n", driverName, functionName);

    while (aiRunning_) {
        double scanPeriod;
        getDoubleParam(P_AIScanPeriod, &scanPeriod);
        if (scanPeriod < 0.01) scanPeriod = 0.01;

        lock();

        for (int ch = 0; ch < MAX_AI_CHANNELS; ch++) {
            int rng;
            lsampl_t data;
            getIntegerParam(ch, P_AIRange, &rng);

            int ret = comedi_data_read(dev_, aiSubdev_, ch, rng, AREF_GROUND, &data);
            if (ret < 0) {
                asynPrint(pasynUserSelf, ASYN_TRACE_ERROR,
                    "%s:%s: comedi_data_read ch=%d failed\n",
                    driverName, functionName, ch);
                continue;
            }

            comedi_range *range = comedi_get_range(dev_, aiSubdev_, ch, rng);
            double volts = comedi_to_phys(data, range, aiMaxdata_);

            setDoubleParam(ch, P_AIValue, volts);
            callParamCallbacks(ch);
        }

        unlock();

        epicsThreadSleep(scanPeriod);
    }
}

/* -------------------------------------------------------------------- */
/*  asynPortDriver overrides                                             */
/* -------------------------------------------------------------------- */

asynStatus drvComediMEMS::writeInt32(asynUser *pasynUser, epicsInt32 value)
{
    int function = pasynUser->reason;
    int addr;
    getAddress(pasynUser, &addr);
    asynStatus status = asynSuccess;

    if (function == P_WaveGenRun) {
        if (value) {
            if (startWaveGen() < 0) status = asynError;
        } else {
            stopWaveGen();
        }
    }
    else {
        status = asynPortDriver::writeInt32(pasynUser, value);
    }

    callParamCallbacks(addr);
    return status;
}

asynStatus drvComediMEMS::writeFloat64(asynUser *pasynUser, epicsFloat64 value)
{
    int function = pasynUser->reason;
    int addr;
    getAddress(pasynUser, &addr);
    asynStatus status;

    status = asynPortDriver::writeFloat64(pasynUser, value);

    /* If frequency or numPoints changed while running, update dwell readback */
    if (function == P_WaveGenFrequency) {
        int numPoints;
        getIntegerParam(P_WaveGenNumPoints, &numPoints);
        if (numPoints > 0 && value > 0) {
            double dwell = 1.0 / (value * numPoints);
            setDoubleParam(P_WaveGenDwell, dwell);
            setDoubleParam(P_WaveGenTotalTime, dwell * numPoints);
        }
        callParamCallbacks();
    }

    return status;
}

asynStatus drvComediMEMS::writeFloat64Array(asynUser *pasynUser,
                                             epicsFloat64 *value,
                                             size_t nElements)
{
    int function = pasynUser->reason;
    int addr;
    getAddress(pasynUser, &addr);

    if (function == P_WaveGenUserWF) {
        if (addr < 0 || addr >= MAX_AO_CHANNELS) return asynError;

        size_t n = nElements;
        if ((int)n > maxPoints_) n = maxPoints_;
        memcpy(userWF_[addr], value, n * sizeof(epicsFloat64));

        /* If running, rebuild the output buffer with new waveform data */
        if (waveGenRunning_) {
            int numPoints, numChans = 0;
            getIntegerParam(P_WaveGenNumPoints, &numPoints);
            for (int i = 0; i < MAX_AO_CHANNELS; i++) {
                int enable;
                getIntegerParam(i, P_WaveGenEnable, &enable);
                if (enable) numChans++;
            }
            buildAOBuffer(numPoints, numChans);
        }

        return asynSuccess;
    }

    return asynPortDriver::writeFloat64Array(pasynUser, value, nElements);
}

asynStatus drvComediMEMS::readFloat64Array(asynUser *pasynUser,
                                            epicsFloat64 *value,
                                            size_t nElements,
                                            size_t *nIn)
{
    int function = pasynUser->reason;
    int addr;
    getAddress(pasynUser, &addr);

    if (function == P_WaveGenUserWF) {
        if (addr < 0 || addr >= MAX_AO_CHANNELS) return asynError;

        int numPoints;
        getIntegerParam(P_WaveGenNumPoints, &numPoints);
        size_t n = numPoints;
        if (n > nElements) n = nElements;
        if ((int)n > maxPoints_) n = maxPoints_;
        memcpy(value, userWF_[addr], n * sizeof(epicsFloat64));
        *nIn = n;
        return asynSuccess;
    }

    return asynPortDriver::readFloat64Array(pasynUser, value, nElements, nIn);
}

/* -------------------------------------------------------------------- */
/*  IOC shell configuration function                                     */
/* -------------------------------------------------------------------- */

extern "C" {

static const iocshArg initArg0 = {"portName", iocshArgString};
static const iocshArg initArg1 = {"comediDevice", iocshArgString};
static const iocshArg initArg2 = {"maxPoints", iocshArgInt};
static const iocshArg *const initArgs[] = {&initArg0, &initArg1, &initArg2};
static const iocshFuncDef initFuncDef = {"drvComediMEMSConfigure", 3, initArgs};

static void initCallFunc(const iocshArgBuf *args)
{
    new drvComediMEMS(args[0].sval, args[1].sval, args[2].ival);
}

static void drvComediMEMSRegister(void)
{
    iocshRegister(&initFuncDef, initCallFunc);
}

epicsExportRegistrar(drvComediMEMSRegister);

} /* extern "C" */
