
import os, csv, sys
from datetime import datetime
import numpy as np
import matplotlib.pylab as plt
from pathlib import Path
from cLogging import setup_logging
import logging, yaml


from typing import List

# load ocean direct code here TODO: move where it lives
sys.path.insert(0, str(Path.cwd() / "telluric" ))
from oceandirect.OceanDirectAPI import OceanDirectAPI, OceanDirectError, Spectrometer

# Functions useful for reading spectra from the Ocean Insight HR4Pro spectrometer
odapi = OceanDirectAPI()

# default config file
config_file = str(Path.cwd().resolve().parent / "config" / "h4rpro.yaml")


class cH4RPro:
    def __init__(self,night, source, config_file=config_file):
        # Define attributes
        # read from config file, loads default config_file
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)

        self.source    = source # feed it a source string for the header
        self.night     = night # YYYYMMDD
        self.name      = self.config['name'] # should be H4Rpro

        # make data and log dirs have sub direction of night string
        self.data_dir = Path(self.config['data_dir']) / self.night / self.name
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.log_dir = Path(self.config['log_dir']) / self.night
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # initiate logger
        self.logger = setup_logging(log_dir=self.log_dir,
                                    log_name=self.name,
                                    log_level=logging.DEBUG)
        

    def connect(self,custom_wavelength=False):
        """find serial number of device and connect. 
        Also store key device properties.
        
        custom_wavelength Bool
            True is want to load custom wavelength params
            False will load those stored on device which may not be accurate"""
        serialNumberList = self._read_all_serial_numbers()
        if len(serialNumberList) == 0:
            self.logger.error("No H4RPro device found.")
        else:
            serialNumber = serialNumberList[0]

        odapi = OceanDirectAPI()
        odapi.find_usb_devices()
        devId = odapi.get_device_ids()[0]
        self.device = odapi.open_device(devId)
        devSerialNumber = self.device.get_serial_number()
        if devSerialNumber != serialNumber:
            print("Error: Serial number does not match.")
            return  # Exit the function if the serial numbers don't match
        
        spectrometer_advanced = Spectrometer.Advanced(self.device)
        self.nonlinearity_coeffs   = spectrometer_advanced.get_nonlinearity_coeffs()
        
        if custom_wavelength: 
            self.wavelength_coeffs = self._get_custom_wavelength_coeffs()
            self.logger.info('Using custom wavelength coefficients for H4RPro')
        else:
            self.wavelength_coeffs = spectrometer_advanced.get_wavelength_coeffs()
            self.logger.warning('Using old wavelength coefficients for H4RPro')

    def disconnect(self):
        self.device.close_device()

    def _get_custom_wavelength_coeffs(self):
        """custom coeffs defined in config file
        format is c[0] + c[1] * pixels + c[2] * pixels**2 + c[3] * pixels**3 """
        return self.config['h4rpro_coeffs']
    
    def _read_all_serial_numbers(self) -> List[str]:
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

        self.logger.info("Reading H4RPRO Serial Numbers")
        return serialNumberList

    def correct_nonlinearity(self,raw_intensity, nonlinearity_coeffs):
        """Corrects for nonlinearity using the coefficients provided by the spectrometer."""
        raw_intensity = np.array(raw_intensity, dtype=float)
        corrected_intensity = raw_intensity.copy()
        # corrected_intensity = np.array(corrected_intensity)

        for i, coeff in enumerate(nonlinearity_coeffs):
            corrected_intensity += coeff * raw_intensity**(i + 1)
            
        return corrected_intensity

    def writeSpectraToCSV(self,wavelengths: List, spectra: List, output_file_name: str) -> None:
        """
        Writes the wavelengths and spectra to a CSV file.
        
        Parameters:
        wavelengths (List): List of wavelengths.
        spectra (List): List of spectra, where each spectrum is a List of intensity values.
        output_file_name (str): The name of the output CSV file.
        """
        self.logger.info("Writing H4RPRO data to %s"%output_file_name)
        # Create the CSV file
        output_file = os.path.join(self.data_dir, output_file_name)
        with open(output_file, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            
            # Write the header
            header = ['Wavelength'] + [f'Spectrum_{i+1}' for i in range(len(spectra))]
            csv_writer.writerow(header)
            
            # Write the data rows
            for i in range(len(wavelengths)):
                row = [wavelengths[i]] + [spectrum[i] for spectrum in spectra]
                csv_writer.writerow(row)

    def correct_spectrum(self,raw_spectrum, wavelength_coeffs, nonlinearity_coeffs):
        """Corrects the spectrum for nonlinearity and converts pixel values to wavelengths."""
        c = wavelength_coeffs
        num_data_points = len(raw_spectrum) # 3648

        pixels = np.arange(num_data_points)
        wavelengths = c[0] + c[1] * pixels + c[2] * pixels**2 + c[3] * pixels**3 # polynomial equation to convert pixel values to wavelengths

        correct_spectrum = self.correct_nonlinearity(raw_spectrum, nonlinearity_coeffs)

        return wavelengths, correct_spectrum

    def read_spectra(self, integrationTimeUs: int, spectraToRead: int):
        """The main function to take spectral data. 
        Will use the calibration parameters to match wavelengths and correct nonlinearity, 
        then takes a certain number of exposures with a given exposure time in microseconds. 
        """
        all_spectra = [[] for _ in range(spectraToRead)]
        self.device.set_integration_time(integrationTimeUs)
        for i in range(spectraToRead):
            self.logger.info("Reading and correcting H4RPRO Spectrum")
            raw_spectrum = self.device.get_formatted_spectrum()
            wavelengths, spectrum = self.correct_spectrum(raw_spectrum, self.wavelength_coeffs, self.nonlinearity_coeffs)
            all_spectra[i] = spectrum
            time.sleep(0.1)

        # save name of CSV for spectrum
        self.last_time_tag = datetime.utcnow().strftime("%Y-%m-%dT%H.%M.%S.%f")
        self.csv_file_name  = Path(self.data_dir)  / f"{self.last_time_tag}_{self.source}.csv"
    
        # save
        self.writeSpectraToCSV(wavelengths, all_spectra, self.csv_file_name)

        return wavelengths, all_spectra



if __name__ == '__main__':
    config = {}
    config['log_dir'] = './'
    config['data_dir'] = './'
    config['h4rpro_coeffs'] = [-4.96439687e-11, -1.50967200e-6, 6.02120089e-2, 5.77925772e2]
    h4rpro  = cH4RPro(night='20251208', source='dark')#,config=config)
    h4rpro.connect()

    t_sec             = .02
    integrationTimeUs = int(t_sec *10**6)
    spectraToRead     = 5
    
    wl, flx = h4rpro.read_spectra(integrationTimeUs, spectraToRead)
    h4rpro.disconnect()

    # plot
    plt.figure('telluricspectra')
    offset=0.958 # calibrated it and need an added 0.74nm offset, but this may change over time
    #plt.axvline(607.4)
    plt.plot(wl-offset,np.median(flx,axis=0))
    plt.xlabel('Wavelength')
