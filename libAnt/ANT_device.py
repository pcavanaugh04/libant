# -*- coding: utf-8 -*-
"""
Created on Mon Mar 11 10:41:23 2024

@author: pcavana
"""

# from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QListWidgetItem
# from PyQt5 import uic
# from PyQt5.QtCore import QTimer
# import sys
import os
# import time
import math
from datetime import datetime
from PyQt5.QtCore import pyqtSlot, pyqtSignal, QObject, QThread
from libAnt.node import Node
from libAnt.drivers.usb import DriverException
from libAnt.message import BroadcastMessage, ChannelResponseMessage
import libAnt.exceptions as e
# import libAnt.constants as c
# import logging
import functools
import libAnt.profiles.fitness_equipment_profile as p
import libAnt.profiles.power_profile as pwr
import libAnt.profiles.speed_cadence_profile as scp


class ANTDevice(QObject):
    """Interface with ANTUSB stick to communicate with other ANT devies.

    An "ANT Device" will primarily refer to an FE-C enabled trainer. However
    It will eventually encapsulate all data streams coming from the device
    in question
    """

    device_types = {
        'FE-C': 17, 'PWR': 11, 'SPD': 123,
        'CD': 122, 'SPD+CD': 121, 'HR': 0x78}

    connection_signal = pyqtSignal(bool)
    success_signal = pyqtSignal('PyQt_PyObject')
    failure_signal = pyqtSignal('PyQt_PyObject')
    tx_success = pyqtSignal('PyQt_PyObject')

    USB_DRIVER_FAIL_THRESHOLD = 3  # Attempts to init USB Node before failing

    def __init__(self, debug=False, logger=None):
        super().__init__()
        self.node = None
        self.connected = False

        # Attributes used for writing sensor data to file
        self.log_file = None
        self.file_open_flag = False
        self._log_data_flag = False
        self._log_path = ""
        self._log_name = ""
        self.name = "trainer"
        self.connected = False
        self.channels = []
        self.messages = []
        self.prev_msg_len = 0
        self.trainer_msgs = [None]
        self.data = ANTData()
        self.datas = []
        self.debug = debug
        self.prev_msg_len = 0
        self.event_count = 0
        self.grade = 0
        # self.wheel_diameter = None
        self.wheel_diameter = 0.7
        self.FE_C_channel = None
        self.user_weight = 75  # User Weight in kg

        # Pass in logger functionality
        self.logger = logger

        def success_handler(msg):

            if type(msg) == BroadcastMessage:
                # Decide which channel to store in
                ANT_channel = self.channels[msg.channel]
                # FEC Specific Handling
                if ANT_channel.device_type == self.device_types['FE-C']:
                    # Extract power information from trainer specific data page
                    if int(msg.content[0]) == 0x19:
                        trainer_msg = p.TrainerDataPage(
                            msg,
                            ANT_channel.data.prev_trainer_msg)
                        # ANT_channel.messages.append(f"{trainer_msg}")
                        self.data.inst_power = trainer_msg.inst_power
                        self.data.avg_power = trainer_msg.avg_power
                        # self.ANT_channel.event_count = trainer_msg.event
                        try:
                            self.data.torque = (
                                self.data.avg_power
                                / (self.data.rpm / 60 * 2 * math.pi))
                        except ZeroDivisionError:
                            self.data.torque = 0

                        self.data.timestamp = trainer_msg.timestamp
                        ANT_channel.data = FECData(data=self.data)
                        ANT_channel.data.prev_trainer_msg = trainer_msg

                    # Extract speed info from general FE data page
                    elif int(msg.content[0]) == 0x10:
                        FE_msg = p.GeneralFEDataPage(msg)
                        speed_kph = FE_msg.speed * 3600 / 10**6
                        self.data.speed = speed_kph
                        rpm = speed_kph * 1000 / 60 / \
                            (math.pi * self.wheel_diameter)
                        self.data.rpm = rpm
                        try:
                            self.data.torque = (self.data.avg_power
                                                / (rpm / 60 * 2 * math.pi))
                        except ZeroDivisionError:
                            self.data.torque = 0

                        self.data.timestamp = FE_msg.timestamp
                        ANT_channel.data = FECData(data=self.data)

                    else:
                        self.data.timestamp = datetime.now()
                        ANT_channel.data = FECData(self.data)

                    # Create a new ANTData object, pre-populated with prev data
                    # self.data = ANTData(self.data)

                elif ANT_channel.device_type == self.device_types['PWR']:

                    # Case for Power-only page
                    if int(msg.content[0] == 0x10):
                        # Build Profile data from broadcast message
                        power_msg = pwr.PowerDataPage(
                            msg, ANT_channel.data.prev_power_msg)
                        # update data attributes for program display
                        self.data.inst_power = power_msg.inst_power
                        self.data.avg_power = power_msg.avg_power
                        self.data.timestamp = power_msg.timestamp
                        # Update channel data for saving
                        ANT_channel.data.inst_power = power_msg.inst_power
                        ANT_channel.data.avg_power = power_msg.inst_power
                        ANT_channel.data.timestamp = power_msg.timestamp
                        ANT_channel.data.prev_power_msg = power_msg

                    # ANT_channel.event_count = power_msg.event

                    # Case for torque-only page
                    elif int(msg.content[0] == 0x11):
                        # Build Profile data from broadcast message
                        torque_msg = pwr.TorqueDataPage(
                            msg, ANT_channel.data.prev_torque_msg)
                        self.data.avg_torque = torque_msg.avg_torque
                        self.data.timestamp = torque_msg.timestamp
                        # Build Profile data from broadcast message
                        ANT_channel.data.avg_torque = torque_msg.avg_torque
                        ANT_channel.data.timestamp = torque_msg.timestamp
                        ANT_channel.data.prev_torque_message = torque_msg

                elif ANT_channel.device_type == self.device_types['SPD+CD']:
                    if int(msg.content[0] == 0x00):
                        # Build profile data from broadcast message
                        spd_cd_msg = scp.SpeedCadencePage(
                            msg,
                            self.wheel_diameter,
                            ANT_channel.data.prev_message)
                        # update data attributes for program display
                        self.data.cadence = float(spd_cd_msg.cadence)
                        self.data.speed = float(spd_cd_msg.speed)
                        self.data.timestamp = spd_cd_msg.timestamp
                        # Update channel data for saving
                        ANT_channel.data.cadence = spd_cd_msg.cadence
                        ANT_channel.data.speed = spd_cd_msg.speed
                        ANT_channel.data.timestamp = spd_cd_msg.timestamp

                elif ANT_channel.device_type == self.device_types['SPD']:
                    pass

                elif ANT_channel.device_type == self.device_types['CD']:
                    pass

                else:
                    pass
                    # ANT_channel.messages.append(f'{msg}')

                if self.log_data_flag:
                    ANT_channel._save_data(ANT_channel.data)

                self.datas.append(self.data)
                ANT_channel.messages.append(f'{msg}')

            # Special case for acknowledged transmission event
            elif (type(msg) == ChannelResponseMessage
                  and msg.event_code == 0x05):
                self.channels[msg.channel].messages.append('Tx Success!')

            else:
                self.messages.append(f'{msg}')

        def fail_handler(msg):
            if hasattr(msg, 'channel'):
                self.channels[msg.channel].messages.append(f'{msg}')
            else:
                self.messages.append(f'{msg}')

            if isinstance(msg, e.RxSearchTimeout):
                if self.connected and self.channels[msg.channel].is_active:
                    self.disconnect()
                    # logger.warning("ANT+ Trainer Connection Timeout. "
                    # "Disconnecting Device")
                else:
                    pass

            # if isinstance(msg, DriverException):
            #     self.clear_device()

        self.success_signal.connect(success_handler)
        self.failure_signal.connect(fail_handler)

        # Define avaliable Device Profiles
        self.dev_profiles = list(self.device_types.keys())

    # def add_message(self, msg):
    #     """Add message to node message array or respective channel"""

    #     if hasattr(msg, "channel"):
    #         channel = msg.channel
    #     else:
    #         channel = None
    #     msg = str(msg)
    #     self.node.add_msg(msg, channel)

    def init_node(self, debug=False):
        """Checks to see if specified ANT USB Stick Hardware is recognized."""
        if self.node is not None:
            return

        fail_count = 0
        # Iterate through loop until fail criteria is met
        while True:
            try:
                # Try to initialize Node with specified ANT USBStick-2 or -m
                # driver characteristics
                self.node = Node(debug=debug)
                return  # Exit the loop if initialization succeeds
            except DriverException as e:
                fail_count += 1
                if fail_count > self.USB_DRIVER_FAIL_THRESHOLD:
                    raise e

    def init_start_node_thread(self):
        """Start the USB loop of the ANT USB Node.

        Function will attempt to construct the USB node and determine if
        starting the thread is necessary. Returns the start
        thread object if created so calling objects can connect signals upon
        completion. Calling function will need to connect slots to completion
        signals and start the thread.

        Parameters
        ----------
        None

        Returns
        -------
        start_thread: ANTWorker
        Instance of worker thread created to execute the node start function
        and completion monitoring.
        """
        try:
            self.init_node(debug=self.debug)
        except DriverException as e:
            raise e

        else:
            if (self.node is not None) and (not self.node.isRunning()):
                start_thread = ANTWorker(self,
                                         self.node.start,
                                         self.callback,
                                         self.error_callback)
                return start_thread

    def init_channels(self, success):
        """Initialize channel attribures of ANT device."""
        if success:
            self.channels = [ANTChannel(i)
                             for i in range(self.node.max_channels)]

    def update_connection_status(self, connected: bool):
        """Update connected attribute and emit connected signal."""
        self.connected = connected
        self.connection_signal.emit(connected)

        if connected:
            for channel in self.channels:
                if channel.device_type == 17:
                    self.FE_C_channel = channel.number

    @pyqtSlot()
    def callback(self, msg):
        self.success_signal.emit(msg)

    @pyqtSlot()
    def error_callback(self, emsg):
        self.failure_signal.emit(emsg)

    def set_track_resistance(self, **kwargs):
        """Create and send a track resistance page to the device.

        Parameters
        ----------
        channel: int
            Number of channel the tx message should be sent on

        Returns
        -------
        None.

        """

        if self.FE_C_channel is not None:
            channel = self.FE_C_channel

        else:
            self.node.add_msg(
                "Warning: Cannot Send Track Resistance message without FE-C Channel")
            return

        channel = self.FE_C_channel
        self.grade = kwargs.get("grade")
        grade = p.set_grade(channel, **kwargs)
        self.send_tx_msg(grade)
        self.channels[channel].messages.append(
            f"Track Resistance Command Sent: {kwargs}")

    def set_config(self, **kwargs):
        """Create and send a user config page to the device.

        Parameters
        ----------
        channel: int
            Number of channel the tx message should be sent on

        Returns
        -------
        None.
        """
        if self.FE_C_channel is not None:
            channel = self.FE_C_channel

        else:
            self.node.add_msg(
                "Warning: Cannot Send User Config message without FE-C Channel")
            return
        cfg = p.set_user_config(channel, **kwargs)
        if "user_weight" in kwargs:
            self.user_weight = kwargs['user_weight']
        self.send_tx_msg(cfg)
        self.channels[channel].messages.append(
            f"User Config Command Sent: {kwargs}")

    def send_tx_msg(self, msg):
        """Send tx message to ANT Device"""

        tx_thread = ANTWorker(self,
                              self.node.send_tx_msg,
                              msg)
        tx_thread.done_signal.connect(functools.partial(self.tx_msg_status,
                                                        msg))
        tx_thread.start()

    def tx_msg_status(self, msg, success):
        """Callback to determine success state of tx message. Repeat message
        if failed"""

        self.tx_success.emit(success)
        if success:
            pass
        else:
            self.send_tx_msg(msg)

    def disconnect(self, timeout=False):
        """Disconnect all active channels on the ANT device."""

        print("In ANT_device disconnect method")

        # Close log file, if active
        if self.log_data_flag:
            self.log_data_flag = False

        # Close channels
        for channel in self.node.channels:
            if (channel is not None) and not (channel.closing):
                channel_close_thread = ANTWorker(self,
                                                 channel.close
                                                 )
                channel_close_thread.done_signal.connect(
                    self.node.clear_channel)
                channel_close_thread.start()
                self.channels[channel.number].is_active = False

            channel_close_thread.done_signal.connect(
                lambda: self.update_connection_status(False))
        self.FE_C_channel = None

    def close_channel(self, channel_num, connection=None):
        """Close channel and remove channel object from node."""
        close_thread = ANTWorker(self, self.node.channels[channel_num].close,
                                 channel_num)
        close_thread.done_signal.connect(self.node.clear_channel)
        if connection is not None:
            close_thread.done_signal.connect(connection)
        close_thread.done_signal.connect(
            lambda: self.connection_signal.emit(False))
        close_thread.start()

    @property
    def log_name(self):
        """log_name attribute getter."""
        return self._log_name

    @log_name.setter
    def log_name(self, log_name: str):
        self._log_name = log_name
        for channel in self.channels:
            if channel.is_active:
                channel.log_name = log_name

    @property
    def log_path(self):
        """log_path attribute getter."""
        return self._log_path

    @log_path.setter
    def log_path(self, log_path: str):
        self._log_path = log_path
        for channel in self.channels:
            if channel.is_active:
                channel.log_path = log_path

    @property
    def log_data_flag(self):
        """Getter for log_data_flag attribute."""
        return self._log_data_flag

    @log_data_flag.setter
    def log_data_flag(self, set_value: bool):
        self._log_data_flag = set_value
        for channel in self.channels:
            if channel.is_active:
                channel.log_data_flag = set_value

    def close_log_file(self):
        self.log_data_flag = False


