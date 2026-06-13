from datetime import datetime,timezone
import numpy as np
import sys
from pathlib import Path
#import telnetlib
import socket
from scipy import signal
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve() ))
from cFLIR import cFLIR


class cGuider(cFLIR):
    def __init__(self,night):
        super().__init__(night) # do this to get logger and config

        self.logger.info('Trying to connect to TCS')
        self.centroid_method = 'std'  # 'std' (marginal std) or 'com' (center of mass)

    def connect(self):
        """connect to TCS via TCP socket"""
        self.session = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.config['TIMEOUT'])
            sock.connect((self.config['HOST_IP'], self.config['PORT']))
            self.session = sock
            self.logger.info(f"Connected to TCS at {self.config['HOST_IP']}:{self.config['PORT']}")
        except Exception as e:
            self.logger.error(f"Couldn't connect to TCS at {self.config['HOST_IP']}:{self.config['PORT']}: {e}")

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

    def _find_centroid(self, data):
        """Dispatch to the selected centroid algorithm (set via self.centroid_method)."""
        if self.centroid_method == 'com':
            return self._find_centroid_com(data)
        return self._find_centroid_std(data)

    def _find_centroid_std(self, data):
        """
        Marginal standard-deviation centroid.
        Blurs the image then finds the column/row with the highest variance.
        Robust to noise but assumes one dominant source and image size >= 300 px.
        """
        kernel = np.outer(signal.windows.gaussian(70, 8), signal.windows.gaussian(70, 8))
        blurred = signal.fftconvolve(data, kernel, mode='same')

        xstd = np.std(blurred, axis=0)
        ystd = np.std(blurred, axis=1)

        # Subtract background estimated from a central strip, normalise
        bg_cols = min(100, len(xstd) // 4)
        bg_rows = min(100, len(ystd) // 4)
        xstdn = (xstd - np.median(xstd[bg_cols : bg_cols * 3])) / max(xstd)
        ystdn = (ystd - np.median(ystd[bg_rows : bg_rows * 3])) / max(ystd)

        try:
            x = np.where(xstdn == max(xstdn))[0][0]
            y = np.where(ystdn == max(ystdn))[0][0]
        except IndexError:
            x, y = data.shape[1] // 2, data.shape[0] // 2

        return x, y

    def _find_centroid_com(self, data):
        """
        Center-of-mass centroid.
        Subtracts a background (median) then computes flux-weighted mean position.
        More accurate than marginal-std for isolated point sources; sensitive to
        background subtraction quality if multiple sources are present.
        """
        background = np.median(data)
        d = np.maximum(data.astype(float) - background, 0)
        total = np.sum(d)

        if total == 0:
            return data.shape[1] // 2, data.shape[0] // 2

        rows, cols = np.indices(data.shape)
        x = int(round(np.sum(cols * d) / total))
        y = int(round(np.sum(rows * d) / total))
        return x, y

    def _calc_offset(self,xcentroid,ycentroid,Nx, Ny,xref=0,yref=0):
        """
        computes the offset

        inputs:
        -------
        xcentroid - float
            centroid of the PSF in x position
        ycentroid - float
            centroid of the PSF in y position
        Nx  = int
            size of subframe in x axis
        Ny - int
            size of subframe in y axis
        xref - float (default 0)
            target position w.r.t. center of frame x axis
        yref - float (default 0)
            target position w.r.t. center of frame y axis

        returns
        -------
        x and y offsets to apply            
        
        xref and yref are defined based on center of image (Nx//2, Ny//2)
        so use subframe to know this

        xref and yref default to 0 (reference is the center!)
        """
        return xcentroid - xref - Nx//2, ycentroid - yref - Ny//2

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

    def _send_command(self, cmd, bufsize=4096):
        """Send a command string over the socket and return the response."""
        if self.session is None:
            raise ConnectionError("TCS socket is not connected")
        self.session.sendall(cmd.encode('ascii'))
        return self.session.recv(bufsize).decode('ascii')

    def expose(self, exposure_time, header_keys={}, source="", writeToFile=True, subframe=None):
        """Wrap cFLIR.expose to inject TCS telemetry into the FITS header."""
        merged = dict(header_keys)
        try:
            merged.update(self.get_telemetry())
        except Exception as e:
            self.logger.warning(f"Could not fetch TCS telemetry for header: {e}")
        super().expose(exposure_time, header_keys=merged, source=source,
                       writeToFile=writeToFile, subframe=subframe)

    def disconnect(self):
        """disconnect socket"""
        try:
            self.session.close()
            self.logger.info('Closed socket connection')
        except:
            self.logger.warning("Couldn't close socket connection")
        
        # disconnect camera
        #super().disconnect()

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
        cmd = 'PT %s %s\n' %(EW_tcs, NS_tcs)

        out = self._send_command(cmd)
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

    def run(self,data,subframe=None,ploton=False):
        """
        run centroid finder and push offset to telescope
        inputs:
        -------
        data - guide camera image
        """
        # data comes from memory now, but can edit this later to load file if data is string(filename)
        #data = load_image(filename,subframe=subframe)

        # apply subframe
        if subframe is not None:
            x0,xf,y0,yf = subframe
            self.subdata = data[x0:xf, y0:yf]
        else:
            self.subdata = data

        Nx,Ny = np.shape(self.subdata)

        # compute reference offset from center to aim for ( for now 0,0 but can add function for DAR for example)
        self.xref,self.yref = 0,0
        
        # fit centroid offset in arcsec
        xcentroid, ycentroid = self._find_centroid(self.subdata)
        dx, dy               = self._calc_offset(xcentroid,ycentroid, Nx, Ny,self.xref,self.yref) # *** note: x plots as y axis in python
        self.dx_arcs, self.dy_arcs     = self._pixel_to_arcsec(dx,dy) 

        # send to TCS if less than 10 arcsec
        if np.abs(self.dx_arcs) < 10 and np.abs(self.dx_arcs) < 10: 
            self.offset_to_TCS(np.round(self.dx_arcs,2), np.round(self.dy_arcs,2)) #send this somewhere?

        if ploton: self.plot_summary(self.subdata,Nx//2,Ny//2,dx,dy,dx_arcs,dy_arcs)

    def get_telemetry(self):
        """
        Get telemetry from telnet connection to telescope
        
        saves telemetry values to dictionary that feeds expose() command to save to FITS header

        REQPOS = "UTC = ddd hh:mm:ss.s, LST = hh:mm:ss.s\nRA = hh:mm:ss.ss, DEC = [+/-]dd:mm:ss.s, HA = [W/E]hh:mm:ss.s\nair mass = aa.aaa"

        """
        self.header_keys = {}

        # --- REQPOS ---
        REQPOS = self._send_command('REQPOS\r')
        self.logger.debug(f"REQPOS raw: {REQPOS!r}")
        utclst, radecha, airmass = REQPOS.split('\n')
        utc, lst = utclst.split(',')
        ra, dec, ha = radecha.split(',')
        self.header_keys['UTC']     = utc.strip('UTC =')
        self.header_keys['LST']     = lst.strip(' LST =')
        self.header_keys['RA']      = ra.strip('RA =')
        self.header_keys['DEC']     = dec.strip('DEC =')
        self.header_keys['HA']      = ha.strip(' HA =')
        self.header_keys['AIRMASS'] = airmass.strip('air mas=').strip('\x00')

        # --- NAME ---
        NAME = self._send_command('NAME\r')
        self.logger.debug(f"NAME raw: {NAME!r}")
        self.header_keys['OBJECT'] = NAME.strip('\n').strip('NAME =')

        # --- REQSTAT ---
        # Response format:
        #   UTC = ddd hh:mm:ss.s
        #   telescope ID = NNN, focus = FF.FF mm, tube length = TT.TT mm
        #   offset RA =   R.R arcsec, DEC =   D.D arcsec
        #   rate RA =   R.R arcsec/hr, DEC =   D.D arcsec/hr
        #   Cass ring angle = CCC.CC\x00
        REQSTAT = self._send_command('REQSTAT\r')
        self.logger.debug(f"REQSTAT raw: {REQSTAT!r}")
        stat_lines = REQSTAT.split('\n')
        tel_id_str, focus_str, tubelen_str = stat_lines[1].split(',')
        off_ra_str,  off_dec_str  = stat_lines[2].split(',')
        rate_ra_str, rate_dec_str = stat_lines[3].split(',')
        self.header_keys['TELID']    = tel_id_str.split('=')[1].strip()
        self.header_keys['FOCUS']    = focus_str.split('=')[1].strip().split()[0]
        self.header_keys['TUBELEN']  = tubelen_str.split('=')[1].strip().split()[0]
        self.header_keys['RAOFFSET'] = off_ra_str.split('=')[1].strip().split()[0]
        self.header_keys['DECOFFST'] = off_dec_str.split('=')[1].strip().split()[0]
        self.header_keys['RARATE']   = rate_ra_str.split('=')[1].strip().split()[0]
        self.header_keys['DECRATE']  = rate_dec_str.split('=')[1].strip().split()[0]
        self.header_keys['CASSANG']  = stat_lines[4].split('=')[1].strip().strip('\x00')

        return self.header_keys
    

def main():
    """example run"""
    night = datetime.now(timezone.utc).strftime("%Y%m%d")
    test = cGuider(night)
    
    camera = cFLIR(night)
    camera.connect()
    camera.expose(1e5,writeToFile=False)

    test.run(camera.raw_data)
    test.disconnect()


    
if __name__=='__main__':
    main()
    