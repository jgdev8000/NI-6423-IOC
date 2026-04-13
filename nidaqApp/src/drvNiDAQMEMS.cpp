/*
 * drvNiDAQMEMS.cpp
 *
 * EPICS asynPortDriver for NI USB-6423 via NI-DAQmx.
 * Full device support: AO waveform gen, AI polled + HW-timed, DIO, counters.
 */

#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <math.h>

#include <epicsExport.h>
#include <iocsh.h>
#include <epicsThread.h>
#include <epicsTime.h>

#include "drvNiDAQMEMS.h"

static const char *driverName = "drvNiDAQMEMS";

void drvNiDAQMEMS::reportDAQmxError(int32 error, const char *function)
{
    if (error >= 0) return;
    char errBuf[2048];
    DAQmxGetExtendedErrorInfo(errBuf, sizeof(errBuf));
    asynPrint(pasynUserSelf, ASYN_TRACE_ERROR,
        "%s:%s: DAQmx error %d: %s\n",
        driverName, function, (int)error, errBuf);
}

/* ================================================================== */
/*  Constructor                                                        */
/* ================================================================== */

drvNiDAQMEMS::drvNiDAQMEMS(const char *portName, const char *daqmxDevice,
                           int maxPoints)
    : asynPortDriver(portName, MAX_ADDR,
                     asynInt32Mask | asynFloat64Mask | asynFloat64ArrayMask | asynDrvUserMask,
                     asynInt32Mask | asynFloat64Mask | asynFloat64ArrayMask,
                     ASYN_MULTIDEVICE | ASYN_CANBLOCK, 1, 0, 0),
      maxPoints_(maxPoints), simMode_(0),
      aoTask_(0), doTask_(0), aoBuffer_(NULL), doBuffer_(NULL),
      waveGenRunning_(0), aoMonitorThreadId_(0), aoMonitorRunning_(1),
      aiTask_(0), aiThreadId_(0), aiRunning_(1),
      aiAcqTask_(0), aiAcqBuffer_(NULL), aiAcqRunning_(0),
      dioReadTask_(0), dioThreadId_(0), dioRunning_(1),
      ctrThreadId_(0), ctrRunning_(1)
{
    static const char *functionName = "drvNiDAQMEMS";
    int32 ret;

    strncpy(devName_, daqmxDevice, sizeof(devName_) - 1);
    devName_[sizeof(devName_) - 1] = '\0';
    snprintf(markerLine_, sizeof(markerLine_), "%s/port0/line0", devName_);

    /* Detect simulation mode */
    simMode_ = (strcasecmp(daqmxDevice, "SIM") == 0) ? 1 : 0;
    if (simMode_) {
        asynPrint(pasynUserSelf, ASYN_TRACE_FLOW,
            "%s:%s: *** SIMULATION MODE — no hardware ***\n",
            driverName, functionName);
    }

    for (int i = 0; i < MAX_COUNTERS; i++) ctrTask_[i] = 0;

    /* ---- Create all asyn parameters ---- */

    /* Waveform generator - global */
    createParam(P_WaveGenRunString,          asynParamInt32,        &P_WaveGenRun);
    createParam(P_WaveGenFrequencyString,    asynParamFloat64,      &P_WaveGenFrequency);
    createParam(P_WaveGenDwellString,        asynParamFloat64,      &P_WaveGenDwell);
    createParam(P_WaveGenTotalTimeString,    asynParamFloat64,      &P_WaveGenTotalTime);
    createParam(P_WaveGenNumPointsString,    asynParamInt32,        &P_WaveGenNumPoints);
    createParam(P_WaveGenCurrentPointString, asynParamInt32,        &P_WaveGenCurrentPoint);
    createParam(P_WaveGenContinuousString,   asynParamInt32,        &P_WaveGenContinuous);
    createParam(P_WaveGenMarkerEnableString, asynParamInt32,        &P_WaveGenMarkerEnable);
    createParam(P_WaveGenMarkerWidthString,  asynParamInt32,        &P_WaveGenMarkerWidth);
    createParam(P_WaveGenTrigSrcString,      asynParamInt32,        &P_WaveGenTrigSrc);
    createParam(P_WaveGenTrigEdgeString,     asynParamInt32,        &P_WaveGenTrigEdge);

    /* Waveform generator - per channel */
    createParam(P_WaveGenEnableString,       asynParamInt32,        &P_WaveGenEnable);
    createParam(P_WaveGenAmplitudeString,    asynParamFloat64,      &P_WaveGenAmplitude);
    createParam(P_WaveGenOffsetString,       asynParamFloat64,      &P_WaveGenOffset);
    createParam(P_WaveGenUserWFString,       asynParamFloat64Array, &P_WaveGenUserWF);

    /* AI polled */
    createParam(P_AIValueString,             asynParamFloat64,      &P_AIValue);
    createParam(P_AIRangeString,             asynParamInt32,        &P_AIRange);
    createParam(P_AIScanPeriodString,        asynParamFloat64,      &P_AIScanPeriod);

    /* AI acquisition */
    createParam(P_AIAcqRunString,            asynParamInt32,        &P_AIAcqRun);
    createParam(P_AIAcqRateString,           asynParamFloat64,      &P_AIAcqRate);
    createParam(P_AIAcqNumPointsString,      asynParamInt32,        &P_AIAcqNumPoints);
    createParam(P_AIAcqTrigSrcString,        asynParamInt32,        &P_AIAcqTrigSrc);
    createParam(P_AIAcqClkSrcString,         asynParamInt32,        &P_AIAcqClkSrc);
    createParam(P_AIAcqNumAcquiredString,    asynParamInt32,        &P_AIAcqNumAcquired);
    createParam(P_AIAcqDataString,           asynParamFloat64Array, &P_AIAcqData);

    /* DIO */
    createParam(P_DIOOutString,              asynParamInt32,        &P_DIOOut);
    createParam(P_DIOInString,               asynParamInt32,        &P_DIOIn);
    createParam(P_DIODirString,              asynParamInt32,        &P_DIODir);

    /* Counters */
    createParam(P_CtrModeString,             asynParamInt32,        &P_CtrMode);
    createParam(P_CtrCountString,            asynParamInt32,        &P_CtrCount);
    createParam(P_CtrResetString,            asynParamInt32,        &P_CtrReset);
    createParam(P_CtrFreqString,             asynParamFloat64,      &P_CtrFreq);
    createParam(P_CtrPulseFreqString,        asynParamFloat64,      &P_CtrPulseFreq);
    createParam(P_CtrPulseDutyString,        asynParamFloat64,      &P_CtrPulseDuty);
    createParam(P_CtrPulseRunString,         asynParamInt32,        &P_CtrPulseRun);

    /* ---- Set defaults ---- */
    setIntegerParam(P_WaveGenRun, 0);
    setDoubleParam(P_WaveGenFrequency, 1.0);
    setDoubleParam(P_WaveGenDwell, 0.0);
    setDoubleParam(P_WaveGenTotalTime, 0.0);
    setIntegerParam(P_WaveGenNumPoints, 100);
    setIntegerParam(P_WaveGenCurrentPoint, 0);
    setIntegerParam(P_WaveGenContinuous, 1);
    setIntegerParam(P_WaveGenMarkerEnable, 1);
    setIntegerParam(P_WaveGenMarkerWidth, 10);
    setIntegerParam(P_WaveGenTrigSrc, 0);
    setIntegerParam(P_WaveGenTrigEdge, 0);
    setDoubleParam(P_AIScanPeriod, 0.1);
    setIntegerParam(P_AIAcqRun, 0);
    setDoubleParam(P_AIAcqRate, 10000.0);
    setIntegerParam(P_AIAcqNumPoints, 10000);
    setIntegerParam(P_AIAcqTrigSrc, 0);
    setIntegerParam(P_AIAcqClkSrc, 0);
    setIntegerParam(P_AIAcqNumAcquired, 0);

    for (int i = 0; i < MAX_AO_CHANNELS; i++) {
        setIntegerParam(i, P_WaveGenEnable, (i < 2) ? 1 : 0);
        setDoubleParam(i, P_WaveGenAmplitude, 1.0);
        setDoubleParam(i, P_WaveGenOffset, 0.0);
        userWF_[i] = (epicsFloat64 *)calloc(maxPoints_, sizeof(epicsFloat64));
    }
    for (int i = 0; i < MAX_AI_CHANNELS; i++) {
        setDoubleParam(i, P_AIValue, 0.0);
        setIntegerParam(i, P_AIRange, 0);
    }
    for (int i = 0; i < MAX_DIO_LINES; i++) {
        setIntegerParam(i, P_DIOOut, 0);
        setIntegerParam(i, P_DIOIn, 0);
        setIntegerParam(i, P_DIODir, 0);
    }
    for (int i = 0; i < MAX_COUNTERS; i++) {
        setIntegerParam(i, P_CtrMode, 0);
        setIntegerParam(i, P_CtrCount, 0);
        setDoubleParam(i, P_CtrFreq, 0.0);
        setDoubleParam(i, P_CtrPulseFreq, 1000.0);
        setDoubleParam(i, P_CtrPulseDuty, 0.5);
        setIntegerParam(i, P_CtrPulseRun, 0);
    }

    /* ---- Allocate buffers ---- */
    aoBuffer_ = (epicsFloat64 *)calloc(maxPoints_ * MAX_AO_CHANNELS, sizeof(epicsFloat64));
    doBuffer_ = (uInt8 *)calloc(maxPoints_, sizeof(uInt8));
    aiAcqBuffer_ = (epicsFloat64 *)calloc(maxPoints_ * MAX_AI_CHANNELS, sizeof(epicsFloat64));

    /* ---- Self-test & AI task (skip in sim mode) ---- */
    if (!simMode_) {
        ret = DAQmxSelfTestDevice(devName_);
        if (ret < 0) {
            reportDAQmxError(ret, functionName);
        } else {
            asynPrint(pasynUserSelf, ASYN_TRACE_FLOW,
                "%s:%s: device %s self-test passed\n",
                driverName, functionName, devName_);
        }

        char aiChanSpec[128];
        snprintf(aiChanSpec, sizeof(aiChanSpec), "%s/ai0:%d", devName_, MAX_AI_CHANNELS - 1);
        ret = DAQmxCreateTask("memsAI", &aiTask_);
        if (ret >= 0) {
            ret = DAQmxCreateAIVoltageChan(aiTask_, aiChanSpec, "",
                DAQmx_Val_Cfg_Default, -10.0, 10.0, DAQmx_Val_Volts, NULL);
        }
        if (ret >= 0) ret = DAQmxStartTask(aiTask_);
        if (ret < 0) reportDAQmxError(ret, functionName);
    }

    for (int i = 0; i < MAX_ADDR; i++) callParamCallbacks(i);

    /* Start threads AFTER all parameters are initialized and callbacks done.
     * Use epicsThreadSleep to ensure vtable is fully set up before threads
     * call virtual methods like getIntegerParam/setDoubleParam. */
    epicsThreadSleep(0.5);
    aiThreadId_ = epicsThreadCreate("nidaqAI", epicsThreadPriorityMedium,
        epicsThreadGetStackSize(epicsThreadStackMedium), aiThreadC, this);
    aoMonitorThreadId_ = epicsThreadCreate("nidaqAOMon", epicsThreadPriorityMedium,
        epicsThreadGetStackSize(epicsThreadStackMedium), aoMonitorThreadC, this);
    /* DIO and counter threads temporarily disabled for debugging */
    /* dioThreadId_ = epicsThreadCreate("nidaqDIO", epicsThreadPriorityLow,
        epicsThreadGetStackSize(epicsThreadStackMedium), dioThreadC, this);
    ctrThreadId_ = epicsThreadCreate("nidaqCTR", epicsThreadPriorityLow,
        epicsThreadGetStackSize(epicsThreadStackMedium), ctrThreadC, this); */

    asynPrint(pasynUserSelf, ASYN_TRACE_FLOW,
        "%s:%s: initialized %s — 4 AO, 32 AI, 16 DIO, 4 counters\n",
        driverName, functionName, devName_);
}

