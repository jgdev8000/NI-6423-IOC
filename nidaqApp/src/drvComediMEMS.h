/*
 * drvComediMEMS.h
 *
 * EPICS asynPortDriver for NI PCI-6036E via comedi.
 * - Hardware-timed AO waveform generation (2 channels, synchronized)
 * - Polled AI readback (16 channels)
 */

#ifndef DRV_COMEDI_MEMS_H
#define DRV_COMEDI_MEMS_H

#include <comedilib.h>
#include <asynPortDriver.h>
#include <epicsThread.h>
#include <epicsEvent.h>

/* Waveform generator parameters (global) */
#define P_WaveGenRunString          "WAVEGEN_RUN"
#define P_WaveGenFrequencyString    "WAVEGEN_FREQUENCY"
#define P_WaveGenDwellString        "WAVEGEN_DWELL"
#define P_WaveGenTotalTimeString    "WAVEGEN_TOTAL_TIME"
#define P_WaveGenNumPointsString    "WAVEGEN_NUM_POINTS"
#define P_WaveGenCurrentPointString "WAVEGEN_CURRENT_POINT"
#define P_WaveGenContinuousString   "WAVEGEN_CONTINUOUS"

/* Waveform generator parameters (per-channel, addr=0..1) */
#define P_WaveGenEnableString       "WAVEGEN_ENABLE"
#define P_WaveGenAmplitudeString    "WAVEGEN_AMPLITUDE"
#define P_WaveGenOffsetString       "WAVEGEN_OFFSET"
#define P_WaveGenUserWFString       "WAVEGEN_USER_WF"

/* Analog input parameters (per-channel, addr=0..15) */
#define P_AIValueString             "AI_VALUE"
#define P_AIRangeString             "AI_RANGE"

/* AI scan control */
#define P_AIScanPeriodString        "AI_SCAN_PERIOD"

#define MAX_AO_CHANNELS   2
#define MAX_AI_CHANNELS  16
#define MAX_ADDR         16  /* max of AO and AI channel counts */
#define DEFAULT_MAX_POINTS 4096

class drvComediMEMS : public asynPortDriver {
public:
    drvComediMEMS(const char *portName, const char *comediDevice, int maxPoints);
    virtual ~drvComediMEMS();

    /* Overrides from asynPortDriver */
    virtual asynStatus writeInt32(asynUser *pasynUser, epicsInt32 value);
    virtual asynStatus writeFloat64(asynUser *pasynUser, epicsFloat64 value);
    virtual asynStatus writeFloat64Array(asynUser *pasynUser,
                                         epicsFloat64 *value, size_t nElements);
    virtual asynStatus readFloat64Array(asynUser *pasynUser,
                                        epicsFloat64 *value, size_t nElements,
                                        size_t *nIn);

protected:
    /* Parameter indices */
    int P_WaveGenRun;
    int P_WaveGenFrequency;
    int P_WaveGenDwell;
    int P_WaveGenTotalTime;
    int P_WaveGenNumPoints;
    int P_WaveGenCurrentPoint;
    int P_WaveGenContinuous;
    int P_WaveGenEnable;
    int P_WaveGenAmplitude;
    int P_WaveGenOffset;
    int P_WaveGenUserWF;
    int P_AIValue;
    int P_AIRange;
    int P_AIScanPeriod;

private:
    /* Comedi state */
    comedi_t *dev_;
    int comedi_fd_;
    int aoSubdev_;
    int aiSubdev_;
    lsampl_t aoMaxdata_;
    lsampl_t aiMaxdata_;
    comedi_range *aoRange_;
    comedi_range *aiRange_[MAX_AI_CHANNELS];

    /* Waveform generation */
    int maxPoints_;
    epicsFloat64 *userWF_[MAX_AO_CHANNELS];
    lsampl_t *aoBuffer_;        /* interleaved output buffer */
    int aoBufferSize_;
    unsigned int aoChanlist_[MAX_AO_CHANNELS];
    int waveGenRunning_;
    int waveGenNumChans_;
    epicsThreadId waveGenThreadId_;
    epicsEventId waveGenStopEvent_;

    int startWaveGen();
    int stopWaveGen();
    void buildAOBuffer(int numPoints, int numChans);
    static void waveGenThreadC(void *drvPvt);
    void waveGenThread();

    /* AI polling */
    epicsThreadId aiThreadId_;
    int aiRunning_;
    static void aiThreadC(void *drvPvt);
    void aiThread();
};

#endif /* DRV_COMEDI_MEMS_H */
