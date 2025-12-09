
from oceandirect.OceanDirectAPI import OceanDirectAPI, OceanDirectError, Spectrometer
from threading import Thread

def read_spectra(odapi: OceanDirectAPI, devId: int) -> None:
    try:
        device       = odapi.open_device(devId)
        serialNumber = device.get_serial_number()

        for i in range(200):
            spectra = device.get_formatted_spectrum()
            print("serial/spectra: %s ==> %d, %d, %d, %d" %
                 (serialNumber, spectra[100], spectra[101], spectra[102], spectra[103]), flush=True)

        odapi.close_device(id)
    except OceanDirectError as err:
        [errorCode, errorMsg] = err.get_error_details()
        print("read_spectra(): exception msg / %d = %s" % (errorCode, errorMsg))

def main():
    od = OceanDirectAPI()
    device_count = od.find_usb_devices()
    print("Total Device Found:  %d" % device_count)

    if device_count == 0:
        print("No device found.")
    else:
        device_ids = od.get_device_ids()
        threadList = []

        #build all threads
        for id in device_ids:
            threadList.append(Thread(target=read_spectra, args=(od, id)))

        #start them all together
        for threadValue in threadList:
            threadValue.start()

        #wait for all of them to complete
        for threadValue in threadList:
            threadValue.join()

if __name__ == '__main__':
    main()