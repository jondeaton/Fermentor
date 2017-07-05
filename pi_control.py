#!/usr/bin/env python

import os
import sys
import subprocess
import logging
import argparse
import time, serial, wx, threading, thread
from datetime import datetime
import numpy as np
from matplotlib import pyplot as plt
from matplotlib.font_manager import FontProperties

__version__ = 1.0
__author__ = "Jonathan Deaton (jdeaton@stanford.edu)"
__license__ = "No license"

logging.basicConfig(format='[%(asctime)s][%(levelname)s][%(funcName)s] - %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class Fermentor():

    def __init__(self):

        self.time_stamp = datetime.utcnow().strftime("%Y-%m-%d-%H%MZ")
        self.plot_dir = "plots_directory"
        self.ports_to_try = ['/dev/cu.usbmodem1421', '/dev/cu.usbmodem621', '/dev/cu.usbmodem411', '/dev/ttyACM0',
                             '/dev/ttyACM1', '/dev/ttyACM2', '/dev/ttyACM3', 'COM1', 'COM2', 'COM3', 'COM4']

        # Fermentor State
        self.is_on = False
        self.pump_is_on = False
        self.fan_is_on = False
        self.controlling_temperature = True
        self.temperature = 0
        self.motor_speed = 0
        self.default_motor_speed = 0.95
        self.red_abs = 0
        self.green_abs = 0

        # Fermentor History
        self.time_started = time.time()
        self.temperatures = np.array([])
        self.temp_times = np.array([])
        self.red_abs_hist = np.array([])
        self.green_abs_hist = np.array([])
        self.od_times = np.array([])
        self.time_running = 0

        # Serial Port Establishment
        self.ser = serial.Serial(baudrate=9600, timeout=1)
        self.try_open_serial_port()

    # FERMENTOR CONTROL

    def try_open_serial_port(self, port=None):
        """
        This function tries to open a connection w
        :return:
        """
        if port is None:
            for port in self.ports_to_try:
                try:
                    self.try_open_serial_port(port=port)
                    return
                except:
                    pass
        else:
            logger.info("Opening serial port on %s ... " % port)
            self.ser.port = port
            self.ser.open()
            logger.info("Success opening serial port")
            self.serial_checker()
            os.mkdir(self.plot_dir)


    def fan_on(self, *args):
        self.send_instruction("fan on")
        self.fan_is_on = True

    def fan_off(self, *args):
        self.send_instruction("fan off")
        self.fan_is_on = False

    def pump_on(self, *args):
        self.send_instruction("pump on")
        self.pump_is_on = True

    def pump_off(self, *args):
        self.send_instruction("pump off")
        self.pump_is_off = False

    def heater_on(self, *args):
        self.send_instruction("heater on")
        self.controlling_temperature = False

    def heater_off(self, *args):
        self.send_instruction("heater off")
        self.controlling_temperature = False

    def control_heat(self, *args):
        self.send_instruction("control heat")
        self.controlling_temperature = True

    def measure_OD(self, *args):
        self.send_instruction("OD")

    def set_motor(self, ratio, *args):
        self.motor_speed = ratio
        self.send_instruction("motor %.4f" % self.motor_speed)

    def motor_on(self, *args):
        self.set_motor(self.default_motor_speed)
        time.sleep(0.3)
        self.kickstart()

    def motor_off(self, *args):
        self.set_motor(0)

    def kickstart(self, *args):
        self.send_instruction("kickstart")

    def measure_temperature(self, *args):
        self.send_instruction("temp")

    def get_data(self, *args):
        self.send_instruction("data")

    # For resetting history or fermentor
    def reset(self, *args):
        self.send_instruction("reset")
        self.time_started = time.time()
        self.time_running = 0
        self.temperatures = np.array([])
        self.temp_times = np.array([])
        self.red_abs_hist = np.array([])
        self.green_abs_hist = np.array([])
        self.od_times = np.array([])
        print "Reset fermentor data logging"

    def light_show(self, *args):
        self.send_instruction("light show")

    def system_on(self, *args):
        self.time_started = time.time()
        self.send_instruction("on")
        self.is_on = True
        self.control_heat = True
        self.fan_is_on = True
        self.pump_is_on = True
        self.motor_speed = self.default_motor_speed
        self.controlling_temperature = True

    def system_off(self, *args):
        self.reset()
        self.send_instruction("off")
        self.is_on = False
        self.control_heat = False
        self.fan_is_on = False
        self.pump_is_on = False
        self.motor_speed = 0
        self.controlling_temperature = False

    # SERIAL INTERFACE
    def send_instruction(self, instruction):
        print "Sending instruction: \"%s\" ... " % instruction,
        sys.stdout.flush()
        try:
            self.ser.write(instruction)
            print "success"
        except:
            print "failure"

    def serial_checker(self):
        try:
            line = self.ser.readline()
            if line.startswith("OD:"):
                self.red_abs, self.green_abs = map(float, line.split()[1:])
                self.red_abs_hist = np.append(self.red_abs_hist, self.red_abs)
                self.green_abs_hist = np.append(self.green_abs_hist, self.green_abs)
                self.od_times = np.append(self.od_times, time.time() - self.time_started )
                print "Updated OD measurements: RA=%.2f GA=%.2f" % (self.red_abs, self.green_abs)
            elif line.startswith("temp:"):
                self.temperature = float(line.split()[1])
                self.temp_times = np.append(self.temp_times, time.time() - self.time_started)
                self.temperatures = np.append(self.temperatures, self.temperature)
                print "Updated temperature: %.3f deg C" % self.temperature
            elif line.startswith("data:"):
                self.red_abs_hist = np.array(map(float, line.split()[1::2]))
                self.green_abs_hist = np.array(map(float, line.split()[2::2]))
                self.red_abs = self.red_abs_hist[-1]
                self.green_abs = self.green_abs_hist[-1]
        except:
            pass

        self.checker = threading.Timer(0.01, self.serial_checker)
        self.checker.start()

    # PLOTTING
    def make_OD_plot(self):
        print "Making OD plot ... ",
        sys.stdout.flush()
        time_stamp = datetime.utcnow().strftime("%Y-%m-%d-%H%MZ")
        file_name = "%s/od_plot_%s.png" % (self.plot_dir, time_stamp)
        ratio = self.red_abs_hist / self.green_abs_hist

        plt.figure()
        plt.clf()
        red_line, = plt.plot(self.od_times, self.red_abs_hist, 'r-o', label="Red Absorbance")
        green_line, = plt.plot(self.od_times, self.green_abs_hist,'g-o', label="Green Absorbance")
        blue_line, = plt.plot(self.od_times, ratio, 'b-o', label="\'Color\' (Red / Green)")

        plt.title("Culture History")
        plt.xlabel("Seconds")
        plt.ylabel("Percent")
        plt.legend(handles=[red_line, green_line, blue_line], loc=4)

        plt.grid(True)
        plt.savefig(file_name)
        print "done"
        return file_name

    def make_temp_plot(self):
        print "Making temperature plot ... ",
        sys.stdout.flush()
        time_stamp = datetime.utcnow().strftime("%Y-%m-%d-%H%MZ")
        file_name = "%s/temp_plot_%s.png" % (self.plot_dir, time_stamp)

        plt.figure()
        plt.clf()
        temp_line, = plt.plot(self.temp_times, self.temperatures, 'k-o', label="Temperature")
        plt.plot(self.temp_times, [36 for _ in xrange(self.temp_times.shape[0])], 'r')
        plt.plot(self.temp_times, [38 for _ in xrange(self.temp_times.shape[0])], 'r')
        plt.title("Temperature History")
        plt.xlabel("Time (seconds)")
        plt.ylabel("Temperature (deg C)")
        plt.legend(handles=[temp_line], loc=4)
        plt.grid(True)
        plt.savefig(file_name)
        print "done"
        return file_name

    def make_plots(self):
        print "Making plots ... ",
        sys.stdout.flush()
        time_stamp = datetime.utcnow().strftime("%Y-%m-%d-%H%MZ")
        file_name = "%s/plots_%s.png" % (self.plot_dir, time_stamp)

        ratio = self.red_abs_hist / self.green_abs_hist

        fig = plt.figure()
        fig.set_size_inches(12,4)
        plt.clf()
        plt.subplot(131)
        red_line, = plt.plot(self.od_times/3600, self.red_abs_hist, 'r-o', label="Red Absorbance")
        green_line, = plt.plot(self.od_times/3600, self.green_abs_hist,'g-o', label="Green Absorbance")
        plt.yticks(np.arange(0, 1.10, 0.1), np.arange(0, 1.10, 0.1))
        plt.title("Optical History")
        plt.xlabel("Time (hours)")
        plt.ylabel("Optical Density")
        plt.grid(True)

        plt.subplot(132)
        blue_line, = plt.plot(self.od_times/3600, ratio, 'b-o', label="\'Color\' (Red / Green)")
        plt.title("Color History")
        plt.ylabel("Color (Red / Green)")
        plt.xlabel("Time (hours)")
        plt.grid(True)

        plt.subplot(133)
        temp_line, = plt.plot(self.temp_times/3600, self.temperatures, 'k-o', label="Temperature")
        plt.plot(self.temp_times/3600, [36 for _ in xrange(self.temp_times.shape[0])], 'r')
        plt.plot(self.temp_times/3600, [38 for _ in xrange(self.temp_times.shape[0])], 'r')
        plt.title("Temperature History")
        plt.xlabel("Time (hours)")
        plt.ylabel("Temperature (deg C)")
        plt.grid(True)

        plt.savefig(file_name)
        print "done"
        return file_name, plt

    # For recording optical data to a csv file
    def record_data(self):
        self.update_history("Recording optical data ... ")
        time_stamp = datetime.utcnow().strftime("%Y-%m-%d-%H%MZ")
        file_name = "od_data_%s.csv" % time_stamp
        np.savetxt(file_name, self.red_abs_hist, delimiter=",", fmt='%.3f', header="# OD data (Rabs then Gabs) from %s " % time_stamp)
        f = open(file_name, 'ab')
        np.savetxt(f, self.green_abs_hist, delimiter=",", fmt='%.3f')
        self.update_history(append="done")
        return file_name


# GRAPHICAL USER INTERFACE
class Frame(wx.Frame):
    def __init__(self, app, fermentor):

        self.app = app
        self.fermentor = fermentor
        self.title = "Fermentor Control Panel "
        x_dimension = 800
        y_dimension = 300

        wx.Frame.__init__(self, None, title=self.title + self.fermentor.time_stamp, size=(x_dimension, y_dimension))
        self.Bind(wx.EVT_CLOSE, self.close_app)

        panel = wx.Panel(self)
        box = wx.BoxSizer(wx.VERTICAL)

        # TITLE TEXT
        self.title_text = wx.StaticText(panel, -1, self.title)
        self.title_text.SetFont(wx.Font(14, wx.SWISS, wx.NORMAL, wx.BOLD))
        self.title_text.SetSize(self.title_text.GetBestSize())
        box.Add(self.title_text, 0, wx.ALL, 10)

        # TEMPERATURE TEXT
        self.temp_text = wx.StaticText(panel, -1, "Temperature: ")
        self.temp_text.SetFont(wx.Font(14, wx.SWISS, wx.NORMAL, wx.BOLD))
        self.temp_text.SetSize(self.temp_text.GetBestSize())
        box.Add(self.temp_text, 0, wx.ALL, 15)

        # OPTICAL DENSITY TEXT
        self.red_text = wx.StaticText(panel, -1, "Red Absorbance:\t0.0")
        self.green_text = wx.StaticText(panel, -1, "Green Absorbance:\t0.0")
        self.red_text.SetFont(wx.Font(14, wx.SWISS, wx.NORMAL, wx.BOLD))
        self.green_text.SetFont(wx.Font(14, wx.SWISS, wx.NORMAL, wx.BOLD))
        self.red_text.SetSize(self.temp_text.GetBestSize())
        self.green_text.SetSize(self.temp_text.GetBestSize())
        box.Add(self.red_text, 0, wx.ALL, 16)
        box.Add(self.green_text, 0, wx.ALL, 17)

        # TIME TEXT
        self.time_text = wx.StaticText(panel, -1, "Time running: 0 minutes")
        self.time_text.SetFont(wx.Font(14, wx.SWISS, wx.NORMAL, wx.BOLD))
        self.time_text.SetSize(self.time_text.GetBestSize())
        box.Add(self.time_text, 0, wx.ALL, 17)

        #threading.Timer(0.1, self.temperature_updater)
        #threading.Timer(0.1, self.od_updater)
        #threading.Timer(0.1, self.time_updater)

        # RADIOBUTTONS

        x_start = 300
        dx = 120
        y_top = 10
        dy = 60

        self.system_on_rb = wx.RadioButton(panel, -1, "System ON", (x_start, y_top), style=wx.RB_GROUP)
        self.Bind(wx.EVT_RADIOBUTTON, self.turn_system_on, self.system_on_rb)

        self.system_off_rb  = wx.RadioButton(panel, -1, "System OFF", (x_start, y_top+dy))
        self.Bind(wx.EVT_RADIOBUTTON, self.turn_system_off, self.system_off_rb)

        self.motor_on_rb = wx.RadioButton(panel, -1, "Motor ON",  (x_start + dx, y_top), style=wx.RB_GROUP)
        self.Bind(wx.EVT_RADIOBUTTON, self.fermentor.motor_on, self.motor_on_rb)

        self.motor_off_rb  = wx.RadioButton(panel, -1, "Motor OFF", (x_start + dx, y_top+dy))
        self.Bind(wx.EVT_RADIOBUTTON, self.fermentor.motor_off, self.motor_off_rb)

        self.pump_on_rb = wx.RadioButton(panel, -1, "Pump ON", (x_start + 2*dx, y_top), style=wx.RB_GROUP)
        self.Bind(wx.EVT_RADIOBUTTON, self.fermentor.pump_on, self.pump_on_rb)

        self.pump_off_rb = wx.RadioButton(panel, -1, "Pump OFF", (x_start + 2*dx, y_top+dy))
        self.Bind(wx.EVT_RADIOBUTTON, self.fermentor.pump_off, self.pump_off_rb)

        self.heater_on_rb = wx.RadioButton(panel, -1, "Heater ON", (x_start + 3*dx, y_top), style=wx.RB_GROUP)
        self.Bind(wx.EVT_RADIOBUTTON, self.fermentor.control_heat, self.heater_on_rb)

        self.heater_off_rb = wx.RadioButton(panel, -1, "Heater OFF", (x_start + 3*dx, y_top+dy))
        self.Bind(wx.EVT_RADIOBUTTON, self.heating_system_off, self.heater_off_rb)

        # BUTTONS

        measure_od_button = wx.Button(panel, -1, "Measure OD", (x_start+dx, y_top+2*dy))
        self.Bind(wx.EVT_BUTTON, self.fermentor.measure_OD, measure_od_button)

        update_plots_button = wx.Button(panel, -1, "Show Plots", (x_start + 2*dx, y_top+2*dy))
        self.Bind(wx.EVT_BUTTON, self.update_plot, update_plots_button)

        reset_button = wx.Button(panel, -1, "Reset", (x_start + 3*dx, y_top + 2*dy))
        self.Bind(wx.EVT_BUTTON, self.fermentor.reset, reset_button)

        close_button = wx.Button(panel, -1, "Close", (x_start + dx, y_top + 3*dy))
        self.Bind(wx.EVT_BUTTON, self.close_app, close_button)

        update_button = wx.Button(panel, -1, "Update", (100, 250))
        self.Bind(wx.EVT_BUTTON, self.update_stats, update_button)

        panel.SetSizer(box)
        panel.Layout()

    def turn_system_on(self, *args):
        self.fermentor.system_on()

        self.motor_on_rb.SetValue(True)
        self.motor_off_rb.SetValue(False)

        self.pump_on_rb.SetValue(True)
        self.pump_off_rb.SetValue(False)

        self.heater_on_rb.SetValue(True)
        self.heater_off_rb.SetValue(False)

    def turn_system_off(self, *args):
        self.fermentor.system_off()
        self.motor_on_rb.SetValue(False)
        self.motor_off_rb.SetValue(True)

        self.pump_on_rb.SetValue(False)
        self.pump_off_rb.SetValue(True)

        self.heater_on_rb.SetValue(False)
        self.heater_off_rb.SetValue(True)

    def heating_system_off(self, *args):
        self.fermentor.heater_off()
        time.sleep(0.1)
        self.fermentor.fan_off()

    def update_stats(self, *args):
        self.temperature_updater()
        self.od_updater()
        self.time_updater()

    def temperature_updater(self):
        self.temp_text.SetLabel("Temperature: %.2f deg C" % self.fermentor.temperature)

    def od_updater(self):
        self.red_text.SetLabel("Red Absorbance: %.3f" % self.fermentor.red_abs)
        self.green_text.SetLabel("Green Absorbance: %.3f" % self.fermentor.green_abs)

    def time_updater(self):
        self.fermentor.time_running = time.time() - self.fermentor.time_started
        self.time_text.SetLabel("Time running:\t%dm %ds" % (self.fermentor.time_running//60, self.fermentor.time_running%60))

    def update_plot(self, event):
        file, plt = self.fermentor.make_plots()
        plt.show()

    def close_app(self, event):
        logger.info("Turning fermentor off...")
        self.fermentor.system_off()
        logger.info("Closing app...")
        sys.exit(0)

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument("-fake", "--fake_data", action='store_true', help="Display fake data")
    args = parser.parse_args()

    fermentor = Fermentor()
    fermentor.fake_data = args.fake_data


    logger.info("Opening GUI... ")
    app = wx.App(redirect=True)
    Frame(app, fermentor).Show()
    app.MainLoop()
    exit()