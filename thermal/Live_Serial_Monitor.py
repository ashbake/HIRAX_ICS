import serial
import csv
import time
import os

# Readout from the Arduino's serial monitor and write to a CSV file. Make sure Arduino IDE serial monitor is closed first
# Can stop the readout at any time by pressing 'Ctrl + C'

# Replace 'COM3' with your Arduino's serial port
serial_port = 'COM5'
baud_rate = 9600
os.chdir('./Serial_Monitor_Files')
output_file = os.path.join(os.getcwd(), 'Test32.csv')
# output_file = 'C:/Users/Willi/Documents/Python_Files/Random/Serial_Monitor_Files/Test11.csv'

ser = serial.Serial(serial_port, baud_rate)
time.sleep(2)  # Wait for the serial connection to initialize

with open(output_file, 'w', newline='') as csvfile:
    csv_writer = csv.writer(csvfile)
    csv_writer.writerow(['Time (s)', '% Power Output', 'RTD Temp1 (C)', 'RTD Temp2 (C)', 'Avg Temp (C)'])  # Write the header

    try:
        while True:
            line = ser.readline().decode('utf-8').strip()
            data = line.split(',')
            if len(data) == 5:
                csv_writer.writerow(data)
                print(f"Time: {data[0]}, % Power Output: {data[1]}, Temp1: {data[2]}, Temp2: {data[3]}, Avg Temp: {data[4]}")
    except KeyboardInterrupt:
        print("Data logging stopped.")
    finally:
        ser.close()

saved_file_path = os.path.abspath(output_file)
print(f"CSV file saved at: {saved_file_path}")
