# runs guider and saves telemetry
# input arguments:
# 1 source is string for name of target
# 2 exp_time is exposure time in settings
# 3 interval (optional) time between exposures


import time, sys, argparse, telnetlib
import numpy as np

from pathlib import Path
from datetime import datetime, timezone
from scipy import signal
from PIL import Image

sys.path.insert(0, str(Path.cwd().resolve().parent / "utils" ))
from cGuider import cGuider

# Parse User Inputs
parser = argparse.ArgumentParser()
parser.add_argument('source', help='Target Name[str]')
parser.add_argument('exp_time', help='Exposure Time in seconds [float]')
parser.add_argument('--interval', type=float, default=0,
                    help='Time between captures')
args = parser.parse_args()

# Determine night string for logging and folder creation
night = datetime.now(timezone.utc).strftime("%Y%m%d")


class Guiding(cGuider):
    def __init__(self,night, source):
        super().__init__(night, source) # do this to get logger and config 

        self.session  = telnetlib.Telnet(self.config['HOST_IP'],self.config['PORT'],self.config['TIMEOUT'])

        self.ref_x = self.config['ref_x'] # eventually this reference can change with differential atmospheric dispersion
        self.ref_y = self.config['ref_y']

        self.subframe = self.config['subframe']

        # telemetry file TODO 
        #self.telemtry_path =  Path(self.config['data_dir']) / self.night / 'telemetry'
        # self.telemetry_file = str(self.telemetry_path / f"guide_{self.source}_{self.last_time_tag}.txt")

    def _load_image(self,filename,subframe=500):
        """
        load filename (includes path) (if not using image from memory)

        filename (str): 

        subframe (int): npixels of subframe box to take around center
        """

        f = np.array(Image.open(filename))
        nx,ny = np.shape(f)
        xcent,ycent = nx//2, ny//2
        r = subframe//2

        return f[xcent-r:xcent+r,ycent-r:ycent+r]

    def _find_centroid(self,data):
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

    def _calc_offset(self,xcent,ycent,subframe,xref=0,yref=0):
        """
        xref and yref are defined based on center of image (w//2, l//2)
        so use subframe to know this

        xref and yref default to 0 (reference is the center!)
        """
        return xcent - xref - subframe//2, ycent - yref - subframe//2

    def _calc_plate_scale(self,mag=1.5,pixel_size=3.45):
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

    def _pixel_to_arcsec(self,dx,dy):
        """
        convert pixel shift to arseconds using plate scale
        """
        plate_scale = self._calc_plate_scale(mag=1.5) # arsec/pixel
        return dx * plate_scale, dy * plate_scale

    def disconnect(self):
        self.logger.info('Closing telnet connection')
        self.session.close()

    def offset_to_TCS(self, dx_arcs, dy_arcs):
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

        out = self.session.write(cmd.encode('ascii'))
        self.logger.info(f'Moved telescope by {EW_tcs} EW and {NS_tcs} NS')
        return out

    def plot_summary(self,data,xcent,ycent,dx,dy,dx_arcs,dy_arcs):
        """
        plot summary of image and shift
        mark x,y reference and summarize shift in title
        """
        import matplotlib.pylab as plt

        plt.figure(-99)
        plt.clf()
        plt.imshow(data)
        plt.scatter(xcent,ycent,marker='x',c='r')
        plt.title('EW: %s NS: %s' %(round(dy_arcs,2), round(-1*dx_arcs,2)))
        plt.arrow(xcent,ycent,-1*dx,-1*dy,length_includes_head=True,head_width=10)
        plt.pause(0.1)

    def run(self,data,ploton=False):
        """
        run centroid finder and push offset to telescope
        inputs:
        -------
        data - 
        """
        # data comes from memory now, but can edit this later to load file if data is string(filename)
        #data = load_image(filename,subframe=subframe)

        # apply subframe
        nx,ny = np.shape(data)
        xcent,ycent = nx//2, ny//2
        r = self.subframe//2
        subdata = data[xcent-r:xcent+r,ycent-r:ycent+r]
        
        # fit centroid offset in arcsec
        xcent, ycent = self._find_centroid(subdata)
        dx, dy       = self._calc_offset(xcent,ycent,self.subframe,self.xref,self.yref) # *** note: x plots as y axis in python
        dx_arcs, dy_arcs = self._pixel_to_arcsec(dx,dy) 

        # send to TCS if less than 10 arcsec
        if np.abs(dx_arcs) < 10 and np.abs(dx_arcs) < 10: 
            self.offset_to_TCS(dx_arcs, dy_arcs) #send this somewhere?

        if ploton: self.plot_summary(data,xcent,ycent,dx,dy,dx_arcs,dy_arcs)

    def get_telemetry(self):
        """
        Get telemetry from telnet connection to telescope
        
        saves telemetry values to dictionary that feeds expose() command to save to FITS header

        REQPOS = "UTC = ddd hh:mm:ss.s, LST = hh:mm:ss.s\nRA = hh:mm:ss.ss, DEC = [+/-]dd:mm:ss.s, HA = [W/E]hh:mm:ss.s\nair mass = aa.aaa"

        """
        self.header_keys = {}
        REQPOS = self.session.write('REQPOS'.encode('ascii'))
        NAME   = self.session.write('NAME'.encode('ascii'))

        # format
        utclst, radecha, airmass = REQPOS.split('\n')
        utc, lst = utclst.split(',')
        ra, dec, ha  = radecha.split(',')

        # save
        self.header_keys['name'] = NAME.strip('\n').strip('NAME =') # TODO check all this works with real TCS output
        self.header_keys['UTC'] = utc.strip('UTC =')
        self.header_keys['LST'] = lst.strip(' LST =')
        self.header_keys['RA']  = ra.strip('RA =')
        self.header_keys['DEC'] = dec.strip('DEC =')
        self.header_keys['HA']  = ha.strip(' HA =')
        self.header_keys['airmass']  = ra.strip('airmass =')

        return self.header_keys

def main():
    # setup
    camera = cGuider(night, args.source)
    exp_time =  float(args.exp_time) * 1e6
    guiding  =  Guiding(night, args.source)

    try:
        # connect camera
        success = camera.connect()
        frame_num = 0
        
        if success: 
            while True:
                # Step 1 Capture image
                header_keys = guiding.get_telemtry()
                camera.expose(exp_time, header_keys) # takes microseconds, header keys goes into fits header
                
                # Step 2: Calculation and Push Offset to telescope
                guiding.run(camera.raw_data)

                # Step 4: Pause by user amount
                time.sleep(args.interval)

                # Iterate frame number and repeat loop
                frame_num += 1
                print(f"Captured frame {frame_num}", end='\r')  
        else:
            print('No Camera Detected') 
    except KeyboardInterrupt:
        print(f"\n\nStopped after {frame_num} frames")
        
    except Exception as e:
        print(f"\n\nError: {e}")
        
    finally:
        # Always cleanup
        print("Disconnecting camera...")
        camera.disconnect()
        guiding.disconnect()
        print(f"Session complete. {frame_num} frames saved to {camera.data_dir}")

if __name__ == "__main__":
    main()

