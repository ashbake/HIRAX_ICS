/********************************************************
//PID controller that reads inputs from multiple RTD sensors (takes the average) and outputs heat accordingly. 
// Controlls 3 PID loops independently. 
// Adapted by Will Melby for HIRAX
// Edited by Ashley Baker and Jake Zimmer
 ********************************************************/

#include <PID_v1.h>
#include <Motoron.h>
#include <Wire.h>
#include <Adafruit_MAX31865.h>
// #include <ArduinoSTL.h>
// #include <Ethernet.h>
// #include <SPI.h>

using namespace std;

// THIS INITIALIZES TEMP SENSOR BOARD CONNECTIONS
// Use software SPI: CS, DI, DO, CLK
// CS chip is assigned to each board, 10 total boards
// 6 are for filters, four for temps on breadboard
// a is on top and b is on bottom **TODO: Check this**
Adafruit_MAX31865 filt1a = Adafruit_MAX31865(1, 11, 12, 13);
Adafruit_MAX31865 filt1b = Adafruit_MAX31865(2, 11, 12, 13);
Adafruit_MAX31865 filt2a = Adafruit_MAX31865(3, 11, 12, 13);
Adafruit_MAX31865 filt2b = Adafruit_MAX31865(4, 11, 12, 13);
Adafruit_MAX31865 corner = Adafruit_MAX31865(5, 11, 12, 13);
Adafruit_MAX31865 filt3a = Adafruit_MAX31865(6, 11, 12, 13);
Adafruit_MAX31865 filt3b = Adafruit_MAX31865(7, 11, 12, 13);
Adafruit_MAX31865 stage  = Adafruit_MAX31865(8, 11, 12, 13);
Adafruit_MAX31865 middle = Adafruit_MAX31865(9, 11, 12, 13);
Adafruit_MAX31865 air    = Adafruit_MAX31865(10, 11, 12, 13);

// The value of the Rref resistor. Use 430.0 for PT100 and 4300.0 for PT1000
#define RREF      430.0
#define MAXPOWER  514 // from 800 * 9W / 14W. Motoron max out is 800, max heater power is 9W but voltage and resistance would make max 14W

// The 'nominal' 0-degrees-C resistance of the sensor
// 100.0 for PT100, 1000.0 for PT1000
// TOODO - ICE BATH TO DETERMINE RESISTANCE see https://learn.adafruit.com/adafruit-max31865-rtd-pt100-amplifier/arduino-code
#define RNOMINAL  100.0

// setup Controller for powering heaters
MotoronI2C mc;

//Allocate memmory to Variables we'll be using
double Setpoint;
double Input1, Input2, Input3;
double Output1, Output2, Output3;
float filt_T1, filt_T2, filt_T3;

// Define tuning parameters
double Kp=20, Ki=3, Kd=0.02;

// Setup PID instance 
PID myPID1(&Input1, &Output1, &Setpoint, Kp, Ki, Kd, DIRECT);
PID myPID2(&Input2, &Output2, &Setpoint, Kp, Ki, Kd, DIRECT);
PID myPID3(&Input3, &Output3, &Setpoint, Kp, Ki, Kd, DIRECT);

// compute_set_temp determines filter temp set point from temp1 and temp2
// and turns off heaters if temps are reading out errors (<0)
// by setting temp to the setpoint
// bad temps seem to be 988.79 but then this would turn off power to heater
double compute_set_temp(double temp1, double temp2)
{
	if  ((temp1 < 0) && (temp2 < 0)) {
		return Setpoint;
	}
	if (temp2 < 0) {
		return temp1;
	}
	if ((temp1 < 0) ) {
		return temp2;
	}
	
	return (temp1 + temp2)/2 ;
}

double average(float a[], int n)
{
    // Find sum of array element
    float sum = 0;
    for (int i = 0; i < n; i++)
        sum += a[i];

    return (double)sum / n;
}