drvNiDAQMEMS::~drvNiDAQMEMS()
{
    aiRunning_ = 0;
    aoMonitorRunning_ = 0;
    dioRunning_ = 0;
    ctrRunning_ = 0;
    stopWaveGen();
    stopAIAcq();
    for (int i = 0; i < MAX_COUNTERS; i++) stopCounter(i);
    if (!simMode_) {
        if (aiTask_) { DAQmxStopTask(aiTask_); DAQmxClearTask(aiTask_); }
        if (aoTask_) DAQmxClearTask(aoTask_);
        if (doTask_) DAQmxClearTask(doTask_);
        if (dioReadTask_) { DAQmxStopTask(dioReadTask_); DAQmxClearTask(dioReadTask_); }
    }
    for (int i = 0; i < MAX_AO_CHANNELS; i++) free(userWF_[i]);
    free(aoBuffer_);
    free(doBuffer_);
    free(aiAcqBuffer_);
}

/* ================================================================== */
/*  AO Waveform Generation (hardware-timed)                            */
/* ================================================================== */

void drvNiDAQMEMS::buildAOBuffer(int numPoints, int numChans)
{
    for (int ch = 0; ch < numChans; ch++) {
        epicsFloat64 amplitude, offset;
        getDoubleParam(ch, P_WaveGenAmplitude, &amplitude);
        getDoubleParam(ch, P_WaveGenOffset, &offset);
        for (int j = 0; j < numPoints; j++) {
            aoBuffer_[j * numChans + ch] = userWF_[ch][j] * amplitude + offset;
        }
    }
}

