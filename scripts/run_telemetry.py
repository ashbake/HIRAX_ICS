import  sys, argparse,time

from pathlib import Path
from datetime import datetime, timezone


sys.path.insert(0, str(Path.cwd().resolve().parent / "utils" ))
from cThermal import cThermal

# Parse User Inputs
parser = argparse.ArgumentParser()
parser.add_argument('--interval', type=float, default=0,
                    help='Time between captures')
args = parser.parse_args()

# Determine night string for logging and folder creation
night = datetime.now(timezone.utc).strftime("%Y%m%d")


def main():
    test = cThermal(night)

    try:
        # connect camera
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
        else:
            print('No Camera Detected') 
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