class ANTChannel():
    """Store channels specific data Coming from an ANT communication stream"""

    def __init__(self, number):
        self.is_active = False
        self.type = None
        self._device_type = None
        self._profile = None
        self.device_number = None
        self.state = None
        self.network_number = None
        self.number = number
        self.data = ANTData()
        self.messages = []
        self.prev_message = None
        self.prev_msg_len = 0
        self.event_count = None
        self.datas = []
        self.file_open_flag = False
        self._log_data_flag = False
        self.log_name = ""
        self.log_path = ""
        self.log_start_time = None
        self.log_file = None
        self._device_profiles = {value: key for key,
                                 value in ANTDevice.device_types.items()}

    @property
    def device_type(self):
        return self._device_type

    @device_type.setter
    def device_type(self, value):
        if value in self._device_profiles:
            self._device_type = value
            self._profile = self._device_profiles[value]
        else:
            raise ValueError(f"Invalid device type: {value}")

    @property
    def profile(self):
        return self._profile

    @property
    def log_data_flag(self):
        return self._log_data_flag

    @log_data_flag.setter
    def log_data_flag(self, set_value: bool):
        self._log_data_flag = set_value
        if set_value:
            self._open_log_file()

        else:
            self.close_log_file()

    def _open_log_file(self):
        """Open a file to record sensor data.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        # TODO: Make sure theres a good way to set log_name attribute
        file_name = f"{self.log_name}-{self.profile}_data.csv"
        # msg_file_name = f"{self.log_name}-{self.name}_messages.csv"
        self.log_file_path = os.path.join(self.log_path, file_name)
        # msg_file_path = os.path.join(self.log_path, msg_file_name)
        self.log_file = open(self.log_file_path, 'w')
        # self.msg_file = open(msg_file_path, 'w')

        # Write data header to first line of file
        self.log_file.write(
            f"datetime,elapsed_time,{self.data._DATA_HEADER}\n")
        # self.msg_file.write("datetime,message\n")

        self.file_open_flag = True
        self.log_start_time = datetime.now()
        # logger.console(f"Data Logging Started for {self.name}. "
        #                f"File names: {file_name}, {msg_file_name}")

    def close_log_file(self):
        """Check and close data file if required.

        Returns
        -------
        None.

        """

        if self.file_open_flag:
            self.log_file.close()
            # self.msg_file.close()
            self.file_open_flag = False
            # logger.console(f"Saving data stopped for {self.name}")

    def _save_data(self, data):
        """Save data object as line in data file in log file."""

        # format data into csv for saving
        data_time = (datetime.now() - self.log_start_time).total_seconds()
        formatted_data = data.get_formatted()

        # write to file
        self.log_file.write(f"{datetime.now()},{data_time},{formatted_data}\n")

        # Write to messages file
        # if len(self.messages) > self.prev_msg_len:
        #     new_content = self.node.messages[self.prev_msg_len:]
        #     for x in new_content:
        #         self.msg_file.write(f"{x}\n")
        #     self.prev_msg_len = len(self.node.messages)


class ANTWorker(QThread):

    done_signal = pyqtSignal("PyQt_PyObject")

    def __init__(self, parent, fn, *args, **kwargs):
        super().__init__(parent=parent)
        self.run_function = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        success = self.run_function(*self.args, **self.kwargs)
        self.done_signal.emit(success)


class ANTData():
    """Object to hold ANT data.

    Data will be a program-level container for storing relevant device data
    It will be updated by recieved data on any channel within the device
    and will be referenced by the main program to update visual data

    Note: data will be written to file at the channel level. Each channel
    tracked by the device will save to an independent data file for post
    analysis

    """

    _ATTRIBUTES = ["timestamp", "inst_power",
                   "avg_power", "speed", "rpm", "torque"]
    _DATA_HEADER = ",".join(_ATTRIBUTES)

    def __init__(self, data=None):
        """Init a new instance, with option to carryover previous data."""

        self.timestamp = ""
        self.prev_message = None

        if data is not None and isinstance(data, ANTData):
            self.inst_power = data.inst_power
            self.avg_power = data.avg_power
            self.speed = data.speed
            self.rpm = data.rpm
            self.torque = data.torque
            self.cadence = data.cadence

        else:
            self.inst_power = 0
            self.avg_power = 0
            self.speed = 0
            self.rpm = 0
            self.torque = 0
            self.cadence = 0

    def get_formatted(self):
        """Return comma separated list of values."""

        attributes = []

        for attr in self._ATTRIBUTES:
            value = getattr(self, attr)
            attributes.append(f"{value}")

        formatted = ",".join(attributes)
        return formatted


class FECData(ANTData):
    """Object to hold Data coming from FE-C profile ANT Devices."""

    _ATTRIBUTES = ["timestamp", "inst_power",
                   "avg_power", "speed", "rpm", "torque"]
    _DATA_HEADER = ",".join(_ATTRIBUTES)

    def __init__(self, data=None):
        """Accept message and update attributes depending on type."""
        super().__init__()
        self.timestamp = ""
        self.prev_trainer_msg = None

        if data is not None and isinstance(data, ANTData):
            self.inst_power = data.inst_power
            self.avg_power = data.avg_power
            self.speed = data.speed
            self.rpm = data.rpm
            self.torque = data.torque
        else:
            self.inst_power = 0
            self.avg_power = 0
            self.speed = 0
            self.rpm = 0
            self.torque = 0


class PWRData(ANTData):
    """Object to hold Data coming from PWR profile ANT Devices."""

    _ATTRIBUTES = ["timestamp", "inst_power",
                   "avg_power", "torque"]
    _DATA_HEADER = ",".join(_ATTRIBUTES)

    def __init__(self, data=None):
        super().__init__()

        self.timestamp = ""
        self.prev_power_msg = None
        self.prev_torque_msg = None

        if data is not None and isinstance(data, PWRData):
            self.inst_power = data.inst_power
            self.avg_power = data.avg_power
            self.torque = data.torque
        else:
            self.inst_power = 0
            self.avg_power = 0
            self.torque = 0


class SPDData(ANTData):
    """Object to hold Data coming from SPD profile ANT Devices."""

    _ATTRIBUTES = ["timestamp", "speed", "rpm"]
    _DATA_HEADER = ",".join(_ATTRIBUTES)

    def __init__(self, data=None):
        super().__init__()
        self.timestamp = ""

        if data is not None and isinstance(data, SPDData):
            self.speed = data.speed
            self.rpm = data.rpm
        else:
            self.speed = 0
            self.rpm = 0


class CDData(ANTData):
    """Object to hold Data coming from CD profile ANT Devices."""

    _ATTRIBUTES = ["timestamp", "rpm", "torque"]
    _DATA_HEADER = ",".join(_ATTRIBUTES)

    def __init__(self, data=None):
        pass


class SPDCDData(ANTData):
    """Object to hold Data coming from SPD+CD profile ANT Devices."""

    _ATTRIBUTES = ["timestamp", "speed", "rpm"]
    _DATA_HEADER = ",".join(_ATTRIBUTES)

    def __init__(self, data=None):
        self.timestamp = ""
        self.prev_message = None

        if data is not None and isinstance(data, SPDCDData):
            self.speed = data.speed
            self.rpm = data.rpm
        else:
            self.speed = 0
            self.rpm = 0