int drvNiDAQMEMS::startWaveGen()
{
    static const char *functionName = "startWaveGen";
    int numPoints, continuous, markerEnable, markerWidth, trigSrc, trigEdge;
    double frequency;
    int32 ret;

    if (waveGenRunning_) stopWaveGen();

    getIntegerParam(P_WaveGenNumPoints, &numPoints);
    getDoubleParam(P_WaveGenFrequency, &frequency);
    getIntegerParam(P_WaveGenContinuous, &continuous);
    getIntegerParam(P_WaveGenMarkerEnable, &markerEnable);
    getIntegerParam(P_WaveGenMarkerWidth, &markerWidth);
    getIntegerParam(P_WaveGenTrigSrc, &trigSrc);
    getIntegerParam(P_WaveGenTrigEdge, &trigEdge);

    if (numPoints < 1 || numPoints > maxPoints_) {
        asynPrint(pasynUserSelf, ASYN_TRACE_ERROR,
            "%s:%s: invalid numPoints=%d\n", driverName, functionName, numPoints);
        return -1;
    }
    if (frequency <= 0.0) {
        asynPrint(pasynUserSelf, ASYN_TRACE_ERROR,
            "%s:%s: invalid frequency=%f\n", driverName, functionName, frequency);
        return -1;
    }

    /* Determine enabled channels */
    int numChans = 0;
    int chanIdx[MAX_AO_CHANNELS];
    for (int i = 0; i < MAX_AO_CHANNELS; i++) {
        int enable;
        getIntegerParam(i, P_WaveGenEnable, &enable);
        if (enable) chanIdx[numChans++] = i;
    }
    if (numChans == 0) {
        asynPrint(pasynUserSelf, ASYN_TRACE_ERROR,
            "%s:%s: no channels enabled\n", driverName, functionName);
        return -1;
    }

    /* Build channel spec */
    char aoChanSpec[128];
    if (numChans == 1) {
        snprintf(aoChanSpec, sizeof(aoChanSpec), "%s/ao%d", devName_, chanIdx[0]);
    } else {
        snprintf(aoChanSpec, sizeof(aoChanSpec), "%s/ao%d:%d",
                 devName_, chanIdx[0], chanIdx[numChans - 1]);
    }

    double requestedSampleRate = frequency * numPoints;
    buildAOBuffer(numPoints, numChans);

    double actualSampleRate = requestedSampleRate;
    double dwell, actualFrequency;

    if (!simMode_) {
        /* Clear old tasks */
        if (aoTask_) { DAQmxClearTask(aoTask_); aoTask_ = 0; }
        if (doTask_) { DAQmxClearTask(doTask_); doTask_ = 0; }

        ret = DAQmxCreateTask("memsAO", &aoTask_);
        if (ret < 0) { reportDAQmxError(ret, functionName); return -1; }

        ret = DAQmxCreateAOVoltageChan(aoTask_, aoChanSpec, "", -10.0, 10.0, DAQmx_Val_Volts, NULL);
        if (ret < 0) { reportDAQmxError(ret, functionName); return -1; }

        int32 sampleMode = continuous ? DAQmx_Val_ContSamps : DAQmx_Val_FiniteSamps;
        ret = DAQmxCfgSampClkTiming(aoTask_, "", requestedSampleRate,
            DAQmx_Val_Rising, sampleMode, (uInt64)numPoints);
        if (ret < 0) { reportDAQmxError(ret, functionName); return -1; }

        if (trigSrc > 0) {
            char trigTerm[128];
            snprintf(trigTerm, sizeof(trigTerm), "/%s/PFI%d", devName_, trigSrc - 1);
            int32 edge = trigEdge ? DAQmx_Val_Falling : DAQmx_Val_Rising;
            ret = DAQmxCfgDigEdgeStartTrig(aoTask_, trigTerm, edge);
            if (ret < 0) { reportDAQmxError(ret, functionName); return -1; }
        }

        uInt32 onboardSize = 0;
        DAQmxGetBufOutputOnbrdBufSize(aoTask_, &onboardSize);
        if (numPoints * numChans <= (int)onboardSize) {
            DAQmxSetWriteRegenMode(aoTask_, DAQmx_Val_AllowRegen);
        } else {
            for (int c = 0; c < numChans; c++) {
                char cn[128];
                snprintf(cn, sizeof(cn), "%s/ao%d", devName_, chanIdx[c]);
                DAQmxSetAOUsbXferReqSize(aoTask_, cn, 65536);
            }
        }

        DAQmxGetSampClkRate(aoTask_, &actualSampleRate);

        int32 written = 0;
        ret = DAQmxWriteAnalogF64(aoTask_, numPoints, 0, 10.0,
            DAQmx_Val_GroupByScanNumber, aoBuffer_, &written, NULL);
        if (ret < 0) { reportDAQmxError(ret, functionName); return -1; }

        if (markerEnable) {
            int pw = markerWidth;
            if (pw < 1) pw = 1;
            if (pw > numPoints) pw = numPoints;
            memset(doBuffer_, 0, maxPoints_ * sizeof(uInt8));
            for (int j = 0; j < pw; j++) doBuffer_[j] = 1;

            char sclk[128], strig[128];
            snprintf(sclk, sizeof(sclk), "/%s/ao/SampleClock", devName_);
            snprintf(strig, sizeof(strig), "/%s/ao/StartTrigger", devName_);

            int32 sm = continuous ? DAQmx_Val_ContSamps : DAQmx_Val_FiniteSamps;
            ret = DAQmxCreateTask("memsMarker", &doTask_);
            if (ret >= 0) ret = DAQmxCreateDOChan(doTask_, markerLine_, "", DAQmx_Val_ChanPerLine);
            if (ret >= 0) ret = DAQmxCfgSampClkTiming(doTask_, sclk, actualSampleRate,
                DAQmx_Val_Rising, sm, (uInt64)numPoints);
            if (ret >= 0) ret = DAQmxCfgDigEdgeStartTrig(doTask_, strig, DAQmx_Val_Rising);
            if (ret >= 0) ret = DAQmxWriteDigitalLines(doTask_, numPoints, 0, 10.0,
                DAQmx_Val_GroupByChannel, doBuffer_, &written, NULL);
            if (ret >= 0) ret = DAQmxStartTask(doTask_);
            if (ret < 0) reportDAQmxError(ret, functionName);
        }

        ret = DAQmxStartTask(aoTask_);
        if (ret < 0) { reportDAQmxError(ret, functionName); return -1; }
    }
    /* else: sim mode — skip all DAQmx, just update PVs */

    dwell = 1.0 / actualSampleRate;
    actualFrequency = actualSampleRate / numPoints;

    /* Update PVs */
    setIntegerParam(P_WaveGenCurrentPoint, 0);
    setDoubleParam(P_WaveGenDwell, dwell);
    setDoubleParam(P_WaveGenFrequency, actualFrequency);
    setDoubleParam(P_WaveGenTotalTime, dwell * numPoints);
    waveGenRunning_ = 1;
    setIntegerParam(P_WaveGenRun, 1);
    callParamCallbacks();

    asynPrint(pasynUserSelf, ASYN_TRACE_FLOW,
        "%s:%s: started AO, %d ch, %d pts, freq=%.6f Hz, rate=%.1f S/s\n",
        driverName, functionName, numChans, numPoints, actualFrequency, actualSampleRate);
    return 0;
}

