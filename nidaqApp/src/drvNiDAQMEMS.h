/*
 * drvNiDAQMEMS.h
 *
 * EPICS asynPortDriver for NI USB-6423 via NI-DAQmx.
 * Full device support: AO waveform gen, AI polled + HW-timed, DIO, counters.
 */

#ifndef DRV_NIDAQMEMS_H
#define DRV_NIDAQMEMS_H

#include <NIDAQmx.h>
#include <asynPortDriver.h>
#include <epicsThread.h>

/* --- Waveform generator (global) --- */
#define P_WaveGenRunString          "WAVEGEN_RUN"
#define P_WaveGenFrequencyString    "WAVEGEN_FREQUENCY"
#define P_WaveGenDwellString        "WAVEGEN_DWELL"
#define P_WaveGenTotalTimeString    "WAVEGEN_TOTAL_TIME"
#define P_WaveGenNumPointsString    "WAVEGEN_NUM_POINTS"
#define P_WaveGenCurrentPointString "WAVEGEN_CURRENT_POINT"
#define P_WaveGenContinuousString   "WAVEGEN_CONTINUOUS"
#define P_WaveGenMarkerEnableString "WAVEGEN_MARKER_ENABLE"
#define P_WaveGenMarkerWidthString  "WAVEGEN_MARKER_WIDTH"
#define P_WaveGenTrigSrcString      "WAVEGEN_TRIG_SRC"
#define P_WaveGenTrigEdgeString     "WAVEGEN_TRIG_EDGE"

/* --- Waveform generator (per-channel, addr=0..3) --- */
#define P_WaveGenEnableString       "WAVEGEN_ENABLE"
#define P_WaveGenAmplitudeString    "WAVEGEN_AMPLITUDE"
#define P_WaveGenOffsetString       "WAVEGEN_OFFSET"
#define P_WaveGenUserWFString       "WAVEGEN_USER_WF"

/* --- Analog input (per-channel, addr=0..31) --- */
#define P_AIValueString             "AI_VALUE"
#define P_AIRangeString             "AI_RANGE"
#define P_AIScanPeriodString        "AI_SCAN_PERIOD"

/* --- AI acquisition (hardware-timed) --- */
#define P_AIAcqRunString            "AIACQ_RUN"
#define P_AIAcqRateString           "AIACQ_RATE"
#define P_AIAcqNumPointsString      "AIACQ_NUM_POINTS"
#define P_AIAcqTrigSrcString        "AIACQ_TRIG_SRC"
#define P_AIAcqClkSrcString         "AIACQ_CLK_SRC"
#define P_AIAcqNumAcquiredString    "AIACQ_NUM_ACQUIRED"
#define P_AIAcqDataString           "AIACQ_DATA"

/* --- Digital I/O (per-line, addr=0..15) --- */
#define P_DIOOutString              "DIO_OUT"
#define P_DIOInString               "DIO_IN"
#define P_DIODirString              "DIO_DIR"

/* --- Counters (per-counter, addr=0..3) --- */
#define P_CtrModeString             "CTR_MODE"
#define P_CtrCountString            "CTR_COUNT"
#define P_CtrResetString            "CTR_RESET"
#define P_CtrFreqString             "CTR_FREQ"
#define P_CtrPulseFreqString        "CTR_PULSE_FREQ"
#define P_CtrPulseDutyString        "CTR_PULSE_DUTY"
#define P_CtrPulseRunString         "CTR_PULSE_RUN"

#define MAX_AO_CHANNELS   4
#define MAX_AI_CHANNELS  32
#define MAX_DIO_LINES    16
#define MAX_COUNTERS      4
#define MAX_ADDR         32  /* must be >= all of the above */

/* Counter modes */
enum CtrMode {
    CTR_MODE_DISABLED = 0,
    CTR_MODE_EDGE_COUNT = 1,
    CTR_MODE_FREQ_MEAS = 2,
    CTR_MODE_PULSE_GEN = 3
};

class drvNiDAQMEMS : public asynPortDriver {
public:
    drvNiDAQMEMS(const char *portName, const char *daqmxDevice, int maxPoints);
    virtual ~drvNiDAQMEMS();

