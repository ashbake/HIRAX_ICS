# usage 
# python run_science.py 'test' 0.2
import  sys, argparse,time

from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path.cwd().resolve().parent / "utils" ))
from cSBIG import cSBIG

# Parse User Inputs
parser = argparse.ArgumentParser()
try:
    parser.add_argument('source', default='test', type=str,help='Target Name[str]')
    parser.add_argument('exp_time', default=0, type=float, help='Exposure Time in seconds [float]')
    parser.add_argument('--interval', type=float, default=0,
                        help='Time between captures')
    args = parser.parse_args()
except:
    args = parser.parse_args()
    args.exp_time = 0
    args.source= 'test'
    args.interval=0

# Determine night string for logging and folder creation
night = datetime.now(timezone.utc).strftime("%Y%m%d")


def main():
    camera = cSBIG(night, args.source)
    camera.connect()

    try:
        # connect camera
        # exptype - 1 for science, 0 for bias
        exptype=0 if args.exp_time ==0 else 1
        success = camera.Expose(args.exp_time, exptype)
        iter = 0
        time0 = time.time()
        if success: 
            while True:
                # Step 1 Capture image

                camera.Expose(args.exp_time, exptype)
                #camera.saveImage()

                time.sleep(args.interval)

                # Iterate frame number and repeat loop
                iter += 1
                print(f"Reading thermal data {iter}", end='\r')  
        else:
            print('No Camera Detected') 
    except KeyboardInterrupt:
        print(f"\n\nStopped after {iter} frames")
        print(time0 - time.time())
        
    except Exception as e:
        print(f"\n\nError: {e}")
        
    finally:
        # Always cleanup
        camera.disconnect()
        print(f"Session complete. {iter} temperature reads saved to {camera.data_dir}")


if __name__=="__main__":
    main()
    #pass