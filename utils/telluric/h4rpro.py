
import os, csv, time
import numpy as np
import matplotlib.pylab as plt

from typing import List
from oceandirect.OceanDirectAPI import OceanDirectAPI, OceanDirectError, Spectrometer
# Functions useful for reading spectra from the Ocean Insight HR4Pro spectrometer
odapi = OceanDirectAPI()

def read_all_serial_numbers() -> List[str]:
    """
    Read all devices' serial numbers. Later on we assign one serial number for each
    process.
    """
    odapi = OceanDirectAPI()
    try:
        device_count = odapi.find_usb_devices()
        serialNumberList = []
        if device_count > 0:
            device_ids = odapi.get_device_ids()
            for devId in device_ids:
                device = odapi.open_device(devId)
                serialNumberList.append(device.get_serial_number())
                device.close_device()
        odapi.shutdown()
    except OceanDirectError as err:
        [errorCode, errorMsg] = err.get_error_details()
        #print("read_all_serial_numbers(): exception / error / %s / %d = %s" %
        #     (serialNumber, errorCode, errorMsg))
    return serialNumberList


def correct_nonlinearity(raw_intensity, nonlinearity_coeffs):
    """Corrects for nonlinearity using the coefficients provided by the spectrometer."""
    raw_intensity = np.array(raw_intensity, dtype=float)
    corrected_intensity = raw_intensity.copy()
    # corrected_intensity = np.array(corrected_intensity)

    for i, coeff in enumerate(nonlinearity_coeffs):
        corrected_intensity += coeff * raw_intensity**(i + 1)
        
    return corrected_intensity


def writeSpectraToCSV(wavelengths: List, spectra: List, output_file_name: str) -> None:
    """
    Writes the wavelengths and spectra to a CSV file.
    
    Parameters:
    wavelengths (List): List of wavelengths.
    spectra (List): List of spectra, where each spectrum is a List of intensity values.
    output_file_name (str): The name of the output CSV file.
    """
    # Create the CSV file
    output_file = os.path.join(os.getcwd(), output_file_name)
    with open(output_file, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        
        # Write the header
        header = ['Wavelength'] + [f'Spectrum_{i+1}' for i in range(len(spectra))]
        csv_writer.writerow(header)
        
        # Write the data rows
        for i in range(len(wavelengths)):
            row = [wavelengths[i]] + [spectrum[i] for spectrum in spectra]
            csv_writer.writerow(row)


def correct_spectrum(raw_spectrum, wavelength_coeffs, nonlinearity_coeffs):
    """Corrects the spectrum for nonlinearity and converts pixel values to wavelengths."""
    c = wavelength_coeffs
    num_data_points = len(raw_spectrum) # 3648

    pixels = np.arange(num_data_points)
    wavelengths = c[0] + c[1] * pixels + c[2] * pixels**2 + c[3] * pixels**3 # polynomial equation to convert pixel values to wavelengths

    correct_spectrum = correct_nonlinearity(raw_spectrum, nonlinearity_coeffs)

    return wavelengths, correct_spectrum


def read_spectra(serialNumber: str, integrationTimeUs: int, spectraToRead: int, csv_file_name: str):
    """The main function to take spectral data. 
    Will use the calibration parameters to match wavelengths and correct nonlinearity, 
    then takes a certain number of exposures with a given exposure time in microseconds. 
    Specify the file name for the csv file where the output data will be saved."""
    #read_all_serial_numbers()
    odapi = OceanDirectAPI()
    odapi.find_usb_devices()
    devId = odapi.get_device_ids()[0]
    device = odapi.open_device(devId)
    devSerialNumber = device.get_serial_number()
    if devSerialNumber != serialNumber:
        print("Error: Serial number does not match.")
        return  # Exit the function if the serial numbers don't match
    
    spectrometer_advanced = Spectrometer.Advanced(device)
    wavelength_coeffs = spectrometer_advanced.get_wavelength_coeffs()
    nonlinearity_coeffs = spectrometer_advanced.get_nonlinearity_coeffs()
    
    all_spectra = [[] for _ in range(spectraToRead)]
    device.set_integration_time(integrationTimeUs)
    for i in range(spectraToRead):
        raw_spectrum = device.get_formatted_spectrum()
        wavelengths, spectrum = correct_spectrum(raw_spectrum, wavelength_coeffs, nonlinearity_coeffs)
        all_spectra[i] = spectrum
        time.sleep(0.1)

    device.close_device()
    writeSpectraToCSV(wavelengths, all_spectra, csv_file_name)

    return wavelengths, all_spectra



if __name__ == '__main__':
    # Find Serial Number
    serialNumberList = read_all_serial_numbers()
    print("Device Serial Numbers:  %s" % ', '.join(map(str, serialNumberList)) )
    if len(serialNumberList) == 0:
        print("No device found.")
    else:
        serialNumber = serialNumberList[0]
    plt.ion()

   # load bkg file
    bkg_file = 'outputs\\bkg_arclamp_2025-05-26T00.03.37.csv'
    bkg_data = np.mean(np.loadtxt(bkg_file,delimiter=',',skiprows=1).T[1:],axis=0)
    #plt.plot(wl,bkg_data)
    # define things
    t_sec             = .02
    integrationTimeUs = int(t_sec *10**6)
    spectraToRead     = 5
    tag               = 'sep3_607filter_%ss'%t_sec
    csv_file_name     = 'outputs\\%s_%s.csv'%(tag,time.strftime("%Y-%m-%dT%H.%M.%S", time.gmtime()))
    
    
    wl, flx = read_spectra(serialNumber, integrationTimeUs, spectraToRead, csv_file_name)
    

    # plot
    plt.figure('telluricspectra')
    #plt.plot(wl,flx[0])
    #plt.plot(wl,flx[0])
    #plt.plot(wl,flx[2])
    offset=0.958 # calibrated it and need an added 0.74nm offset, but this may change over time
    #plt.axvline(607.4)
    plt.plot(wl-offset,np.median(flx,axis=0))
    plt.xlabel('Wavelength')
