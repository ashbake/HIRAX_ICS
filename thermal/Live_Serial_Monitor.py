import serial
import time
import os
from astropy.time import Time

import matplotlib.pylab as plt
import numpy as np
plt.style.use('ggplot')
# Readout from the Arduino's serial monitor and write to a CSV file. Make sure Arduino IDE serial monitor is closed first
# Can stop the readout at any time by pressing 'Ctrl + C'

# Upgrades desired
# - filter files into date folders for some organization since there are lots of plots now
# - arduino code - average data by 5 seconds before feeding to PID loop

def WriteToFile(filePath,data):
    """
    write data to file, if file exists it will append

    inputs
    ------
    filePath - str
        path and filename to save to
    data - str
        data to write, should contain line break and delimiters already
    """
    file = None
    if not (os.path.isfile(filePath)):
        file = open(filePath, 'w')
        hdr = '#elapsed_time, in1, in2, in3, power1, power2, power3, temp1a, temp1b, temp2a, temp2b,\
                temp3a, temp3b, temp5, temp8, temp9, temp10\n'
        file.write(hdr)
    else:
        file = open(filePath, 'a')
    
    file.write(data)

    file.close()

def ProcessData(rawdata, alldata={}):
    """
    function to append rawdata to alldata dictionary
    check 'Triple_PID_Temp_Control' Arduino file for serial print out order

    inputs:
    -------
    data - 'str'
        raw data from serial read out
    
    outputs
    -------
    labeled in cats
    """
    lines = rawdata.split(',')

    label_order =['elapsed_time',
                  'input1','input2','input3',
                  'pct_power1','pct_power2','pct_power3',
                  'temp1a','temp1b',
                  'temp2a','temp2b',
                  'temp3a','temp3b',
                  'temp5','temp8','temp9','temp10']
    if len(lines) - 1 != len(label_order): raise ValueError('lines length and labels dont match!')
    
    # if data is none, initialize
    if len(alldata.keys())==0:
        alldata = {}
        for i, label in enumerate(label_order): alldata[label] = [float(lines[i])]
    else:
        for i, label in enumerate(label_order): alldata[label].append(float(lines[i]))
    
    return alldata

def ShowData(alldata):
    """
    Plot data
    """
    figname = 'Temp Data'  
    fig, axs = plt.subplots(2,1,num=figname)
    plt.gcf()
    plt.clf()
    axs[0] = fig.add_subplot(2,1,1)
    axs[1] = fig.add_subplot(2,1,2)
    axs[0].autoscale(enable=True,axis='both')
    axs[1].set_xlabel('Time Steps')
    axs[0].set_ylabel('Temperature (C)')
    axs[1].set_ylabel('Power (%)')
    axs[0].plot(alldata['elapsed_time'],alldata['input1'],label='temp input 1 (C)')
    axs[0].plot(alldata['elapsed_time'],alldata['input2'],label='temp input 2 (C)')
    axs[0].plot(alldata['elapsed_time'],alldata['input3'],label='temp input 3 (C)')
    axs[1].plot(alldata['elapsed_time'],alldata['pct_power1'],label='power 1 (%)')
    axs[1].plot(alldata['elapsed_time'],alldata['pct_power2'],label='power 2 (%)')
    axs[1].plot(alldata['elapsed_time'],alldata['pct_power3'],label='power 3 (%)')
    axs[0].legend()
    axs[1].legend()
    plt.pause(0.015)

    return fig, axs

def ProcData(alldata):
    """
    plot processed data
    """
    # bin data
    N = 15 # kernel length, must be odd, if even can change -R to -R-1 below
    binned1 = np.convolve(alldata['input1'],np.ones(N)/N, mode='valid')
    binned2 = np.convolve(alldata['input2'],np.ones(N)/N, mode='valid')
    binned3 = np.convolve(alldata['input3'],np.ones(N)/N, mode='valid')
    time_min = (np.array(alldata['elapsed_time']) - alldata['elapsed_time'][0])/60
    R = (N-1)//2

    plt.figure(figsize=(8,5))
    plt.plot(time_min[R:-R], 1000 * (binned1 - np.median(binned1)),label='filt 1')
    plt.plot(time_min[R:-R], 1000 * (binned2- np.median(binned2)),label='filt 2')
    plt.plot(time_min[R:-R], 1000 * (binned3- np.median(binned3)),label='filt 3')
    plt.xlabel('Time [min]')
    plt.ylabel('Mean Offset Temperature [mK]')
    plt.legend(fontsize=10)
    plt.title('Time Since %s'%time_start.isot)
    plt.savefig('.' + output_file.strip('.csv') + '_proc_bin_%s.png'%N)

    # allan deviation plot in region where data are flat
    # commented out by default - only do this if have flat region to select, must change selection indices below
    #bins = np.arange(1,50,2)
    #stds = np.zeros(len(bins))
    #for i,N in enumerate(bins):
    #    tmp_bin = np.convolve(alldata['input1'][5000:11000],np.ones(N)/N, mode='valid')
    #    stds[i]   =  np.std(tmp_bin)

    #bin_to_time = bins * 60 * np.mean(np.diff(time_min)) # in seconds
    #plt.figure()
    #plt.loglog(bins, 1000*stds)
    #plt.plot(bins, 1000*stds[0] *bins ** -0.5,'k--',label='x^-0.5' )
    #plt.xlabel('Bin Samples [sec]')
    #plt.ylabel('Sigma [mK]')
    #plt.title('Allan Deviation of Temperatures')
    #plt.legend()
    #plt.show()
    #plt.savefig('.' + output_file.strip('.csv') + '_allan.png')


# Replace 'COM4' with your Arduino's serial port
serial_port = 'COM4'
baud_rate = 9600
#os.chdir('./temperature_data')

ser = serial.Serial(serial_port, baud_rate)
time.sleep(2)  # Wait for the serial connection to initialize
alldata={} # initilize alldata

time_start = Time.now()
output_file  = './temperature_data/arduino_temp_output_jd%s.csv'%time_start.jd

try:
    while True:
        rawdata = ser.read_until(b'\n').decode('utf-8').strip()
        alldata = ProcessData(rawdata,alldata)
        WriteToFile(output_file, rawdata + '\n')
        fig, axs = ShowData(alldata)
except KeyboardInterrupt:
    print("Data logging stopped.")
finally:
    ser.close()

saved_file_path = os.path.abspath(output_file)
print(f"CSV file saved at: {saved_file_path}")

# save plot of temperatures
plt.savefig(output_file.replace('csv', 'png'))

# analyze data further
ProcData(alldata)