int drvNiDAQMEMS::stopWaveGen()
{
    if (!waveGenRunning_) return 0;
    if (!simMode_) {
        if (doTask_) { DAQmxStopTask(doTask_); DAQmxClearTask(doTask_); doTask_ = 0; }
        if (aoTask_) { DAQmxStopTask(aoTask_); DAQmxClearTask(aoTask_); aoTask_ = 0; }
    }
    waveGenRunning_ = 0;
    setIntegerParam(P_WaveGenRun, 0);
    setIntegerParam(P_WaveGenCurrentPoint, 0);
    callParamCallbacks();
    return 0;
}

void drvNiDAQMEMS::aoMonitorThreadC(void *p) { ((drvNiDAQMEMS*)p)->aoMonitorThread(); }

void drvNiDAQMEMS::aoMonitorThread()
{
    epicsTimeStamp simStart;
    epicsTimeGetCurrent(&simStart);

    while (aoMonitorRunning_) {
        if (waveGenRunning_) {
            int numPoints, continuous;
            getIntegerParam(P_WaveGenNumPoints, &numPoints);
            getIntegerParam(P_WaveGenContinuous, &continuous);

            if (numPoints > 0) {
                int curPt = 0;

                if (simMode_) {
                    /* Simulate CurrentPoint based on elapsed time */
                    double frequency;
                    getDoubleParam(P_WaveGenFrequency, &frequency);
                    epicsTimeStamp now;
                    epicsTimeGetCurrent(&now);
                    double elapsed = epicsTimeDiffInSeconds(&now, &simStart);
                    double sampleRate = frequency * numPoints;
                    uInt64 totalGen = (uInt64)(elapsed * sampleRate);
                    curPt = (int)(totalGen % (uInt64)numPoints);
                    if (!continuous && totalGen >= (uInt64)numPoints) {
                        lock();
                        waveGenRunning_ = 0;
                        setIntegerParam(P_WaveGenRun, 0);
                        callParamCallbacks();
                        unlock();
                    }
                } else if (aoTask_) {
                    uInt64 totalGen = 0;
                    int32 ret = DAQmxGetWriteTotalSampPerChanGenerated(aoTask_, &totalGen);
                    if (ret >= 0) {
                        curPt = (int)(totalGen % (uInt64)numPoints);
                        if (!continuous && totalGen >= (uInt64)numPoints) {
                            lock();
                            waveGenRunning_ = 0;
                            setIntegerParam(P_WaveGenRun, 0);
                            callParamCallbacks();
                            unlock();
                        }
                    }
                }

                lock();
                setIntegerParam(P_WaveGenCurrentPoint, curPt);
                callParamCallbacks();
                unlock();
            }
        } else if (simMode_) {
            /* Reset sim timer when stopped so next start begins at 0 */
            epicsTimeGetCurrent(&simStart);
        }
        epicsThreadSleep(0.05);
    }
}

