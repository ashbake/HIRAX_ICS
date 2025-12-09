#link to DL forum: https://forum.diffractionlimited.com/threads/sdk-request.10476/


import time
import alpaca
import logging
import subprocess 
import sys

ERROR = True
NOERROR = False
 
##------------------------------------------------------------------------------
## Class: cCamera
##------------------------------------------------------------------------------
address = '0812A3C8' #i have no idea what the address would be for a USB device
device_number = 0
camera = alpaca.Camera(address=address, device_number=device_number)
camera.Connected = True

# alpaca.Camera
# can put in code here
"""
 'abortexposure',
 'action',
 'bayeroffsetx',
 'bayeroffsety',
 'binx',
 'biny',
 'camerastate',
 'cameraxsize',
 'cameraysize',
 'canabortexposure',
 'canasymmetricbin',
 'canfastreadout',
 'cangetcoolerpower',
 'canpulseguide',
 'cansetccdtemperature',
 'canstopexposure',
 'ccdtemperature',
 'commandblind',
 'commandbool',
 'commandstring',
 'connected',
 'cooleron',
 'coolerpower',
 'description',
 'driverinfo',
 'driverversion',
 'electronsperadu',
 'exposuremax',
 'exposuremin',
 'exposureresolution',
 'fastreadout',
 'fullwellcapacity',
 'gain',
 'gainmax',
 'gainmin',
 'gains',
 'hasshutter',
 'heatsinktemperature',
 'imagearray',
 'imagearrayvariant',
 'imageready',
 'interfaceversion',
 'ispulseguiding',
 'lastexposureduration',
 'lastexposurestarttime',
 'maxadu',
 'maxbinx',
 'maxbiny',
 'name',
 'numx',
 'numy',
 'percentcompleted',
 'pixelsizex',
 'pixelsizey',
 'pulseguide',
 'readoutmode',
 'readoutmodes',
 'sensorname',
 'sensortype',
 'setccdtemperature',
 'startexposure',
 'startx',
 'starty',
 'stopexposure'"""