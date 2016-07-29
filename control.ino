// Module 4 Arduino Driver
// BIOE 123, Winter 2016, 02.25.2016
// Group: Jon Deaton, Katie Donahue, Mark Kirollos

#include <EEPROM.h>

// Pin definition
int motor_pin = 10;
int heater_pin = 6;
int temp_pin = 0;
int fan_pin = 5;
int pump_pin = 3;
int red_read_pin = 5;
int green_read_pin = 3;
int red_LED_pin = 13;
int green_LED_pin = 11;

//OD Reader
unsigned long last_od_measurement = 0;
//unsigned long time_between_ods = 20000;
unsigned long time_between_ods = 20000;
int start_address = 0;
int od_address = start_address;
bool recording_data = true;

// Heating Control
bool heat_controlled = true;
float set_point = 37.0;
unsigned long last_temp_control = 0;
unsigned long time_between_temps = 5000;

// Motor Control
float max_duty_cycle = 0.2;
int kickstart_duration = 1; // microseconds
float motor_speed = 0.0;

// State
float red_absorbance = 0;
float green_absorbance = 0;
float temp = 0.0;
bool pump_is_on = false;
bool heater_is_on = false;
bool fan_is_on = false;
bool is_on = true;

void setup() {
  Serial.begin(9600);
  
  pinMode(motor_pin, OUTPUT);
  pinMode(heater_pin, OUTPUT);
  pinMode(fan_pin, OUTPUT);
  pinMode(pump_pin, OUTPUT);

  // OD Reader
  pinMode(red_LED_pin, OUTPUT);
  pinMode(green_LED_pin, OUTPUT);

  analogWrite(green_LED_pin, LOW);
  analogWrite(red_LED_pin, LOW);
  
  last_od_measurement = millis();
  last_temp_control = millis();
  od_address = start_address;
  is_on = false;
}

void loop() {
  // Look for data coming in from Serial
  if(Serial.available() > 0) {
    execute_instruction(read_line());
  }

  if(is_on) {
    analogWrite(motor_pin, (int) (255 * max_duty_cycle * motor_speed));
    analogWrite(pump_pin, 255 * pump_is_on);
    analogWrite(fan_pin, 255 * fan_is_on);

    if(millis() - last_od_measurement >= time_between_ods) {
      measure_recoard_od();
      last_od_measurement = millis();
    }

    if (heat_controlled && (millis() - last_temp_control >= time_between_temps)) {
      control_temperature();
      last_temp_control = millis();
    } else {
      analogWrite(heater_pin, 255 * heater_is_on);
      analogWrite(fan_pin, 255 * fan_is_on);
    }
    
  } else {
    // System is off
    analogWrite(motor_pin, 0);
    analogWrite(pump_pin, 0);
    analogWrite(fan_pin, 0);
    analogWrite(heater_pin, 0);
  }
}

// Reads a line of instruction from Serial
String read_line() {
  String line = "";
  while(Serial.available() > 0) {
    char char_in = (char) Serial.read();
    line += char_in;
  }
  return line;
}

// Ececutes an instruction line
void execute_instruction(String instruction) {
  
  if (instruction.equals("on")) {
    turn_on();
  } else if (instruction.equals("off")) {
    turn_off();
  } else if (instruction.equals("fan on")) {
    fan_is_on = true;
  } else if (instruction.equals("fan off")) {
    fan_is_on = false;
  } else if (instruction.equals("pump on")) {
    pump_is_on = true;
  } else if (instruction.equals("pump off")) {
    pump_is_on = false;
  } else if (instruction.equals("temp")) {
    Serial.print("temp: ");
    Serial.println(String(measure_temp(), 4));
  } else if (instruction.equals("OD")) {
    measure_od();
  } else if (instruction.equals("kickstart")) {
    kickstart_motor();
  } else if (instruction.equals("light show")) {
    light_show();
  } else if (instruction.equals("heater on")) {
    heater_is_on = true;
    heat_controlled = false;
  } else if (instruction.equals("heater off")) {
    heater_is_on = false;    
    heat_controlled = false;
  } else if (instruction.equals("control heat")) {
    heat_controlled = true;
    fan_is_on = true;
  } else if (instruction.equals("data")) {
    send_data();
  } else if(instruction.equals("reset")) {
    start_address = od_address;
  } else if (instruction.startsWith("motor")) {
    motor_speed = instruction.substring(6).toFloat();
  } 
}