/* ================================================================== */
/*  AI Polled Thread                                                    */
/* ================================================================== */

void drvNiDAQMEMS::aiThreadC(void *p) { ((drvNiDAQMEMS*)p)->aiThread(); }

void drvNiDAQMEMS::aiThread()
{
    float64 data[MAX_AI_CHANNELS];
    int32 read;
    double simTime = 0;

    while (aiRunning_) {
        double scanPeriod;
        getDoubleParam(P_AIScanPeriod, &scanPeriod);
        if (scanPeriod < 0.01) scanPeriod = 0.01;

        if (simMode_) {
            /* Generate simulated AI values: slow sine waves with different phases */
            lock();
            for (int ch = 0; ch < MAX_AI_CHANNELS; ch++) {
                double val = 2.0 * sin(2.0 * M_PI * 0.1 * simTime + ch * 0.5)
                           + 0.1 * (rand() / (double)RAND_MAX - 0.5);
                setDoubleParam(ch, P_AIValue, val);
                callParamCallbacks(ch);
            }
            unlock();
            simTime += scanPeriod;
        } else {
            int32 ret = DAQmxReadAnalogF64(aiTask_, 1, 1.0,
                DAQmx_Val_GroupByChannel, data, MAX_AI_CHANNELS, &read, NULL);
            if (ret >= 0 && read > 0) {
                lock();
                for (int ch = 0; ch < MAX_AI_CHANNELS; ch++) {
                    setDoubleParam(ch, P_AIValue, data[ch]);
                    callParamCallbacks(ch);
                }
                unlock();
            }
        }
        epicsThreadSleep(scanPeriod);
    }
}

/* ================================================================== */
/*  AI Acquisition (hardware-timed)                                     */
/* ================================================================== */

int drvNiDAQMEMS::startAIAcq()
{
    static const char *functionName = "startAIAcq";
    int numPoints, trigSrc, clkSrc;
    double rate;
    int32 ret;

    if (aiAcqRunning_) stopAIAcq();

    getIntegerParam(P_AIAcqNumPoints, &numPoints);
    getDoubleParam(P_AIAcqRate, &rate);
    getIntegerParam(P_AIAcqTrigSrc, &trigSrc);
    getIntegerParam(P_AIAcqClkSrc, &clkSrc);

    if (numPoints < 1 || numPoints > maxPoints_) return -1;
    if (rate <= 0) return -1;

    if (simMode_) {
        /* Generate simulated acquisition data */
        lock();
        for (int ch = 0; ch < MAX_AI_CHANNELS; ch++) {
            for (int j = 0; j < numPoints; j++) {
                aiAcqBuffer_[ch * numPoints + j] =
                    2.0 * sin(2.0 * M_PI * j / numPoints + ch * 0.5);
            }
            doCallbacksFloat64Array(aiAcqBuffer_ + ch * numPoints, numPoints, P_AIAcqData, ch);
        }
        setIntegerParam(P_AIAcqNumAcquired, numPoints);
        callParamCallbacks();
        unlock();
        aiAcqRunning_ = 0;
        lock();
        setIntegerParam(P_AIAcqRun, 0);
        callParamCallbacks();
        unlock();
        return 0;
    }

    /* Must stop polled AI while acquisition runs (same physical channels) */
    if (aiTask_) { DAQmxStopTask(aiTask_); }

    if (aiAcqTask_) { DAQmxClearTask(aiAcqTask_); aiAcqTask_ = 0; }

    char aiChanSpec[128];
    snprintf(aiChanSpec, sizeof(aiChanSpec), "%s/ai0:%d", devName_, MAX_AI_CHANNELS - 1);

    ret = DAQmxCreateTask("memsAIAcq", &aiAcqTask_);
    if (ret < 0) { reportDAQmxError(ret, functionName); return -1; }

    ret = DAQmxCreateAIVoltageChan(aiAcqTask_, aiChanSpec, "",
        DAQmx_Val_Cfg_Default, -10.0, 10.0, DAQmx_Val_Volts, NULL);
    if (ret < 0) { reportDAQmxError(ret, functionName); return -1; }

    /* Clock source */
    const char *clkSource = "";
    if (clkSrc == 1) {
        static char aoClk[128];
        snprintf(aoClk, sizeof(aoClk), "/%s/ao/SampleClock", devName_);
        clkSource = aoClk;
    }

    ret = DAQmxCfgSampClkTiming(aiAcqTask_, clkSource, rate,
        DAQmx_Val_Rising, DAQmx_Val_FiniteSamps, (uInt64)numPoints);
    if (ret < 0) { reportDAQmxError(ret, functionName); return -1; }

    /* Trigger source */
    if (trigSrc == 1) {
        char trig[128];
        snprintf(trig, sizeof(trig), "/%s/ao/StartTrigger", devName_);
        ret = DAQmxCfgDigEdgeStartTrig(aiAcqTask_, trig, DAQmx_Val_Rising);
    } else if (trigSrc >= 2) {
        char trig[128];
        snprintf(trig, sizeof(trig), "/%s/PFI%d", devName_, trigSrc - 2);
        ret = DAQmxCfgDigEdgeStartTrig(aiAcqTask_, trig, DAQmx_Val_Rising);
    }
    if (ret < 0) { reportDAQmxError(ret, functionName); return -1; }

    ret = DAQmxStartTask(aiAcqTask_);
    if (ret < 0) { reportDAQmxError(ret, functionName); return -1; }

    /* Read data (blocking) in a thread-safe way */
    int totalSamples = numPoints * MAX_AI_CHANNELS;
    int32 sampsRead = 0;
    ret = DAQmxReadAnalogF64(aiAcqTask_, numPoints, rate > 0 ? (numPoints / rate + 5.0) : 30.0,
        DAQmx_Val_GroupByChannel, aiAcqBuffer_, totalSamples, &sampsRead, NULL);

    if (ret >= 0 && sampsRead > 0) {
        lock();
        setIntegerParam(P_AIAcqNumAcquired, sampsRead);
        /* Push per-channel waveform data */
        for (int ch = 0; ch < MAX_AI_CHANNELS; ch++) {
            doCallbacksFloat64Array(aiAcqBuffer_ + ch * numPoints, sampsRead, P_AIAcqData, ch);
        }
        callParamCallbacks();
        unlock();
    } else {
        reportDAQmxError(ret, functionName);
    }

    DAQmxStopTask(aiAcqTask_);
    DAQmxClearTask(aiAcqTask_);
    aiAcqTask_ = 0;

    /* Restart polled AI */
    if (aiTask_) DAQmxStartTask(aiTask_);

    aiAcqRunning_ = 0;
    lock();
    setIntegerParam(P_AIAcqRun, 0);
    callParamCallbacks();
    unlock();

    return 0;
}