    virtual asynStatus writeInt32(asynUser *pasynUser, epicsInt32 value);
    virtual asynStatus writeFloat64(asynUser *pasynUser, epicsFloat64 value);
    virtual asynStatus writeFloat64Array(asynUser *pasynUser,
                                         epicsFloat64 *value, size_t nElements);
    virtual asynStatus readFloat64Array(asynUser *pasynUser,
                                        epicsFloat64 *value, size_t nElements,
                                        size_t *nIn);

protected:
    /* Parameter indices — waveform gen */
    int P_WaveGenRun;
    int P_WaveGenFrequency;
    int P_WaveGenDwell;
    int P_WaveGenTotalTime;
    int P_WaveGenNumPoints;
    int P_WaveGenCurrentPoint;
    int P_WaveGenContinuous;
    int P_WaveGenMarkerEnable;
    int P_WaveGenMarkerWidth;
    int P_WaveGenTrigSrc;
    int P_WaveGenTrigEdge;
    int P_WaveGenEnable;
    int P_WaveGenAmplitude;
    int P_WaveGenOffset;
    int P_WaveGenUserWF;

    /* Parameter indices — AI */
    int P_AIValue;
    int P_AIRange;
    int P_AIScanPeriod;

    /* Parameter indices — AI acquisition */
    int P_AIAcqRun;
    int P_AIAcqRate;
    int P_AIAcqNumPoints;
    int P_AIAcqTrigSrc;
    int P_AIAcqClkSrc;
    int P_AIAcqNumAcquired;
    int P_AIAcqData;

    /* Parameter indices — DIO */
    int P_DIOOut;
    int P_DIOIn;
    int P_DIODir;

    /* Parameter indices — Counters */
    int P_CtrMode;
    int P_CtrCount;
    int P_CtrReset;
    int P_CtrFreq;
    int P_CtrPulseFreq;
    int P_CtrPulseDuty;
    int P_CtrPulseRun;

private:
    char devName_[64];
    char markerLine_[128];

    int maxPoints_;
    int simMode_;       /* 1 = simulation (no hardware), 0 = real DAQmx */

    /* --- AO waveform generation --- */
    TaskHandle aoTask_;
    TaskHandle doTask_;
    epicsFloat64 *userWF_[MAX_AO_CHANNELS];
    epicsFloat64 *aoBuffer_;
    uInt8 *doBuffer_;
    int waveGenRunning_;
    epicsThreadId aoMonitorThreadId_;
    int aoMonitorRunning_;

    int startWaveGen();
    int stopWaveGen();
    void buildAOBuffer(int numPoints, int numChans);
    static void aoMonitorThreadC(void *drvPvt);
    void aoMonitorThread();

    /* --- AI polled --- */
    TaskHandle aiTask_;
    epicsThreadId aiThreadId_;
    int aiRunning_;
    static void aiThreadC(void *drvPvt);
    void aiThread();

    /* --- AI acquisition (HW-timed) --- */
    /* Note: aiAcqTask_ declared after maxPoints_ to match init order */
    TaskHandle aiAcqTask_;
    epicsFloat64 *aiAcqBuffer_;
    int aiAcqRunning_;

    int startAIAcq();
    int stopAIAcq();

    /* --- DIO --- */
    TaskHandle dioReadTask_;
    epicsThreadId dioThreadId_;
    int dioRunning_;
    static void dioThreadC(void *drvPvt);
    void dioThread();

    /* --- Counter monitor --- */
    epicsThreadId ctrThreadId_;
    int ctrRunning_;
    static void ctrThreadC(void *drvPvt);
    void ctrThread();

    /* --- Counters --- */
    TaskHandle ctrTask_[MAX_COUNTERS];

    int configureCounter(int ctr, int mode);
    int startPulseGen(int ctr);
    int stopCounter(int ctr);

    /* Error helper */
    void reportDAQmxError(int32 error, const char *function);
};

#endif /* DRV_NIDAQMEMS_H */
