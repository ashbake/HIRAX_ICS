import  sys, argparse,time

from pathlib import Path
from datetime import datetime, timezone

import matplotlib.pylab as plt


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "utils" ))
from cThermal import cThermal

# Parse User Inputs
parser = argparse.ArgumentParser()
parser.add_argument('--interval', type=float, default=0,
                    help='Time between captures')
parser.add_argument('--plot', type=bool, default=False,
                    help='Whether to have plot running')
args = parser.parse_args()

# Determine night string for logging and folder creation
night = datetime.now(timezone.utc).strftime("%Y%m%d")


def ShowData(alldata):
    """
    Plot data in figure named Temp Data
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


def main():
    test = cThermal(night)

    try:
        # serial port camera
        success = test.connect()
        iter = 0
        
        if success: 
            while True:
                # Step 1 Capture image
                test.read_data()

                time.sleep(args.interval)

                # Iterate frame number and repeat loop
                iter += 1
                print(f"Reading thermal data {iter}", end='\r') 

                # running plot of alldata
                if args.plot:
                    print('plotting',args.plot)
                    ShowData(test.alldata)
        else:
            print('No Device at COM Port %s Detected' %test.config['COM_Port']) 
    except KeyboardInterrupt:
        print(f"\n\nStopped after {iter} frames")
        
    except Exception as e:
        print(f"\n\nError: {e}")
        
    finally:
        # Always cleanup
        test.disconnect()
        print(f"Session complete. {iter} temperature reads saved to {test.data_dir}")


if __name__=="__main__":
    main()