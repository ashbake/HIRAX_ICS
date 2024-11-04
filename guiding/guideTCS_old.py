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

import numpy as np
import matplotlib.pylab as plt
from PIL import Image
import glob,os
import pandas as pd
from scipy import signal

plt.ion()

######### FILL ME IN
datapath = '/Users/ashbake/Documents/Research/Projects/HIRAX/data/guider/' # put in permanent place
date     = '20220706/' # make fxn to figure this out
xref, yref= 0,0


######### {TEMP} FAKE IMAGE GENERATION
def twoD_Gaussian(x,y, amplitude, xo, yo, sigma_x, sigma_y, theta, offset):
	"""
	have to define x and y using meshgrid
	"""
	xo = float(xo)
	yo = float(yo)
	a = (np.cos(theta)**2)/(2*sigma_x**2) + (np.sin(theta)**2)/(2*sigma_y**2)
	b = -(np.sin(2*theta))/(4*sigma_x**2) + (np.sin(2*theta))/(4*sigma_y**2)
	c = (np.sin(theta)**2)/(2*sigma_x**2) + (np.cos(theta)**2)/(2*sigma_y**2)
	
	return offset + amplitude*np.exp( - (a*((x-xo)**2) + 2*b*(x-xo)*(y-yo) + c*((y-yo)**2)))

def make_fake_image(dx,dy):
	"""
	somethin to work with

	width: 2160
	length: 4096

	xcent and ycent define fake star position, must fall
	within width and length respectively
	"""
	# open data in right format
	im = Image.open('/Users/ashbake/Documents/Research/Projects/HIRAX/data/guider/20220609/focus_coarse_20mm.tiff')
	w,l = np.shape(im)
	amplitude = 150
	sigma_x, sigma_y = 25,35
	offset = 0 # background counts
	theta = 0.1
	xcent, ycent = l//2 + dx, w//2 + dy

	xtarr,ytarr = np.meshgrid(np.arange(l), np.arange(w)) # not sure why i have to flip these but i do

	fakegaus = im + twoD_Gaussian(xtarr, ytarr, amplitude, 
								xcent, ycent, sigma_x, sigma_y, theta, offset)

	return fakegaus.astype('uint8')

def save_fake_images(data,ind=0):
	"""
	save a handful of fake iamges to check as tiff
	can move these by hand into data folder to check code is working
	"""
	im = Image.fromarray(data)
	im.save('testdata_%04d.tiff'%ind)

def make_fake_data_sequence():
	"""
	"""
	inds = np.arange(10)
	for i in np.arange(len(inds)):
		dx, dy = (-0.5 + np.random.random(2)) * 100 # random number b/n -50 and 50
		data = make_fake_image(dx,dy)
		save_fake_images(data,ind=i)


######### if want a different source finder 

def minimizing_function(p, fluxdat, xtarr, ytarr, x_mean, y_mean):
    """
    Uses Gaussian2D (amplitude=1, x_mean=0, y_mean=0, x_stddev=None, y_stddev=None, theta=None, cov_matrix=None, **kwargs
    
    inputs:
    -------
    p: params (tuple; amplitude, x sigma, y sigma of 2D gaussian)
    fluxdat: data with flux for each npix by npix postage stamp for each frame of total nframes
    x_mean: solved for mean mask x position
    y_mean: solved for mean mask y position
    
    outputs:
    --------
    xi^2 of fit
    """
    nframes = len(x_mean)
    
    #Unpack coeffs
    amp, x_sig, y_sig, theta, offx, offy = p
    
    # define 2d gaussian
    xs, ys = np.arange(-5,5)-xt, np.arange(-5,5)-yt
    model = np.array([twoD_Gaussian(xtarr, ytarr, amp,\
                                    x_mean[i]+ offx,\
                                    y_mean[i]+offy, x_sig, y_sig, theta, 0) for i in np.arange(nframes)])

    # Minimization
    return np.sum(np.sum((model - fluxdat)**2)) # add photon noise as errors...


def find_centroid_gausfit(data):
	"""
	finish making this in case need a more complex routine to centroid

	"""
	# fit gaussian to data
	p_start = (np.max(fluxdat[0]), 0.4, 0.4, 0, 0,0) # amplitude (e-), xsig (pix), ysig (pix)

	out    = opt.minimize(minimizing_function,p_start,\
					args=(fluxdat, xtarr, ytarr, x_mean, y_mean),\
					method="SLSQP",options={'maxiter' : maxiter}) 
	return xpix,ypix


######## {MOVE} TOOLS


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
	
	mag: ratio of first lens to guide camera lens (150:100 or 150:75)
	pixel_size: pixel size in microns (3.45 for guider)
	"""
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


def offset_to_TCS(dx_arcs, dy_arcs):
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
	dx_tcs = -1 * dx_arcs
	dy_tcs = -1 * dy_arcs
	string = 'PT %s %s \r' %(dx_tcs, dy_tcs)

	with open('guide_to_TCS.txt','wb') as f:
		f.write(string.encode('ascii'))
	f.close()
	

def plot_summary():
	"""
	plot summary of image and shift
	mark x,y reference and summarize shift in title
	"""
	pass


def run(ind):
	"""
	"""
	#filelist = glob.glob(datapath + date + '*tiff')
	filelist = sorted(glob.glob(os.path.join(date,'*tiff')), key = lambda t: os.stat(t).st_mtime)
	filename = filelist[-1] # take file modified most recently
	subframe = 500
	data = load_image(filename,subframe=subframe)

	# fit centroid offset in arcsec
	xcent, ycent = find_centroid(data)
	dx, dy       = calc_offset(xcent,ycent,subframe,xref,yref) # *** note: x plots as y axis in python
	dx_arcs, dy_arcs = pixel_to_arcsec(dx,dy)	

	# send to TCS
	offset_to_TCS(dx_arcs, dy_arcs) #send this somewhere?

if __name__=='__main__':
	# start while loop to constantly check until loop is killed, pause 1 sec at end of each loop
	pass

		