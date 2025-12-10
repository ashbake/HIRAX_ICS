from datetime import datetime
import logging, os
from pathlib import Path
import numpy as np
from astropy.io import fits

import PySpin

from cLogging import setup_logging
import logging, yaml

os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

config_file = str(Path.cwd().resolve().parent / "config" / "guider.yaml")


class cGuider:
    def __init__(self, night, source, config_file=config_file):
        # Define attributes
        # read from config file, loads default config_file
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)

        self.source    = source # feed it a source string for the header
        self.night     = night # YYYYMMDD
        self.name      = self.config['name'] # should be H4Rpro
        self.file_format  = self.config['file_format']

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
        self.system = PySpin.System.GetInstance()

        # Get current library version
        version = self.system.GetLibraryVersion()
        print('Library version: %d.%d.%d.%d' % (version.major, version.minor, version.type, version.build))

        # Retrieve list of cameras from the system
        self.cam_list = self.system.GetCameras()
        num_cameras = self.cam_list.GetSize()
        self.logger.info('Number of cameras detected: %d' % num_cameras)

        if num_cameras == 0:
            # Clear camera list before releasing system
            self.cam_list.Clear()

            # Release system instance
            self.system.ReleaseInstance()

            self.logger.error('Not enough cameras! Exiting')
            return False
        
        self.cam = self.cam_list[0] # we just have one Flir camera so try taking 0th index

        try:
            # Initialize camera
            self.cam.Init()

            # Print device info
            self.device_info = self._get_device_info()

        except PySpin.SpinnakerException as ex:
                print('Error: %s' % ex)
                return False

    def disconnect(self):
        # Deinitialize camera
        self.cam.DeInit()

        del self.cam

        # Clear camera list before releasing system
        self.cam_list.Clear()

        # Release system instance
        self.system.ReleaseInstance()

    def expose(self,exposure_time):
        if not self._configure_exposure(exposure_time):
            return False

        # Acquire images
        if not self.acquire_images(): self.logger.warning('FLIR guider image acquisition Failed.')

        # Reset exposure
        self._reset_exposure()

    def _get_device_info(self):
        """
        This function prints the device information of the camera from the transport
        layer; please see NodeMapInfo example for more in-depth comments on printing
        device information from the nodemap.

        :param cam: Camera to get device information from.
        :type cam: CameraPtr
        :return: True if successful, False otherwise.
        :rtype: bool

        Should print out:
        DeviceID: 2CDDA350840A_0AC89101_FFFF0000_0AC80181
        DeviceSerialNumber: 22053898
        DeviceVendorName: FLIR
        DeviceModelName: Blackfly S BFS-PGE-88S6M
        DeviceType: GigEVision
        DeviceDisplayName: FLIR Blackfly S BFS-PGE-88S6M
        DeviceAccessStatus: OpenReadWrite
        DeviceVersion: 2103.0.343.0
        DeviceUserID:
        DeviceDriverVersion: PgrLwf.sys : 2.7.3.507
        DeviceIsUpdater: 0
        GevCCP: ControlAccess
        GUIXMLLocation: Device
        GUIXMLPath: Input.xml
        GenICamXMLLocation: Device
        GenICamXMLPath:
        GevDeviceIPAddress: 0xac89101
        GevDeviceSubnetMask: 0xffff0000
        GevDeviceMACAddress: 0x2cdda350840a
        GevDeviceGateway: 0xac80181
        DeviceLinkSpeed: 1000
        GevVersionMajor: 1
        GevVersionMinor: 2
        GevDeviceModeIsBigEndian: 1
        GevDeviceReadAndWriteTimeout: 100000
        GevDeviceMaximumRetryCount: 3
        GevDevicePort: 29200
        GevDeviceDiscoverMaximumPacketSize: Node not readable
        GevDeviceMaximumPacketSize: 1500
        GevDeviceIsWrongSubnet: 0
        GevDeviceAutoForceIP: 0
        GevDeviceForceIP: 0
        GevDeviceForceIPAddress: 0xac89101
        GevDeviceForceSubnetMask: 0xffff0000
        GevDeviceForceGateway: 0xac80181
        """

        print('*** DEVICE INFORMATION ***\n')

        try:
            nodemap = self.cam.GetTLDeviceNodeMap()

            node_device_information = PySpin.CCategoryPtr(nodemap.GetNode('DeviceInformation'))
            save_info = {}
            if PySpin.IsAvailable(node_device_information) and PySpin.IsReadable(node_device_information):
                features = node_device_information.GetFeatures()
                for feature in features:
                    node_feature = PySpin.CValuePtr(feature)
                    if print:
                        print('%s: %s' % (node_feature.GetName(),
                                        node_feature.ToString() if PySpin.IsReadable(node_feature) else 'Node not readable'))
                    save_info[node_feature.GetName()] = (node_feature.ToString() 
                                                         if PySpin.IsReadable(node_feature) 
                                                         else 'Node not readable')
            else:
                print('Device control information not available.')

        except PySpin.SpinnakerException as ex:
            print('Error: %s' % ex.message)
            return False

        return save_info
    
    def _configure_exposure(self,exposure_time):
        """
        This function configures a custom exposure time. Automatic exposure is turned
        off in order to allow for the customization, and then the custom setting is
        applied.

        :param cam: Camera to configure exposure for.
        :type cam: CameraPtr
        :return: True if successful, False otherwise.
        :rtype: bool
        """

        print('*** CONFIGURING EXPOSURE ***\n')

        try:
            result = True

            # Turn off automatic exposure mode
            #
            # *** NOTES ***
            # Automatic exposure prevents the manual configuration of exposure
            # times and needs to be turned off for this example. Enumerations
            # representing entry nodes have been added to QuickSpin. This allows
            # for the much easier setting of enumeration nodes to new values.
            #
            # The naming convention of QuickSpin enums is the name of the
            # enumeration node followed by an underscore and the symbolic of
            # the entry node. Selecting "Off" on the "ExposureAuto" node is
            # thus named "ExposureAuto_Off".
            #
            # *** LATER ***
            # Exposure time can be set automatically or manually as needed. This
            # example turns automatic exposure off to set it manually and back
            # on to return the camera to its default state.

            if self.cam.ExposureAuto.GetAccessMode() != PySpin.RW:
                self.logger.error('Unable to disable automatic exposure. Aborting...')
                return False

            self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)

            # Set exposure time manually; exposure time recorded in microseconds
            #
            # *** NOTES ***
            # Notice that the node is checked for availability and writability
            # prior to the setting of the node. In QuickSpin, availability and
            # writability are ensured by checking the access mode.
            #
            # Further, it is ensured that the desired exposure time does not exceed
            # the maximum. Exposure time is counted in microseconds - this can be
            # found out either by retrieving the unit with the GetUnit() method or
            # by checking SpinView.

            if self.cam.ExposureTime.GetAccessMode() != PySpin.RW:
                print('Unable to set exposure time. Aborting...')
                return False

            # Ensure desired exposure time does not exceed the maximum
            if exposure_time > self.cam.ExposureTime.GetMax():
                self.logger.warning('Exposure time is greater than the maximum allowed. Capping to Max.')
            exposure_time_to_set = min(self.cam.ExposureTime.GetMax(), exposure_time)
            self.cam.ExposureTime.SetValue(exposure_time_to_set)
            self.logger.info('Guider Shutter time set to %s us...\n' % exposure_time_to_set)

        except PySpin.SpinnakerException as ex:
            print('Error: %s' % ex)
            result = False

        return result

    def _reset_exposure(self):
        """
        This function returns the camera to a normal state by re-enabling automatic exposure.

        :param cam: Camera to reset exposure on.
        :type cam: CameraPtr
        :return: True if successful, False otherwise.
        :rtype: bool
        """
        try:
            result = True

            # Turn automatic exposure back on
            #
            # *** NOTES ***
            # Automatic exposure is turned on in order to return the camera to its
            # default state.

            if self.cam.ExposureAuto.GetAccessMode() != PySpin.RW:
                print('Unable to enable automatic exposure (node retrieval). Non-fatal error...')
                return False

            self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Continuous)

            print('Automatic exposure enabled...')

        except PySpin.SpinnakerException as ex:
            print('Error: %s' % ex)
            result = False

        return result

    def acquire_images(self):
        """
        This function acquires and saves images from a device; please see
        Acquisition example for more in-depth comments on the acquisition of images.

        :param cam: Camera to acquire images from.
        :type cam: CameraPtr
        :return: True if successful, False otherwise.
        :rtype: bool
        """
        print('*** IMAGE ACQUISITION ***')

        try:
            result = True

            # Set acquisition mode to continuous
            if self.cam.AcquisitionMode.GetAccessMode() != PySpin.RW:
                print('Unable to set acquisition mode to continuous. Aborting...')
                return False

            self.cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)
            print('Acquisition mode set to continuous...')

            # Begin acquiring images
            self.cam.BeginAcquisition()

            print('Acquiring images...')

            # Get device serial number for filename
            device_serial_number = ''
            if self.cam.TLDevice.DeviceSerialNumber is not None and self.cam.TLDevice.DeviceSerialNumber.GetAccessMode() == PySpin.RO:
                device_serial_number = self.cam.TLDevice.DeviceSerialNumber.GetValue()

                print('Device serial number retrieved as %s...' % device_serial_number)

            # Get the value of exposure time to set an appropriate timeout for GetNextImage
            timeout = 0
            if self.cam.ExposureTime.GetAccessMode() == PySpin.RW or self.cam.ExposureTime.GetAccessMode() == PySpin.RO:
                # The exposure time is retrieved in µs so it needs to be converted to ms to keep consistency with the unit being used in GetNextImage
                timeout = (int)(self.cam.ExposureTime.GetValue() / 1000 + 1000)
            else:
                print ('Unable to get exposure time. Aborting...')
                return False

            # Retrieve, convert, and save images
            try:
                # Retrieve next received image and ensure image completion
                # By default, GetNextImage will block indefinitely until an image arrives.
                # In this example, the timeout value is set to [exposure time + 1000]ms to ensure that an image has enough time to arrive under normal conditions
                image_result = self.cam.GetNextImage(timeout)
                self.last_time_tag = datetime.utcnow().strftime("%Y-%m-%dT%H.%M.%S.%f")

                if image_result.IsIncomplete():
                    print('Image incomplete with image status %d...' % image_result.GetImageStatus())

                else:
                    # Print image information
                    width = image_result.GetWidth()
                    height = image_result.GetHeight()
                    print('Grabbed Image width = %d, height = %d' % (width, height))

                    # Convert image to Mono8
                    self.image_converted = image_result.Convert(PySpin.PixelFormat_Mono8)
                    self.writeToFile()

                # Release image
                image_result.Release()

            except PySpin.SpinnakerException as ex:
                print('Error: %s' % ex)
                result = False

            # End acquisition
            self.cam.EndAcquisition()

        except PySpin.SpinnakerException as ex:
            print('Error: %s' % ex)
            result = False

        return result
    
    def writeToFile(self):
        """uses pyspin functionalities to save as tiff"""
        if self.file_format=='TIFF':
            # Create a unique filename
            filename = str(self.data_dir / f"guide_{self.source}_{self.last_time_tag}.tiff")

            # Save image
            self.image_converted.Save(filename)

            print('Image saved at %s' % filename)
        elif self.file_format=='FITS':
            """accesses data in local memory to save to fits"""
            raw_data = self.image_converted.GetData().astype(np.uint16)
            self.raw_data = raw_data.reshape(2160, 4096)

            filename = str(self.data_dir / f"guide_{self.source}_{self.last_time_tag}.fits")
            hdu = fits.PrimaryHDU(self.raw_data)

            for key, value in self.device_info.items():
                hdu.header[key] = value
            hdu.header['GTIME'] = self.last_time_tag

            hdu.writeto(filename)
        else:
            self.logger.error('File format in yaml file should be FITS or TIFF')


if __name__=='__main__':
    night = '20251209'
    source = 'dark'
    test = cGuider(night, source)

    test.connect()
    exp_time =  .01 * 1e6
    test.expose(exp_time) # 50 microseconds
    test.expose(2*exp_time) # 50 microseconds
    test.disconnect()