void setup()
{
  Serial.begin(9600);  //baud rate
  Wire.begin();

  Setpoint = 31; // 30 desired but go higher because measuring temperature on the rim

  // reset the motor controller
  mc.reinitialize();    // Bytes: 0x96 0x74
  mc.disableCrc();      // Bytes: 0x8B 0x04 0x7B 0x43
  mc.clearResetFlag();  // Bytes: 0xA9 0x00 0x04

  filt1a.begin(MAX31865_2WIRE);  // set to 2WIRE or 4WIRE as necessary
  filt1b.begin(MAX31865_2WIRE);  
  filt2a.begin(MAX31865_2WIRE); 
  filt2b.begin(MAX31865_2WIRE); 
  corner.begin(MAX31865_2WIRE); 
  filt3a.begin(MAX31865_2WIRE); 
  filt3b.begin(MAX31865_2WIRE); 
  stage.begin(MAX31865_2WIRE); 
  middle.begin(MAX31865_2WIRE); 
  air.begin(MAX31865_2WIRE); 

  // Input the average of two sensors on each filter
  // TODO average last five temperatures
  // initiate array of stored temperatures for averaging
  Input1 = compute_set_temp(filt1a.temperature(RNOMINAL, RREF) , filt1b.temperature(RNOMINAL, RREF));
  Input2 = compute_set_temp(filt2a.temperature(RNOMINAL, RREF) , filt2b.temperature(RNOMINAL, RREF));
  Input3 = compute_set_temp(filt3a.temperature(RNOMINAL, RREF) , filt3b.temperature(RNOMINAL, RREF));

  //turn the PID on
  myPID1.SetMode(AUTOMATIC);
  myPID2.SetMode(AUTOMATIC);
  myPID3.SetMode(AUTOMATIC);  

  // Setting the power limits of the output motor (800 defined in motoron.h)
  myPID1.SetOutputLimits(0, MAXPOWER);
  myPID2.SetOutputLimits(0, MAXPOWER);
  myPID3.SetOutputLimits(0, MAXPOWER);
}

void loop()
{
  static unsigned long startTime = millis();
  unsigned long currentTime = millis();
  float elapsedTime = (currentTime - startTime) / 1000.0;

  filt_T1 = compute_set_temp(filt1a.temperature(RNOMINAL, RREF) , filt1b.temperature(RNOMINAL, RREF));
  filt_T2 = compute_set_temp(filt2a.temperature(RNOMINAL, RREF) , filt2b.temperature(RNOMINAL, RREF));
  filt_T3 = compute_set_temp(filt3a.temperature(RNOMINAL, RREF) , filt3b.temperature(RNOMINAL, RREF));

  // updating running temps with new temperatures
  float running_temps1 [] = {filt_T1, running_temps1[0], running_temps1[1], running_temps1[2], running_temps1[3]};
  float running_temps2 [] = {filt_T2, running_temps2[0], running_temps2[1], running_temps2[2], running_temps2[3]};
  float running_temps3 [] = {filt_T3, running_temps3[0], running_temps3[1], running_temps3[2], running_temps3[3]};

  // average running temps for input to PID loop
  Input1 = average(running_temps1, 5);
  Input2 = average(running_temps2, 5);
  Input3 = average(running_temps3, 5);

  // compute PID loop - Outputs will be updated
  myPID1.Compute();
  myPID2.Compute();
  myPID3.Compute();

  //Pull out all temperatures
  float RTD_temp1a = filt1a.temperature(RNOMINAL, RREF);
  float RTD_temp1b = filt1b.temperature(RNOMINAL, RREF);
  float RTD_temp2a = filt2a.temperature(RNOMINAL, RREF);
  float RTD_temp2b = filt2b.temperature(RNOMINAL, RREF);
  float RTD_temp5  = corner.temperature(RNOMINAL, RREF);
  float RTD_temp3a = filt3a.temperature(RNOMINAL, RREF);
  float RTD_temp3b = filt3b.temperature(RNOMINAL, RREF);
  float RTD_temp8  = stage.temperature(RNOMINAL, RREF);
  float RTD_temp9  = middle.temperature(RNOMINAL, RREF);
  float RTD_temp10 = air.temperature(RNOMINAL, RREF);
  
  // define percent power for printing
  // 64 Ohm resistors, 9W max power rating
  float percent_power1 = (Output1/MAXPOWER)*100;
  float percent_power2 = (Output2/MAXPOWER)*100;
  float percent_power3 = (Output3/MAXPOWER)*100;
  
  // Control motor speed based on PID output
  mc.setSpeedNow(1, Output1);
  mc.setSpeedNow(2, Output2);
  mc.setSpeedNow(3, Output3);

  // Just print the organized outputs I want as Time, Power Outputs, Temps
  Serial.print(elapsedTime);
  Serial.print(",");
  Serial.print(Input1);
  Serial.print(",");
  Serial.print(Input2);
  Serial.print(",");
  Serial.print(Input3);
  Serial.print(",");
  Serial.print(percent_power1);
  Serial.print(",");
  Serial.print(percent_power2);
  Serial.print(",");
  Serial.print(percent_power3);
  Serial.print(",");
  Serial.print(RTD_temp1a);
  Serial.print(",");
  Serial.print(RTD_temp1b);
  Serial.print(",");
  Serial.print(RTD_temp2a);
  Serial.print(",");
  Serial.print(RTD_temp2b);
  Serial.print(",");
  Serial.print(RTD_temp3a);
  Serial.print(",");
  Serial.print(RTD_temp3b);
  Serial.print(",");
  Serial.print(RTD_temp5);
  Serial.print(",");
  Serial.print(RTD_temp8);
  Serial.print(",");
  Serial.print(RTD_temp9);
  Serial.print(",");
  Serial.print(RTD_temp10);
  Serial.print(",");
  Serial.print('\n');

  delay(150);
}
