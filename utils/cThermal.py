
import logging, os
from pathlib import Path
import numpy as np
from astropy.io import fits
from datetime import datetime
import time

import serial 

from cLogging import setup_logging
import logging, yaml

os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

config_file = str(Path.cwd().resolve().parent / "config" / "thermal.yaml")


class cThermal:
    def __init__(self, night, config_file=config_file):
        # Define attributes
        # read from config file, loads default config_file
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)

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
        
    def connect(self):
        # Retrieve singleton reference to system object
        # Replace 'COM4' with your Arduino's serial port
        serial_port = self.config['COM_Port']
        baud_rate   = self.config['baud_rate'] # should be 9600

        self.ser = serial.Serial(serial_port, baud_rate)
        time.sleep(2)  # Wait for the serial connection to initialize

        # make one csv file for all reads until close connection - name file here
        self.start_time_tag = datetime.utcnow().strftime("%Y-%m-%dT%H.%M.%S.%f")
        self.csv_file_name  = Path(self.data_dir)  / f"{self.name}_{self.start_time_tag}.csv"
        self.logger.info(f"Thermal logging will save to {self.csv_file_name}")
        
        # initiate memory for data array
        self.alldata = {}

    def disconnect(self):
        """disconnect from serial port"""
        try:
            self.ser.close()
            self.logger.info('Closed Serial Connection for Thermal Logging')
        except:
            self.logger.warning('Could not close Serial connection for thermal logging')
        
    def read_data(self):
        """read one stream"""
        rawdata = self.ser.read_until(b'\n').decode('utf-8').strip()
        #try:
        self.alldata = self._process_data(rawdata,self.alldata)
        

    def _process_data(self, rawdata, alldata):
        """
        function to parse serial output and append rawdata to alldata dictionary
        check 'Triple_PID_Temp_Control' Arduino file for serial print out order

        inputs:
        -------
        data - 'str'
            raw data from serial read out
        
        outputs
        -------
        labeled in cats
        """
        lines = rawdata.split(',')

        # this is defined by C code on arduino - if edit that need to edit this
        label_order =['elapsed_time',
                    'input1','input2','input3',
                    'pct_power1','pct_power2','pct_power3',
                    'temp1a','temp1b',
                    'temp2a','temp2b',
                    'temp3a','temp3b',
                    'temp5','temp8','temp9','temp10']
        if len(lines) - 1 != len(label_order): raise ValueError('lines length and labels dont match!')
        
        # if data is none, initialize
        if len(alldata.keys())==0:
            alldata = {}
            for i, label in enumerate(label_order): alldata[label] = [float(lines[i])]
        else:
            for i, label in enumerate(label_order): alldata[label].append(float(lines[i]))
        
        return alldata

    def write(self, output_file_name):
        """
        write data to file, if file exists it will append

        inputs
        ------
        filePath - str
            path and filename to save to
        data - str
            data to write, should contain line break and delimiters already
        """
        output_file = os.path.join(self.data_dir, output_file_name)
        if not (os.path.isfile(output_file)):
            file = open(output_file, 'w')
            hdr = '#elapsed_time, in1, in2, in3, power1, power2, power3, temp1a, temp1b, temp2a, temp2b,\
                    temp3a, temp3b, temp5, temp8, temp9, temp10\n'
            file.write(hdr)
        else:
            file = open(output_file, 'a')
        
        file.write(self.alldata)

        file.close()

if __name__=='__main__':
    night = 'test'
    test = cThermal(night)
    test.connect()
    # need to figure out port, how does this work with usb hub?