int drvNiDAQMEMS::stopAIAcq()
{
    if (aiAcqTask_) {
        DAQmxStopTask(aiAcqTask_);
        DAQmxClearTask(aiAcqTask_);
        aiAcqTask_ = 0;
    }
    aiAcqRunning_ = 0;
    /* Restart polled AI */
    if (aiTask_) DAQmxStartTask(aiTask_);
    return 0;
}

/* ================================================================== */
/*  DIO                                                                 */
/* ================================================================== */

void drvNiDAQMEMS::dioThreadC(void *p) { ((drvNiDAQMEMS*)p)->dioThread(); }

void drvNiDAQMEMS::dioThread()
{
    while (dioRunning_) {
        if (simMode_) {
            /* In sim mode, DIOIn mirrors DIOOut for output lines */
            lock();
            for (int i = 0; i < MAX_DIO_LINES; i++) {
                int dir, out;
                getIntegerParam(i, P_DIODir, &dir);
                if (dir) { /* output: read back what was written */
                    getIntegerParam(i, P_DIOOut, &out);
                    setIntegerParam(i, P_DIOIn, out);
                } else { /* input: leave at 0 in sim */
                    setIntegerParam(i, P_DIOIn, 0);
                }
                callParamCallbacks(i);
            }
            unlock();
            epicsThreadSleep(0.1);
            continue;
        }
        /* Real hardware: periodically read input lines */
        TaskHandle readTask = 0;
        char lineBuf[256] = {0};
        int numInputs = 0;
        int inputMap[MAX_DIO_LINES]; /* maps read index -> line number */

        /* Build list of input lines */
        for (int i = 0; i < MAX_DIO_LINES; i++) {
            int dir;
            getIntegerParam(i, P_DIODir, &dir);
            if (dir == 0) { /* Input */
                char ln[128];
                snprintf(ln, sizeof(ln), "%s/port0/line%d", devName_, i);
                if (numInputs > 0) strncat(lineBuf, ",", sizeof(lineBuf) - strlen(lineBuf) - 1);
                strncat(lineBuf, ln, sizeof(lineBuf) - strlen(lineBuf) - 1);
                inputMap[numInputs] = i;
                numInputs++;
            }
        }

        if (numInputs > 0) {
            int32 ret = DAQmxCreateTask("", &readTask);
            if (ret >= 0) ret = DAQmxCreateDIChan(readTask, lineBuf, "", DAQmx_Val_ChanPerLine);
            if (ret >= 0) ret = DAQmxStartTask(readTask);
            if (ret >= 0) {
                uInt8 data[MAX_DIO_LINES];
                int32 read = 0, bytesPerSamp = 0;
                ret = DAQmxReadDigitalLines(readTask, 1, 1.0,
                    DAQmx_Val_GroupByChannel, data, MAX_DIO_LINES, &read, &bytesPerSamp, NULL);
                if (ret >= 0) {
                    lock();
                    for (int i = 0; i < numInputs; i++) {
                        setIntegerParam(inputMap[i], P_DIOIn, data[i] ? 1 : 0);
                        callParamCallbacks(inputMap[i]);
                    }
                    unlock();
                }
            }
            if (readTask) { DAQmxStopTask(readTask); DAQmxClearTask(readTask); }
        }

        epicsThreadSleep(0.1);
    }
}

void drvNiDAQMEMS::ctrThreadC(void *p) { ((drvNiDAQMEMS*)p)->ctrThread(); }

