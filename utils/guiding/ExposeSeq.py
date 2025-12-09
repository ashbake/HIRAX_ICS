## take guide images 
## locate star offset
## trasnalte to arc 
## send to telescope
#
# setup:
# - guide data folder set to current date
# - code checks this folder for new data
# - reference location hard coded for now, but ref first image
#
# sequence:
# 
#  - check for new file in guide folder
#  - if new file, open it
#  - process file through source finder
#  - calculate offset funciton
#  - convert offset to arcsec
#  - save result to TCS format?
####################

import matplotlib.pylab as plt
import os,time

plt.ion()


if __name__=='__main__':
    # take image every 1 sec
    try:
        while True:
            os.system('python ExposeOne.py')
            time.sleep(1)
    except KeyboardInterrupt:
        print('ended by keyboard interrupt')
