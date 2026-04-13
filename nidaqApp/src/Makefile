TOP=../..

include $(TOP)/configure/CONFIG
#----------------------------------------
#  ADD MACRO DEFINITIONS AFTER THIS LINE
#=============================

#=============================
# Build the IOC application

PROD_IOC = nidaq
# nidaq.dbd will be created and installed
DBD += nidaq.dbd

# nidaq.dbd will be made up from these files:
nidaq_DBD += base.dbd
nidaq_DBD += asyn.dbd
nidaq_DBD += busySupport.dbd
nidaq_DBD += asSupport.dbd
nidaq_DBD += nidaqSupport.dbd

# Driver source
nidaq_SRCS += drvNiDAQMEMS.cpp

# nidaq_registerRecordDeviceDriver.cpp derives from nidaq.dbd
nidaq_SRCS += nidaq_registerRecordDeviceDriver.cpp

# Build the main IOC entry point on workstation OSs.
nidaq_SRCS_DEFAULT += nidaqMain.cpp
nidaq_SRCS_vxWorks += -nil-

# Add support libraries
nidaq_LIBS += asyn
nidaq_LIBS += busy
nidaq_LIBS += autosave

# Link NI-DAQmx
nidaq_SYS_LIBS += nidaqmx

# Finally link to the EPICS Base libraries
nidaq_LIBS += $(EPICS_BASE_IOC_LIBS)

#===========================

include $(TOP)/configure/RULES
#----------------------------------------
#  ADD RULES AFTER THIS LINE