void drvNiDAQMEMS::ctrThread()
{
    while (ctrRunning_) {
        for (int ctr = 0; ctr < MAX_COUNTERS; ctr++) {
            int mode = 0;
            epicsInt32 countValue = 0;
            double freqValue = 0.0;
            const char *errTag = NULL;
            int32 errCode = 0;

            lock();
            getIntegerParam(ctr, P_CtrMode, &mode);
            unlock();

            if (simMode_) {
                double pulseFreq = 0.0;
                int pulseRun = 0;
                lock();
                getIntegerParam(ctr, P_CtrPulseRun, &pulseRun);
                if (mode == CTR_MODE_PULSE_GEN && pulseRun) {
                    getDoubleParam(ctr, P_CtrPulseFreq, &pulseFreq);
                }
                unlock();
                freqValue = pulseFreq;
            } else if (ctrTask_[ctr]) {
                if (mode == CTR_MODE_EDGE_COUNT) {
                    uInt32 count = 0;
                    int32 ret = DAQmxReadCounterScalarU32(ctrTask_[ctr], 0.1, &count, NULL);
                    if (ret >= 0) {
                        countValue = (epicsInt32)count;
                    } else {
                        errTag = "ctrThread:EdgeCount";
                        errCode = ret;
                    }
                } else if (mode == CTR_MODE_FREQ_MEAS) {
                    float64 freq = 0.0;
                    int32 ret = DAQmxReadCounterScalarF64(ctrTask_[ctr], 0.1, &freq, NULL);
                    if (ret >= 0) {
                        freqValue = freq;
                    } else {
                        errTag = "ctrThread:Freq";
                        errCode = ret;
                    }
                } else if (mode == CTR_MODE_PULSE_GEN) {
                    int pulseRun = 0;
                    double pulseFreq = 0.0;
                    lock();
                    getIntegerParam(ctr, P_CtrPulseRun, &pulseRun);
                    getDoubleParam(ctr, P_CtrPulseFreq, &pulseFreq);
                    unlock();
                    freqValue = pulseRun ? pulseFreq : 0.0;
                }
            }

            if (errTag) reportDAQmxError(errCode, errTag);

            lock();
            setIntegerParam(ctr, P_CtrCount, countValue);
            setDoubleParam(ctr, P_CtrFreq, freqValue);
            callParamCallbacks(ctr);
            unlock();
        }
        epicsThreadSleep(0.1);
    }
}

/* ================================================================== */
/*  Counters                                                            */
/* ================================================================== */

int drvNiDAQMEMS::configureCounter(int ctr, int mode)
{
    static const char *functionName = "configureCounter";
    int32 ret;

    stopCounter(ctr);

    if (mode == CTR_MODE_DISABLED) return 0;
    if (simMode_) return 0; /* In sim, mode is tracked in PVs only */

    char ctrChan[128];
    snprintf(ctrChan, sizeof(ctrChan), "%s/ctr%d", devName_, ctr);

    ret = DAQmxCreateTask("", &ctrTask_[ctr]);
    if (ret < 0) { reportDAQmxError(ret, functionName); return -1; }

    if (mode == CTR_MODE_EDGE_COUNT) {
        ret = DAQmxCreateCICountEdgesChan(ctrTask_[ctr], ctrChan, "",
            DAQmx_Val_Rising, 0, DAQmx_Val_CountUp);
        if (ret >= 0) ret = DAQmxStartTask(ctrTask_[ctr]);
    } else if (mode == CTR_MODE_FREQ_MEAS) {
        ret = DAQmxCreateCIFreqChan(ctrTask_[ctr], ctrChan, "",
            1.0, 1000000.0, DAQmx_Val_Hz, DAQmx_Val_Rising,
            DAQmx_Val_LowFreq1Ctr, 0.01, 1, NULL);
        if (ret >= 0) ret = DAQmxStartTask(ctrTask_[ctr]);
    } else if (mode == CTR_MODE_PULSE_GEN) {
        double freq, duty;
        getDoubleParam(ctr, P_CtrPulseFreq, &freq);
        getDoubleParam(ctr, P_CtrPulseDuty, &duty);
        if (freq <= 0) freq = 1000.0;
        if (duty <= 0 || duty >= 1) duty = 0.5;
        ret = DAQmxCreateCOPulseChanFreq(ctrTask_[ctr], ctrChan, "",
            DAQmx_Val_Hz, DAQmx_Val_Low, 0.0, freq, duty);
        /* Don't start yet — wait for PulseRun */
    }

    if (ret < 0) {
        reportDAQmxError(ret, functionName);
        DAQmxClearTask(ctrTask_[ctr]);
        ctrTask_[ctr] = 0;
        return -1;
    }
    return 0;
}

int drvNiDAQMEMS::startPulseGen(int ctr)
{
    static const char *functionName = "startPulseGen";
    if (simMode_) return 0;
    stopCounter(ctr);
    if (configureCounter(ctr, CTR_MODE_PULSE_GEN) < 0) return -1;

    int32 ret = DAQmxCfgImplicitTiming(ctrTask_[ctr], DAQmx_Val_ContSamps, 1000);
    if (ret >= 0) ret = DAQmxStartTask(ctrTask_[ctr]);
    if (ret < 0) { reportDAQmxError(ret, functionName); return -1; }
    return 0;
}

int drvNiDAQMEMS::stopCounter(int ctr)
{
    if (simMode_) return 0;
    if (ctrTask_[ctr]) {
        DAQmxStopTask(ctrTask_[ctr]);
        DAQmxClearTask(ctrTask_[ctr]);
        ctrTask_[ctr] = 0;
    }
    return 0;
}

