from zaber_motion import Units
from zaber_motion.ascii import Connection

import sys

position = 'acquisition'# sys.argv[0]

position_options = ['acquisition','science','custom']

while position not in position_options:
    position = input ("Please specify position: 'acquisition', 'science', or 'custom'")
    # tell user error and request new position

from serial.tools import list_ports
port = list(list_ports.comports())
for p in port:
    print(p.device)


with Connection.open_serial_port("/dev/cu.usbserial-AB0LD7M9") as connection:
    connection.enable_alerts()

    device_list = connection.detect_devices()
    print("Found {} devices".format(len(device_list)))

    device = device_list[0]

    axis = device.get_axis(1)
    if not axis.is_homed():
        axis.home()

    if position=='acquisition':
        # Move to 10mm (update iwth position of acquisition full field mode)
        axis.move_absolute(10, Units.LENGTH_MILLIMETRES)
    
    if position=='science':
        axis.move_absolute(0, Units.LENGTH_MILLIMETRES)

    if position =='custom':
        text = input ("Relative or Absolute Movement (type R or A)?")
        if text=='R': 
            text2 = input ("Type position offset in mm")
            axis.move_relative(float(text2), Units.LENGTH_MILLIMETRES)
        if text=='A': 
            text2 = input ("Type absolute position in mm")
            axis.absolute(float(text2), Units.LENGTH_MILLIMETRES)


# edit this in future such that can change position without having
# to restart code and rehome


