#!../../bin/linux-x86_64/nidaq

< envPaths

epicsEnvSet("IOC",    "iocnidaq")
epicsEnvSet("PREFIX", "MEMS:")
epicsEnvSet("EPICS_CA_MAX_ARRAY_BYTES", "100000")

cd "${TOP}"

## Register all support components
dbLoadDatabase "dbd/nidaq.dbd"
nidaq_registerRecordDeviceDriver pdbbase

## Configure NI-DAQmx MEMS driver
## drvNiDAQMEMSConfigure(portName, daqmxDevice, maxPoints)
drvNiDAQMEMSConfigure("MEMS1", "Dev1", 10000)

## Load waveform generator global controls
dbLoadRecords("db/nidaq_WaveGen.template", "P=$(PREFIX),R=WaveGen:,PORT=MEMS1,ADDR=0,MAX_POINTS=10000,PREC=6")

## Load per-channel waveform generator records
dbLoadRecords("db/nidaq_WaveGenN.template", "P=$(PREFIX),R=WaveGen:Ch0:,PORT=MEMS1,ADDR=0,MAX_POINTS=10000,PREC=4")
dbLoadRecords("db/nidaq_WaveGenN.template", "P=$(PREFIX),R=WaveGen:Ch1:,PORT=MEMS1,ADDR=1,MAX_POINTS=10000,PREC=4")
dbLoadRecords("db/nidaq_WaveGenN.template", "P=$(PREFIX),R=WaveGen:Ch2:,PORT=MEMS1,ADDR=2,MAX_POINTS=10000,PREC=4")
dbLoadRecords("db/nidaq_WaveGenN.template", "P=$(PREFIX),R=WaveGen:Ch3:,PORT=MEMS1,ADDR=3,MAX_POINTS=10000,PREC=4")

## Load analog input records for 16 channels
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:0:,PORT=MEMS1,ADDR=0,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:1:,PORT=MEMS1,ADDR=1,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:2:,PORT=MEMS1,ADDR=2,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:3:,PORT=MEMS1,ADDR=3,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:4:,PORT=MEMS1,ADDR=4,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:5:,PORT=MEMS1,ADDR=5,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:6:,PORT=MEMS1,ADDR=6,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:7:,PORT=MEMS1,ADDR=7,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:8:,PORT=MEMS1,ADDR=8,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:9:,PORT=MEMS1,ADDR=9,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:10:,PORT=MEMS1,ADDR=10,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:11:,PORT=MEMS1,ADDR=11,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:12:,PORT=MEMS1,ADDR=12,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:13:,PORT=MEMS1,ADDR=13,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:14:,PORT=MEMS1,ADDR=14,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:15:,PORT=MEMS1,ADDR=15,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:16:,PORT=MEMS1,ADDR=16,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:17:,PORT=MEMS1,ADDR=17,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:18:,PORT=MEMS1,ADDR=18,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:19:,PORT=MEMS1,ADDR=19,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:20:,PORT=MEMS1,ADDR=20,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:21:,PORT=MEMS1,ADDR=21,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:22:,PORT=MEMS1,ADDR=22,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:23:,PORT=MEMS1,ADDR=23,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:24:,PORT=MEMS1,ADDR=24,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:25:,PORT=MEMS1,ADDR=25,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:26:,PORT=MEMS1,ADDR=26,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:27:,PORT=MEMS1,ADDR=27,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:28:,PORT=MEMS1,ADDR=28,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:29:,PORT=MEMS1,ADDR=29,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:30:,PORT=MEMS1,ADDR=30,PREC=6")
dbLoadRecords("db/nidaq_AI.template", "P=$(PREFIX),R=AI:31:,PORT=MEMS1,ADDR=31,PREC=6")

## AI scan period (seconds)
epicsEnvSet("AI_SCAN_PERIOD", "0.1")

