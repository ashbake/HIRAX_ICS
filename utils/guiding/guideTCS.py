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
import pandas as pd
from scipy import signal
import telnetlib # for communicating to TCS via telnet

plt.ion()

######### FILL ME IN
date     = '20220706' # make fxn to figure this out
datapath = '/Users/ashle/Documents/Data/%s/guiding/'%date # put in permanent place
xref, yref= 0,0 # position on detector where to move the star to. This may need to change for different zenith positions TBD

def load_image(filename,subframe=500):
    """
    load filename (includes path)

    filename (str): 

    subframe (int): npixels of subframe box to take around center
    """

    f = np.array(Image.open(filename))
    nx,ny = np.shape(f)
    xcent,ycent = nx//2, ny//2
    r = subframe//2

    return f[xcent-r:xcent+r,ycent-r:ycent+r]

def find_centroid(data):
    """
    Input: loaded data, Output: x,y center of aperture

    **assumes no other source in frame (or at least that source of interest is the brightest!!)***
    """
    # Convolve image with gaussian kernel
    kernel = np.outer(signal.gaussian(70,8), signal.gaussian(70,8))
    blurred = signal.fftconvolve(data, kernel, mode='same')

    # Take the normalized STD along x,y axes
    xstd = np.std(blurred,axis=0)
    ystd = np.std(blurred,axis=1)
    xstdn = (xstd - np.median(xstd[100:300]))/max(xstd)
    ystdn = (ystd - np.median(ystd[100:300]))/max(ystd)

    # Determine center by maximum. Eventually add check that there's only one source!
    try: x,y = np.where(xstdn == max(xstdn))[0][0], np.where(ystdn == max(ystdn))[0][0]
    except IndexError:
        x,y = 0,0

    return x,y


def calc_offset(xcent,ycent,subframe,xref=0,yref=0):
    """
    xref and yref are defined based on center of image (w//2, l//2)
    so use subframe to know this

    xref and yref default to 0 (reference is the center!)
    """
    return xcent - xref - subframe//2, ycent - yref - subframe//2


def calc_plate_scale(mag=1.5,pixel_size=3.45):
    """
    use focal lengths to calculate rough plate scale at guider
    mag: ratio of first lens to guide camera lens (150:100 or 150:80)
    pixel_size: pixel size in microns (3.45 for guider)
    """
    mag = 150/80 # 150 is focal dist of guide lens, 80 mm is collimator
    # accidentally had 100 has focal distance of first lens
    F_pf = 16.76*10**3 # mm , Focal length Hale telescope
    ps_pf = 206265 / (16.76*10**3) # arcsec/mm  at prime focus
    ps_final = ps_pf / mag

    pixel_size_mm = pixel_size / 1000
    ps_final_pixel = ps_final * pixel_size_mm

    return ps_final_pixel # arcsec/pixel


def pixel_to_arcsec(dx,dy):
    """
    convert pixel shift to arseconds using plate scale
    """
    plate_scale = calc_plate_scale(mag=1.5) # arsec/pixel
    return dx * plate_scale, dy * plate_scale


def offset_to_TCS(session, dx_arcs, dy_arcs):
    """
    send offset to TCS???
    save ascii strign with command according to P200_tcs_remote_cmds.txt

    PT (two arguments):  move telescope in RA and dec simultaneously by
    distance given in first and second arguments, respectively.  Distances are
    in arcseconds.  Positive values move east and north.  Rates of moves are
    set by MRATES - see above.  Moves are precessed to the display equinox.
    Valid range: -6000 to 6000 arcsec in each axis.

    i think that (x) down (in default python plot of guide image) is down so positive 
    dx is west and positive dy is south --> flip signs. x and y are good

    test this ultimately bc not sure if "positive values move east and north" means
    the stars or the telescope. probs the telescope wich would make sign flight correct
    """
    EW_tcs = dy_arcs      # (up/down on guide image, short axis)
    NS_tcs = -1 * dx_arcs # (left/right on guide image, long axis)
    cmd = 'PT %s %s \r' %(EW_tcs, NS_tcs)

    out = session.write(cmd.encode('ascii'))
    return out

def plot_summary(data,xcent,ycent,dx,dy,dx_arcs,dy_arcs):
    """
    plot summary of image and shift
    mark x,y reference and summarize shift in title
    """
    plt.figure(-99)
    plt.clf()
    plt.imshow(data)
    plt.scatter(xcent,ycent,marker='x',c='r')
    plt.title('EW: %s NS: %s' %(round(dy_arcs,2), round(-1*dx_arcs,2)))
    plt.arrow(xcent,ycent,-1*dx,-1*dy,length_includes_head=True,head_width=10)
    plt.pause(0.1)


def run(session):
    """
    """
    filelist = sorted(glob.glob(os.path.join(datapath,date,'*tiff')), key = lambda t: os.stat(t).st_mtime)
    #filelist = sorted(glob.glob(os.path.join(date,'*tiff')), key = lambda t: os.stat(t).st_mtime)
    filename = filelist[-1] # take file modified most recently
    subframe = 1500
    data = load_image(filename,subframe=subframe)

    # fit centroid offset in arcsec
    xcent, ycent = find_centroid(data)
    dx, dy       = calc_offset(xcent,ycent,subframe,xref,yref) # *** note: x plots as y axis in python
    dx_arcs, dy_arcs = pixel_to_arcsec(dx,dy) 

    # send to TCS if less than 10 arcsec
    #if np.abs(dx_arcs) < 10 and np.abs(dx_arcs) < 10: 
    #    offset_to_TCS(session, dx_arcs, dy_arcs) #send this somewhere?

    plot_summary(data,xcent,ycent,dx,dy,dx_arcs,dy_arcs)

    return dx_arcs, dy_arcs # save these!

if __name__=='__main__':
    # Setup Telnet Connection
    HOST_IP = 10.200.99.2
    PORT = 49200
    TIMEOUT = 100
    
    session  = telnetlib.Telnet(HOST_IP,PORT,TIMEOUT)

    savedSet = set()
    try:
        while True:
            retrievedSet  = set()
            for file in os.listdir(os.path.join(datapath,date)):
                fullpath = os.path.join(datapath,date,file)
                stat = os.stat(fullpath)
                time = stat.st_ctime
                size = stat.st_size
                tmod = stat.st_mtime
                retrievedSet.add((fullpath,time))

            newSet = retrievedSet - savedSet
            if len(newSet) > 0:
                run(session) # run takes last file based on creation time, do i have to consider if file isn't done being made yet? could just pause a ms
            savedSet = retrievedSet
            plt.pause(0.1)
            print(savedSet)
    except KeyboardInterrupt:
        session.close()
    

    # start while loop to constantly check until loop is killed, pause 0.1 sec at end of each loop
    # notes: i take last file on creation from glob of full guide data
    # path - should change to just use the popped file from newSet
    # worried tho that there will be multiple new files
    # so should add some exception or take most recent from those files
    # this may work for now tho since new files from guider will
    # always be the most recently created and modified

    # change this to close loop in future - control image acquisition here and take second image to check result?