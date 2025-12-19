#link to DL forum: https://forum.diffractionlimited.com/threads/sdk-request.10476/


import time
from win32com.client import Dispatch
import logging
import subprocess 
import sys, os
from pathlib import Path
from cLogging import setup_logging
import logging, yaml

ERROR = True
NOERROR = False
 
 # default config file
config_file = str(Path(__file__).resolve().parent.parent / "config" / "sbig.yaml")

##------------------------------------------------------------------------------
## Class: cCamera
##   import cSBIG 
##   cam = cSBIG.cSBIGmaxim('20250525')
##   cam.connect()
##------------------------------------------------------------------------------


class cSBIG:
    def __init__(self,night, source, config_file=config_file):
        # Define attributes
        # read from config file, loads default config_file
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)

        self.source    = source # feed it a source string for the header
        self.night     = night # YYYYMMDD
        self.name      = self.config['name'] # should be SBIG

        # make data and log dirs have sub direction of night string
        self.data_dir = Path(self.config['data_dir']) / self.night / self.name
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.log_dir = Path(self.config['log_dir']) / self.night
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # initiate logger
        self.logger = setup_logging(log_dir=self.log_dir,
                                    log_name=self.name,
                                    log_level=logging.DEBUG)
        
        # pull out detector settings
        self.xbin = self.config['xbin']
        self.ybin = self.config['ybin']
        self.set_temperature = self.config['set_temperature']

    def Expose(self,exptime,exptype):
        """
        Take exposure time, exosure type (0 or 1), and 

        exptime - seconds
        exptype - 1 for science, 0 for bias
        """
        if exptype == 1:
            # Science or flat image
            self.logger.info("Exposing light frame...")
            self.CAMERA.Expose(exptime,1,0) # 0 is for no filter
            while not self.CAMERA.ImageReady:
                time.sleep(1)
            self.logger.info("Light frame exposure and download complete!")
        
        if exptype == 0:
            # Bias or dark image, shutter closed
            self.logger.info("Exposing Dark frame...")
            self.CAMERA.Expose(exptime,0,-1)
            while not self.CAMERA.ImageReady:
                time.sleep(1)
            self.logger.info("Dark frame exposure and download complete!")
        
        
    def setFrame(self,opt,l=0,b=0,r=0,t=0):
        """
        """
        x = l
        y = t
        wx = r-l
        wy = b-t
        if opt == 'full':
            self.CAMERA.SetFullFrame()
            self.logger.info("Camera set to full-frame mode")
        elif opt == 'sub':
            self.CAMERA.StartX = x
            self.CAMERA.StartY = y
            self.CAMERA.NumX = wx 
            self.CAMERA.NumY = wy 
            self.logger.info("Camera set to subframe. Note: Inputs must consider binning.")
        else:
            self.logger.error("Set opt to either 'full' or 'sub'")
        

    def setBinning(self,binmode):
        tup = (1,2,4)
        if binmode in tup:
            self.CAMERA.BinX = binmode
            self.CAMERA.BinY = binmode
            self.logger.info("Camera binning set to %dx%d" % (binmode,binmode))
        else:
            self.logger.error("ERROR: Invalid binning specified")


    def saveImage(self,filename):
        try:
            self.CAMERA.SaveImage(filename)
            self.logger.info("saved file to " + filename)
        except:
            self.logger.error("Cannot save file")
            raise EnvironmentError('Halting program')


 
    def coolCCD(self):
        if not self.CAMERA.CanSetTemperature:
            self.logger.error("ERROR: cannot change temperature")
        else:
            self.CAMERA.CoolerOn = True
            time.sleep(0.5)
            ambTemp = self.CAMERA.Temperature
            if ambTemp < 15:
                settemp = -5
            elif (ambTemp >= 15) & (ambTemp < 20):
                settemp = 0
            elif (ambTemp >= 20) & (ambTemp < 25):
                settemp = 5
            else:
                settemp = ambTemp - 20
            
            self.CAMERA.TemperatureSetpoint = settemp
            time.sleep(5)
            self.logger.info("Cooling camera to " + str(settemp) + " C , Amb Temp= " + str(ambTemp))
            self.logger.info("Waiting for Cooler Power to Stabalize Below 35%" )
            tt = time.time()
            fails = 0
            while self.CAMERA.CoolerPower > 35:
                time.sleep(1)
                if time.time()  - tt > 300:
                    settemp += 5
                    self.CAMERA.TemperatureSetpoint = settemp
                    tt = time.time()
                    fails += 0
                    print('failed to cool once')
                if fails > 2:
                    print('temperature didnt reach setpoint')
                    break
            tt = time.time()
            while abs(self.CAMERA.Temperature - self.CAMERA.TemperatureSetpoint) > 0.4:
                time.sleep(1)   # sleep more because it usually overshoots
                if time.time() - tt > 300:
                    mail.send('CAMERA NOT SETTLED','The temperature of the camera never'
                        'settled to within 0.4 degrees C within the setpoint. Check out why'
                        'Continuing anyways.')
                    break


    def shutDown(self):
        if self.CAMERA.CoolerOn:
            # Warm up cooler
            if self.CAMERA.TemperatureSetpoint < self.CAMERA.AmbientTemperature:
                self.CAMERA.TemperatureSetpoint = self.CAMERA.AmbientTemperature
                self.logger.info('Warming Up CCD to Amb. Temp.')
                time.sleep(25)
            # Turn Cooler Off
            self.CAMERA.CoolerOn = False
        # Quit from camera, disconnect
        self.logger.info('Disconnecting and Quitting CAMERA')
        self.CAMERA.Quit()

    def restartmaxim(self):
        self.logger.info('Killing maxim') 
        subprocess.call(['Taskkill','/IM','MaxIm_DL.exe','/F'])

        time.sleep(15)

        self.logger.info('Reconnecting')
        self.connect()


    def recover(self):
        """
        copied this from minerva but logic doesnt make sense, fix..
        """
        self.nfailed = self.nfailed + 1

        try:
            self.shutDown()
        except:
            pass

        if self.nfailed == 1:
            # attempt to reconnect
            self.logger.warning('Camera failed to connect; retrying') 
            self.connect()
        elif self.nfailed == 2:
            # then restart maxim
            self.logger.warning('Camera failed to connect; restarting maxim') 
            self.restartmaxim()
        elif self.nfailed == 4:
            self.logger.error('Camera failed to connect!') 
            sys.exit()

    def connect(self, cooler=True):
        settleTime = 1200
        oscillationTime = 120.0

        # Connect to an instance of Maxim's camera control.
        # (This launches the app if needed)
        self.logger.info('Connecting to Maxim') 
        self.CAMERA = Dispatch("MaxIm.CCDCamera")

        # Connect to the camera 
        self.logger.info('Connecting to camera')
        try:
            self.CAMERA.LinkEnabled = True
            self.nfailed = 0
        except:
            self.nfailed=1
            self.logger.info('Camera failed to connect') 
            self.recover()

        # Prevent the camera from disconnecting when we exit
        self.logger.info('Preventing the camera from disconnecting when we exit') 
        self.CAMERA.DisableAutoShutdown = True

        # If we were responsible for launching Maxim, this prevents
        # Maxim from closing when our application exits
        self.logger.info('Preventing maxim from closing upon exit')
        maxim = Dispatch("MaxIm.Application")
        maxim.LockApp = True

        # Set binning
        self.setBinning(self.xbin)

        # Set to full frame
        self.setFrame('full')

        # Cool CDD
        if cooler == True:
            self.coolCCD()  
            
##
##    END OF 'cCamera' Class
##