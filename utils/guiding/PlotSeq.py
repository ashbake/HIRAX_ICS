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
# how sequence goes:
# 
#  - check for new file in guide folder
#  - if new file, open it
#  - process file through source finder
#  - calculate offset funciton
#  - convert offset to arcsec
#  - save result to TCS format?
####################

import numpy as np
import matplotlib.pylab as plt
from PIL import Image
import glob,os,time

plt.ion()

######### FILL ME IN
date     = '20250429' # make fxn to figure this out
datapath = '/Users/ashle/Documents/Data/%s/guiding/'%date # put in permanent place
xref, yref= 0,0 # position on detector where to move the star to. This may need to change for different zenith positions TBD
if not os.path.exists(datapath): os.makedirs(datapath)

def load_image(filename):#,subframe=500):
    """
    load filename (includes path)

    filename (str): 

    subframe (int): npixels of subframe box to take around center
    """

    f = np.array(Image.open(filename))
    #nx,ny = np.shape(f)
    #xcent,ycent = nx//2, ny//2
    #r = subframe//2

    return f#[xcent-r:xcent+r,ycent-r:ycent+r]



def plot_summary(data,title):
    """
    plot summary of image and shift
    mark x,y reference and summarize shift in title
    """
    plt.figure(-99)
    plt.clf()
    plt.imshow(data)
    plt.title(title)

def run_camonly():
    """
    """
    filelist = sorted(glob.glob(os.path.join(datapath,'*tiff')))
    #filelist = sorted(glob.glob(os.path.join(date,'*tiff')), key = lambda t: os.stat(t).st_mtime)
    filename = filelist[-1] # take file modified most recently
    plt.pause(.1)
    data = load_image(filename)

    plot_summary(data,title=filename.split('\\')[-1])

if __name__=='__main__':
    # Setup Telnet Connection
    while True:
        run_camonly()
        #plt.pause(0.1)
        