/* ================================================================== */
/*  asynPortDriver overrides                                           */
/* ================================================================== */

asynStatus drvNiDAQMEMS::writeInt32(asynUser *pasynUser, epicsInt32 value)
{
    int function = pasynUser->reason;
    int addr;
    getAddress(pasynUser, &addr);
    asynStatus status = asynSuccess;

    if (function == P_WaveGenRun) {
        if (value) { if (startWaveGen() < 0) status = asynError; }
        else stopWaveGen();
    }
    else if (function == P_AIAcqRun) {
        if (value) {
            aiAcqRunning_ = 1;
            setIntegerParam(P_AIAcqRun, 1);
            callParamCallbacks();
            /* Run acquisition in current thread (ASYN_CANBLOCK) */
            if (startAIAcq() < 0) status = asynError;
        } else {
            stopAIAcq();
        }
    }
    else if (function == P_DIOOut) {
        if (!simMode_) {
            char lineName[128];
            snprintf(lineName, sizeof(lineName), "%s/port0/line%d", devName_, addr);
            TaskHandle wt = 0;
            int32 ret = DAQmxCreateTask("", &wt);
            if (ret >= 0) ret = DAQmxCreateDOChan(wt, lineName, "", DAQmx_Val_ChanPerLine);
            if (ret >= 0) ret = DAQmxStartTask(wt);
            if (ret >= 0) {
                uInt8 d = value ? 1 : 0;
                int32 written;
                ret = DAQmxWriteDigitalLines(wt, 1, 1, 1.0,
                    DAQmx_Val_GroupByChannel, &d, &written, NULL);
            }
            if (wt) { DAQmxStopTask(wt); DAQmxClearTask(wt); }
            if (ret < 0) { reportDAQmxError(ret, "writeInt32:DIO"); status = asynError; }
        }
        setIntegerParam(addr, P_DIOOut, value);
    }
    else if (function == P_CtrMode) {
        if (addr >= 0 && addr < MAX_COUNTERS) {
            setIntegerParam(addr, P_CtrMode, value);
            configureCounter(addr, value);
        }
    }
    else if (function == P_CtrReset) {
        if (value && addr >= 0 && addr < MAX_COUNTERS) {
            int mode;
            getIntegerParam(addr, P_CtrMode, &mode);
            if (mode == CTR_MODE_EDGE_COUNT) {
                stopCounter(addr);
                configureCounter(addr, mode);
            }
            setIntegerParam(addr, P_CtrCount, 0);
        }
    }
    else if (function == P_CtrPulseRun) {
        if (addr >= 0 && addr < MAX_COUNTERS) {
            if (value) {
                int mode;
                getIntegerParam(addr, P_CtrMode, &mode);
                if (mode == CTR_MODE_PULSE_GEN) {
                    if (startPulseGen(addr) < 0) status = asynError;
                }
            } else {
                /* Stop but keep task configured */
                if (ctrTask_[addr]) DAQmxStopTask(ctrTask_[addr]);
            }
            setIntegerParam(addr, P_CtrPulseRun, value);
        }
    }
    else {
        status = asynPortDriver::writeInt32(pasynUser, value);
    }

    callParamCallbacks(addr);
    return status;
}

asynStatus drvNiDAQMEMS::writeFloat64(asynUser *pasynUser, epicsFloat64 value)
{
    int function = pasynUser->reason;
    int addr;
    getAddress(pasynUser, &addr);

    asynStatus status = asynPortDriver::writeFloat64(pasynUser, value);

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
    else if ((function == P_CtrPulseFreq || function == P_CtrPulseDuty) &&
             addr >= 0 && addr < MAX_COUNTERS) {
        int mode = 0, running = 0;
        getIntegerParam(addr, P_CtrMode, &mode);
        getIntegerParam(addr, P_CtrPulseRun, &running);
        if (mode == CTR_MODE_PULSE_GEN && running) {
            if (startPulseGen(addr) < 0) status = asynError;
        }
        callParamCallbacks(addr);
    }

    return status;
}

asynStatus drvNiDAQMEMS::writeFloat64Array(asynUser *pasynUser,
                                            epicsFloat64 *value, size_t nElements)
{
    int function = pasynUser->reason;
    int addr;
    getAddress(pasynUser, &addr);

    if (function == P_WaveGenUserWF) {
        if (addr < 0 || addr >= MAX_AO_CHANNELS) return asynError;
        size_t n = nElements;
        if ((int)n > maxPoints_) n = maxPoints_;
        memcpy(userWF_[addr], value, n * sizeof(epicsFloat64));
        return asynSuccess;
    }

    return asynPortDriver::writeFloat64Array(pasynUser, value, nElements);
}

asynStatus drvNiDAQMEMS::readFloat64Array(asynUser *pasynUser,
                                           epicsFloat64 *value, size_t nElements, size_t *nIn)
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

/* ================================================================== */
/*  IOC shell registration                                              */
/* ================================================================== */

extern "C" {

static const iocshArg initArg0 = {"portName", iocshArgString};
static const iocshArg initArg1 = {"daqmxDevice", iocshArgString};
static const iocshArg initArg2 = {"maxPoints", iocshArgInt};
static const iocshArg *const initArgs[] = {&initArg0, &initArg1, &initArg2};
static const iocshFuncDef initFuncDef = {"drvNiDAQMEMSConfigure", 3, initArgs};

static void initCallFunc(const iocshArgBuf *args)
{
    new drvNiDAQMEMS(args[0].sval, args[1].sval, args[2].ival);
}

static void drvNiDAQMEMSRegister(void)
{
    iocshRegister(&initFuncDef, initCallFunc);
}

epicsExportRegistrar(drvNiDAQMEMSRegister);

} /* extern "C" */