void measure_od() {
  // Pump + Motor off
  analogWrite(pump_pin, 0);
  analogWrite(motor_pin, 0);
  analogWrite(heater_pin, 0);
  analogWrite(fan_pin, 0);
  delay(300);

  // Measure Red
  analogWrite(red_LED_pin, 128);
  delay(1000);
  float red_V = measure_pin(red_read_pin) * 5 / 1023.0;
  analogWrite(red_LED_pin, 0);
  
  // Measure Green
  analogWrite(green_LED_pin, 128);
  delay(1000);
  float green_V = measure_pin(green_read_pin) * 5 / 1023.0;
  analogWrite(green_LED_pin, 0);

  // Turn back on and return value
  kickstart_motor();
  red_absorbance = calculate_red(red_V);
  green_absorbance = calculate_green(green_V);
  Serial.print("OD: ");
  Serial.print(red_absorbance);
  Serial.print(" ");
  Serial.println(green_absorbance);
}

void measure_recoard_od() {
  measure_od();
  EEPROM.write(od_address, (byte) red_absorbance * 255);
  EEPROM.write(od_address + 1, (byte) green_absorbance * 255);
  od_address = (2 + od_address) % EEPROM.length();
}

float measure_pin(int pin) {
  int sum = 0;
  int num_samples = 10;
  for(int i = 1; i < num_samples; i++) {
   sum += analogRead(pin);
   delay(10);
  }
  return (1.0 * sum) / num_samples;
}

float calculate_red(float red_V) {
  float baseline = 0.8;
  float max_V = 3.5;
  return (max_V - red_V) / (max_V - baseline);
}

float calculate_green(float green_V) {
  float baseline_V = 0.9;
  float max_V = 3.5;
  return (max_V - green_V) / (max_V - baseline_V);
}

// BANG-BANG
void control_temperature() {
  fan_is_on = true;
  measure_temp();
  if(temp <= set_point) {
    heater_is_on = true;
  } else {
    heater_is_on = false;
  }
}

float measure_temp() {
  analogWrite(pump_pin, 0);
  analogWrite(motor_pin, 0);
  analogWrite(heater_pin, 0);
  analogWrite(fan_pin, 0);
  delay(10);
  float thermosensor_V = 5 * measure_pin(temp_pin) / 1023.0;
  temp = voltage_to_temp(thermosensor_V);
  Serial.print("temp: ");
  Serial.println(temp, 4);
  return temp;
}

// Converts thermosensor voltage into a temperature
float voltage_to_temp(float voltage) {
  float calibration = 2;
  float m = 0.018;
  float b = 0.271;
  return (voltage - b) / m + calibration;
}

void send_data() {
  Serial.print("data: ");
  for(int i = start_address; i < od_address; i++) {
    Serial.print(EEPROM.read(i));
    Serial.print(" ");
  }
  Serial.println("");
}

// Function used to kickstart motor from stopped position
void kickstart_motor() {
  analogWrite(motor_pin, 255);
  delay(kickstart_duration);
}

// Turns the system on
void turn_on() {
  heat_controlled = true;
  is_on = true;
  analogWrite(red_LED_pin, 255);
  analogWrite(green_LED_pin, 255);
  digitalWrite(fan_pin, 255);
  digitalWrite(pump_pin, 255);
  motor_speed = 0.95;
  pump_is_on = true;
  fan_is_on = true;
  heater_is_on = true;
  heat_controlled = true;
  recording_data = true;
  analogWrite(red_LED_pin, 0);
  analogWrite(green_LED_pin, 0);
  light_show();
  kickstart_motor();
}

// Turns the system off
void turn_off() {
  is_on = false;
  heat_controlled = false;
  recording_data = false;
  digitalWrite(fan_pin, 0);
  digitalWrite(pump_pin, 0);
  analogWrite(heater_pin, 0);
  analogWrite(red_LED_pin, 0);
  analogWrite(green_LED_pin, 0);
  light_show();
}

// Just for fun
void light_show() {
  int del = 40;
  int N = 10;
  for(int i = 1; i <= N; i++) {
    analogWrite(red_LED_pin, 128);
    analogWrite(green_LED_pin, 0);
    delay(del);
    analogWrite(red_LED_pin, 0);
    analogWrite(green_LED_pin, 128);
    delay(del);
  }

  for(int i = 1; i <= N; i++) {
    analogWrite(red_LED_pin, 128);
    analogWrite(green_LED_pin, 128);
    delay(del);
    analogWrite(red_LED_pin, 0);
    analogWrite(green_LED_pin, 0);
    delay(del);
  }
}