## Hardware-timed AI acquisition
dbLoadRecords("db/nidaq_AIWaveform.template", "P=$(PREFIX),R=AIAcq:,PORT=MEMS1,ADDR=0,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:0:,PORT=MEMS1,ADDR=0,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:1:,PORT=MEMS1,ADDR=1,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:2:,PORT=MEMS1,ADDR=2,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:3:,PORT=MEMS1,ADDR=3,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:4:,PORT=MEMS1,ADDR=4,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:5:,PORT=MEMS1,ADDR=5,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:6:,PORT=MEMS1,ADDR=6,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:7:,PORT=MEMS1,ADDR=7,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:8:,PORT=MEMS1,ADDR=8,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:9:,PORT=MEMS1,ADDR=9,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:10:,PORT=MEMS1,ADDR=10,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:11:,PORT=MEMS1,ADDR=11,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:12:,PORT=MEMS1,ADDR=12,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:13:,PORT=MEMS1,ADDR=13,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:14:,PORT=MEMS1,ADDR=14,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:15:,PORT=MEMS1,ADDR=15,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:16:,PORT=MEMS1,ADDR=16,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:17:,PORT=MEMS1,ADDR=17,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:18:,PORT=MEMS1,ADDR=18,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:19:,PORT=MEMS1,ADDR=19,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:20:,PORT=MEMS1,ADDR=20,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:21:,PORT=MEMS1,ADDR=21,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:22:,PORT=MEMS1,ADDR=22,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:23:,PORT=MEMS1,ADDR=23,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:24:,PORT=MEMS1,ADDR=24,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:25:,PORT=MEMS1,ADDR=25,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:26:,PORT=MEMS1,ADDR=26,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:27:,PORT=MEMS1,ADDR=27,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:28:,PORT=MEMS1,ADDR=28,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:29:,PORT=MEMS1,ADDR=29,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:30:,PORT=MEMS1,ADDR=30,MAX_POINTS=10000")
dbLoadRecords("db/nidaq_AIWaveformN.template", "P=$(PREFIX),R=AIAcq:31:,PORT=MEMS1,ADDR=31,MAX_POINTS=10000")

## Digital I/O (port0, 16 lines)
dbLoadRecords("db/nidaq_DIO.template", "P=$(PREFIX),R=DIO:0:,PORT=MEMS1,ADDR=0")
dbLoadRecords("db/nidaq_DIO.template", "P=$(PREFIX),R=DIO:1:,PORT=MEMS1,ADDR=1")
dbLoadRecords("db/nidaq_DIO.template", "P=$(PREFIX),R=DIO:2:,PORT=MEMS1,ADDR=2")
dbLoadRecords("db/nidaq_DIO.template", "P=$(PREFIX),R=DIO:3:,PORT=MEMS1,ADDR=3")
dbLoadRecords("db/nidaq_DIO.template", "P=$(PREFIX),R=DIO:4:,PORT=MEMS1,ADDR=4")
dbLoadRecords("db/nidaq_DIO.template", "P=$(PREFIX),R=DIO:5:,PORT=MEMS1,ADDR=5")
dbLoadRecords("db/nidaq_DIO.template", "P=$(PREFIX),R=DIO:6:,PORT=MEMS1,ADDR=6")
dbLoadRecords("db/nidaq_DIO.template", "P=$(PREFIX),R=DIO:7:,PORT=MEMS1,ADDR=7")
dbLoadRecords("db/nidaq_DIO.template", "P=$(PREFIX),R=DIO:8:,PORT=MEMS1,ADDR=8")
dbLoadRecords("db/nidaq_DIO.template", "P=$(PREFIX),R=DIO:9:,PORT=MEMS1,ADDR=9")
dbLoadRecords("db/nidaq_DIO.template", "P=$(PREFIX),R=DIO:10:,PORT=MEMS1,ADDR=10")
dbLoadRecords("db/nidaq_DIO.template", "P=$(PREFIX),R=DIO:11:,PORT=MEMS1,ADDR=11")
dbLoadRecords("db/nidaq_DIO.template", "P=$(PREFIX),R=DIO:12:,PORT=MEMS1,ADDR=12")
dbLoadRecords("db/nidaq_DIO.template", "P=$(PREFIX),R=DIO:13:,PORT=MEMS1,ADDR=13")
dbLoadRecords("db/nidaq_DIO.template", "P=$(PREFIX),R=DIO:14:,PORT=MEMS1,ADDR=14")
dbLoadRecords("db/nidaq_DIO.template", "P=$(PREFIX),R=DIO:15:,PORT=MEMS1,ADDR=15")

## Counters (4 channels)
dbLoadRecords("db/nidaq_Counter.template", "P=$(PREFIX),R=Ctr:0:,PORT=MEMS1,ADDR=0")
dbLoadRecords("db/nidaq_Counter.template", "P=$(PREFIX),R=Ctr:1:,PORT=MEMS1,ADDR=1")
dbLoadRecords("db/nidaq_Counter.template", "P=$(PREFIX),R=Ctr:2:,PORT=MEMS1,ADDR=2")
dbLoadRecords("db/nidaq_Counter.template", "P=$(PREFIX),R=Ctr:3:,PORT=MEMS1,ADDR=3")

cd "${TOP}/iocBoot/${IOC}"

## Autosave setup
set_savefile_path(".", "autosave")
set_requestfile_path(".", "")
save_restoreSet_DatedBackupFiles(1)
set_pass0_restoreFile("autosave_mems.sav")
set_pass1_restoreFile("autosave_mems.sav")

iocInit

## Start autosave after iocInit
makeAutosaveFileFromDbInfo("autosave_mems.req", "autosaveFields")
create_monitor_set("autosave.req", 10, "PREFIX=$(PREFIX)")
create_monitor_set("autosave_mems.req", 10)
