# -*- coding: utf-8 -*-
"""
Created on Fri Aug  2 11:20:30 2022

@author: Ocean Insight Inc.
"""

from oceandirect.OceanDirectAPI import OceanDirectAPI, OceanDirectError, FeatureID

serialNumber = ""



def get_spec_raw_with_meta(device, spectraCount, integrationTime):
    try:
        #50ms
        device.set_integration_time(integrationTime);

        print("[START] Reading spectra with metadata for dev s/n = %s" % serialNumber, flush=True)

        spectraLength = device.get_formatted_spectrum_length()
        print("get_spec_raw_with_meta(device): spectraLength =  %d" % (spectraLength), flush=True)

        for i in range(spectraCount):
            spectra = []
            timestamp = []

            #15 = maxinum number of spectra returned per call
            total_spectra = device.Advanced.get_raw_spectrum_with_metadata(spectra, timestamp, 15)

            print("len(spectra) =  %d" % (total_spectra) )

            #print sample count on each spectra
            for x in range(total_spectra):
                print("spectra: %d, %d, %d, %d" % (spectra[x][100], spectra[x][105], spectra[x][110], spectra[x][115]), flush=True)

        print("")
    except OceanDirectError as e:
        [errorCode, errorMsg] = err.get_error_details()
        print("get_spec_raw_with_meta(device): exception / %d = %s" % (errorCode, errorMsg))


def revision(device):
    try:
        hwVersion = device.Advanced.get_revision_hardware()
        print("revision(device): hwVersion   =  %s " % hwVersion)
    except OceanDirectError as err:
        [errorCode, errorMsg] = err.get_error_details()
        print("revision(device): get_revision_hardware() / %d = %s" % (errorCode, errorMsg))

    try:
        fwVersion = device.Advanced.get_revision_firmware()
        print("revision(device): fwVersion   =  %s " % fwVersion)
    except OceanDirectError as err:
        [errorCode, errorMsg] = err.get_error_details()
        print("revision(device): get_revision_firmware() / %d = %s" % (errorCode, errorMsg))

    try:
        fpgaVersion = device.Advanced.get_revision_fpga()
        print("revision(device): fpgaVersion =  %s " % fpgaVersion)
        print("")
    except OceanDirectError as err:
        [errorCode, errorMsg] = err.get_error_details()
        print("revision(device): get_revision_fpga() / %d = %s" % (errorCode, errorMsg))
    print("")


def readFXBufferedSpectra(device, integrationTime):
    try:
        supported = device.is_feature_id_enabled(FeatureID.DATA_BUFFER)
        print("readFXBufferedSpectra(device): DATA_BUFFER feature supported  = %s" % supported, flush=True)

        if not supported:
            print("")
            return
    except OceanDirectError as err:
        [errorCode, errorMsg] = err.get_error_details()
        print("readFXBufferedSpectra(device): clear_data_buffer() / %d = %s" % (errorCode, errorMsg))

    try:
        #software trigger mode
        device.set_integration_time(integrationTime);
        device.set_trigger_mode(0)
        spectraToReadPerTrigger = 10;
        device.Advanced.clear_data_buffer()
        device.Advanced.set_data_buffer_enable(True)
        device.Advanced.set_data_buffer_capacity(5000)
        device.Advanced.set_number_of_backtoback_scans(spectraToReadPerTrigger)

        #The loop represent 5 triggers.
        #NOTE: 
        #SW trigger happens when you issue a get spectra command. So the for-loop here is just a 
        #symbolic representation of 5 triggers where each trigger will capture 10 spectra
        #and put them to buffer.
        for i in range(5):
            count = 0

            #read 10 buffered spectra from FX unit
            while count < spectraToReadPerTrigger:
                buffer_spectra = []
                timestamp = []

                try:
                    #NOTE:
                    #When buffering is enabled, this command is non-blocking and may return 0 spectra if buffer is empty.
                    #When buffering is disabled, this command will block.
                    #15 = maximum number of spectra returned per call
                    total = device.Advanced.get_raw_spectrum_with_metadata(buffer_spectra, timestamp, 15)

                    if total == 0:
                        #NOTE: probably add some delay here or key press.
                        print("*** no spectra in the buffer.")
                    else:
                        for y in range(total):
                            print("%d] %d ==> %d, %d, %d, %d, %d" % (count, timestamp[y], buffer_spectra[y][500], buffer_spectra[y][600],
                                                                     buffer_spectra[y][700], buffer_spectra[y][800], buffer_spectra[y][900]) )
                            count += 1
                            if count >= spectraToReadPerTrigger:
                                break
                    
                except OceanDirectError as err:
                    [errorCode, errorMsg] = err.get_error_details()
            print("")
        #after you got the buffered spectra then you can clear the buffer if you wanted to.
        device.Advanced.clear_data_buffer()
    except OceanDirectError as err:
        [errorCode, errorMsg] = err.get_error_details()
        print("readFXBufferedSpectra(device): exception / %d = %s" % (errorCode, errorMsg))
    print("")


#----------------------------------------------------------------------------------------
# Main program starts here :-P
#
# This sample code shows how to read buffered spectra from FX devices.
#----------------------------------------------------------------------------------------
if __name__ == '__main__':
    od = OceanDirectAPI()

    (major, minor, point) = od.get_api_version_numbers()
    #look for usb devices
    device_count = od.find_usb_devices()

    print("API Version   : %d.%d.%d " % (major, minor, point))
    print("Total Device  : %d" % device_count)

    if device_count == 0:
        print("No device found.")
    else:
        device_ids = od.get_device_ids()
        print("Device ids    : ", device_ids)
        print("\n")

        for id in device_ids:
            print("**********************************************")
            print("Device ID    : %d   " % id)

            device       = od.open_device(id)
            serialNumber = device.get_serial_number()

            print("Serial Number: %s \n" % serialNumber)

            revision(device)
            readFXBufferedSpectra(device, 10)
            readFXBufferedSpectra(device, 20)

 
            print("\n[END] Closing device [%s]!" % serialNumber)
            print("")
            od.close_device(id)
            
    od.shutdown()
    print("**** exiting program ****")





