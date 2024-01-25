# -*- coding: utf-8 -*-
"""
Created on Tue Mar 14 18:14:15 2023

@author: patri
"""
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QListWidgetItem
from PyQt5 import uic
from PyQt5.QtCore import QTimer
import sys
import os
import time
import math
from datetime import datetime
from PyQt5.QtCore import pyqtSlot, pyqtSignal, QObject, QThread
from libAnt.node import Node
from libAnt.drivers.usb import DriverException
import libAnt.exceptions as e
import logging
import functools
import libAnt.profiles.fitness_equipment_profile as p


class ANTDevice(QObject):
    """Interface with ANTUSB stick to communicate with other ANT devies.

    An "ANT Device" will primarily refer to an FE-C enabled trainer. However
    It will eventually encapsulate all data streams coming from the device
    in question
    """

    connection_signal = pyqtSignal(bool)
    success_signal = pyqtSignal('PyQt_PyObject')
    failure_signal = pyqtSignal('PyQt_PyObject')
    tx_success = pyqtSignal('PyQt_PyObject')

    def __init__(self, debug=False):
        super().__init__()
        self.node = None
        self.connected = False

        # Attributes used for writing sensor data to file
        self.log_file = None
        self.file_open_flag = False
        self.log_data_flag = False
        self.log_path = ""
        self.log_name = ""
        self.name = "trainer"
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

        def success_handler(msg):
            if hasattr(msg, 'build'):
                # If the message has a build method we know it's a broadcast
                # message

                # Extract power information from trainer specific data page
                if int(msg.content[0]) == 0x19:
                    trainer_msg = p.TrainerDataPage(msg, self.trainer_msgs[-1])
                    self.trainer_msgs.append(trainer_msg)
                    self.data.inst_power = trainer_msg.inst_power
                    self.data.avg_power = trainer_msg.avg_power
                    self.event_count = trainer_msg.event
                    try:
                        self.data.torque = (
                            self.data.avg_power
                            / (self.data.rpm / 60 * 2 * math.pi))
                    except ZeroDivisionError:
                        self.data.torque = 0

                    timestamp = trainer_msg.timestamp

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
                    timestamp = FE_msg.timestamp

                else:
                    timestamp = datetime.now()

                self.data.timestamp = timestamp
                self.datas.append(self.data)

                # Creates a new ANTData object, pre-populated with prev data
                self.data = ANTData(self.data)

                if self.log_data_flag:
                    self._save_data(self.data)

            self.add_message(msg)

        def fail_handler(msg):
            self.add_message(msg)
            # if isinstance(msg, RxSearchTimeout):
            #     if self.connected:
            #         # self.close_channel(connection_timeout=True)
            #         logger.warning("ANT+ Trainer Connection Timeout. "
            #                        "Disconnecting Device")
            #     else:
            #         # self.close_channel(search_timeout=True)
            #         logger.console("ANT+ Trainer Search Timeout. "
            #                        "No Device Avaliable")
            #     pass

            # if isinstance(msg, DriverException):
            #     self.clear_device()

        self.success_signal.connect(success_handler)
        self.failure_signal.connect(fail_handler)

        # Define avaliable Device Profiles
        self.dev_profiles = ['FE-C', 'PWR', 'SPD', 'CD', 'SPD+CD', 'HR']
        self.init_node(debug=debug)

    def add_message(self, msg):
        """Add message to node message array or respective channel"""

        if hasattr(msg, "channel"):
            channel = msg.channel
        else:
            channel = None
        msg = str(msg)
        self.node.add_msg(msg, channel)

    def init_node(self, debug=False):
        # May need to try this a few times
        fail_count = 0
        while fail_count < 3:
            try:
                self.node = Node(debug=debug)
            except DriverException as e:
                if fail_count == 2:
                    print(e)

                fail_count += 1
            else:
                return

    @pyqtSlot()
    def callback(self, msg):
        self.success_signal.emit(msg)

    @pyqtSlot()
    def error_callback(self, emsg):
        self.failure_signal.emit(emsg)

    def set_track_resistance(self, channel, **kwargs):
        """Create and send a track resistance page to the device.

        Parameters
        ----------
        channel: int
            Number of channel the tx message should be sent on

        Returns
        -------
        None.

        """

        self.grade = kwargs.get("grade")
        grade = p.set_grade(channel, **kwargs)
        self.send_tx_msg(grade)
        self.node.add_msg(f"Track Resistance Command Sent: {kwargs}", channel)

    def set_config(self, channel, **kwargs):
        """Create and send a user config page to the device.

        Parameters
        ----------
        channel: int
            Number of channel the tx message should be sent on

        Returns
        -------
        None.
        """
        cfg = p.set_user_config(channel, **kwargs)
        self.send_tx_msg(cfg)
        self.node.add_msg(f"User Config Command Sent: {kwargs}", channel)

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


class ANTWindow(QMainWindow):

    def __init__(self, ANT_device):
        # Load UI elements
        self.program_start_time = datetime.now()

        # Initialize superclass
        QMainWindow.__init__(self)
        # Load the graphical layout
        path = os.path.join(os.getcwd(), "libAnt", "GUI", "ant_UI.ui")
        self.UI_elements = uic.loadUi(path, self)
        self.ANT = ANT_device
        self.search_window = None
        self.prev_msg_len = 0

        self.update_timer = QTimer()
        self.update_timer.setInterval(250)
        self.update_timer.timeout.connect(self.periodic_ANT_update)

        # Initialze Search window and slot connections
        self.search_window = ANTSelector(self.ANT)
        self.search_window.selected_signal.connect(self.channel_startup)
        self.search_window.search_signal.connect(self.device_channel_search)

        # def success_handler(msg):
        #     """this function is sent to the node as instructurion how to
        #     handle a successful event"""

        #     if hasattr(msg, 'build'):
        #         # If the message has a build method we know it's a broadcast
        #         # message

        #         # Extract power information from trainer specific data page
        #         if int(msg.content[0]) == 0x19:
        #             trainer_msg = p.TrainerDataPage(msg, self.trainer_msgs[-1])
        #             self.trainer_msgs.append(trainer_msg)
        #             self.data.inst_power = trainer_msg.inst_power
        #             self.data.avg_power = trainer_msg.avg_power
        #             self.event_count = trainer_msg.event
        #             try:
        #                 self.data.torque = (
        #                     self.data.avg_power
        #                     / (self.data.rpm / 60 * 2 * math.pi))
        #             except ZeroDivisionError:
        #                 self.data.torque = 0

        #             timestamp = trainer_msg.timestamp

        #         # Extract speed info from general FE data page
        #         elif int(msg.content[0]) == 0x10:
        #             FE_msg = p.GeneralFEDataPage(msg)
        #             speed_kph = FE_msg.speed * 3600 / 10**6
        #             self.data.speed = speed_kph
        #             rpm = speed_kph * 1000 / 60 / \
        #                 (math.pi * ANT().wheel_diameter)
        #             self.data.rpm = rpm
        #             try:
        #                 self.data.torque = (self.data.avg_power
        #                                     / (rpm / 60 * 2 * math.pi))
        #             except ZeroDivisionError:
        #                 self.data.torque = 0
        #             timestamp = FE_msg.timestamp

        #         else:
        #             timestamp = datetime.now()

        #         self.data.timestamp = timestamp
        #         self.datas.append(self.data)

        #         # Creates a new ANTData object, pre-populated with prev data
        #         self.data = ANTData(self.data)

        #         if self.log_data_flag:
        #             self._save_data(self.data)

        #     msg = str(msg)
        #     self.node.add_msg(msg)

        # Define Signal/Slot Relationship for emitting success and failure

        # class HandlerObject(QObject):
        #     success_signal = pyqtSignal('PyQt_PyObject')
        #     failure_signal = pyqtSignal('PyQt_PyObject')

        #     def __init__(self):
        #         super().__init__()

        #     def callback(self, msg):
        #         self.success_signal.emit(msg)

        #     def error_callback(self, emsg):
        #         self.failure_signal.emit(emsg)

        # self.obj = HandlerObject()
        # self.prev_trainer_msg = None

        # def signal_handler(msg):
        #     if hasattr(msg, 'build') and int(msg.content[0]) == 0x19:
        #         trainer_msg = p.TrainerDataPage(msg, self.prev_trainer_msg)
        #         self.trainer_msgs.append(trainer_msg)
        #         self.power_box.setText(str(trainer_msg.inst_power))
        #         self.event_box.setText(str(trainer_msg.event))
        #         self.avg_power_box.setText(str(trainer_msg.avg_power))
        #         self.prev_trainer_msg = trainer_msg

        #     if hasattr(msg, 'channel'):
        #         channel = msg.channel

        #     else:
        #         channel = None

        #     msg = str(msg)
        #     self.node.add_msg(msg, channel_num=channel)
        #     # self.message_viewer.append(msg)

#         self.obj.success_signal.connect(signal_handler)
#         self.obj.failure_signal.connect(signal_handler)
        # Define avaliable Device Profiles
        self.dev_profiles = ['FE-C', 'PWR', 'HR', '']
        # self.dev_profiles = ['HR', 'FE-C', 'PWR', '']

        # Button Connections
        self.open_search_button.clicked.connect(self.open_search_selection)
        self.close_channel_button.clicked.connect(self.close_channel)
        self.user_config_button.clicked.connect(self.send_usr_cfg)
        self.track_resistance_button.clicked.connect(
            self.send_track_resistance)

    # def check_success(self, success):
    #     if success:
    #         print("Operation Success!")

    #     else:
    #         print("Operation Failed!")

    def closeEvent(self, event):
        # Close and terminate ANT Node
        if self.ANT.node is not None:
            end_thread = ANTWorker(self, self.ANT.node.stop)
            end_thread.start()
            end_thread.finished.connect(
                lambda: QTimer.singleShot(0, self.close_application))
        else:
            QTimer.singleShot(100, self.close_application)

        # Close search selector if visible
        if self.search_window is not None and self.search_window.isVisible():
            self.search_window.close()

        self.update_timer.stop()

        # Remove Package Additions to Path
        sys.path.pop(0)
        event.accept()

    def close_application(self):
        """Remove handlers from root logger on close."""
        QApplication.quit()
        logging.getLogger().root.handlers.clear()

    def showEvent(self, event):
        if self.ANT.node is not None and not self.ANT.node.isRunning():
            start_thread = ANTWorker(self,
                                     self.ANT.node.start,
                                     self.ANT.callback,
                                     self.ANT.error_callback)
            start_thread.done_signal.connect(self.device_startup)
            start_thread.done_signal.connect(self.open_search_selection)
            start_thread.start()

        self.update_timer.start()
        event.accept()

    def open_search_selection(self):
        """Open UI and start channel search function for ANT devices.

        Method opens all available channels on Node and waits for successful
        connection to any ANT devices in proximity
        """

        # Generate a new session of ANT selector window
        # self.search_window = ANTSelector(self.ANT)
        profile = self.channel_profile_combo.currentText()
        if profile == '':
            profile = None
        device_number = self.device_ID_field.text()
        if device_number == '':
            device_number = 0
        print(f"Device number from open_search_selector: {device_number}")
        self.search_window.open_search_mode(profile=profile,
                                            device_number=device_number)

    def device_startup(self, success):
        if success:
            self.name_box.setText(
                str(self.ANT.node._pump._driver._dev._product))
            self.serial_number_box.setText(str(self.ANT.node.serial_number))
            self.max_channels_box.setText(str(self.ANT.node.max_channels))
            self.max_networks_box.setText(str(self.ANT.node.max_networks))
            self.channel_profile_combo.addItems(self.dev_profiles)
        else:
            self.message_viewer.append("Error in Device Startup! "
                                       "Relaunch Program to try again")

    def device_channel_search(self, channel_num):
        """Search for channels with same device number as current connection.

        Only will search for other channels if current device is type FE-C .
        Use of the connect keyword will automatically connect to successful
        pairings.

        Parameters
        ----------
        channel_num : TYPE
            DESCRIPTION.

        Returns
        -------
        None.

        """
        channel = self.ANT.node.channels[channel_num]
        # Return if device is anything other than FE-C channel
        print(
            f"This is where we'd connect to other stuff! on channel {channel_num}")

        if not channel.device_type == 17:
            return

        # Verify parameters
        print("------ Device Channel Search Params ------")
        print(f"Channel Adress: {channel}")
        print(f"Channel number: {channel.number}")
        print(f"Device Number: {channel.device_number}")
        profiles = ['PWR', 'SPD', 'CD', 'SPD+CD']
        self.search_window.open_search_mode(
            device_number=channel.device_number,
            profiles=profiles,
            show=False,
            connect=True)

    def channel_startup(self, channel_num):
        self.status_ch_number_combo.addItem(str(channel_num))
        ch = self.ANT.node.channels[channel_num]
        self.channel_type_box.setText(str(ch.status.get("channel_type")))
        self.network_number_box.setText(
            str(ch.status.get("network_number")))
        self.device_id_box.setText(str(ch.id.get("device_number")))
        device_type = ch.id.get("device_type")
        self.device_type_box.setText(str(device_type))
        if device_type == 17:
            self.ANT.FE_C_channel = channel_num
        self.channel_state_box.setText(str(ch.status.get("channel_state")))

    def close_channel(self):
        channel_num = int(self.status_ch_number_combo.currentText())
        close_thread = ANTWorker(self,
                                 self.ANT.close_channel,
                                 channel_num,
                                 connection=self.channel_remove)
        close_thread.start()

    def channel_remove(self, channel_num):
        if channel_num is not None:
            index = self.status_ch_number_combo.findText(str(channel_num))
            self.status_ch_number_combo.removeItem(index)
            self.channel_type_box.clear()
            self.network_number_box.clear()
            self.device_id_box.clear()
            self.device_type_box.clear()
            self.channel_state_box.clear()
        else:
            self.message_viewer.append("Error in Channel Close! "
                                       "Check Parameters and try again")

    def send_usr_cfg(self):
        cfg_boxes = [self.rider_weight_box, self.wheel_offset_box,
                     self.bike_weight_box, self.wheel_diameter_box,
                     self.gear_ratio_box]
        cfg_keys = ['user_weight', 'wheel_diameter_offset', 'bike_weight',
                    'bike_wheel_diameter', 'gear_ratio']
        cfg_dict = {}
        for i, box in enumerate(cfg_boxes):
            try:
                usr_in = int(box.text())
            except ValueError:
                pass
            else:
                cfg_dict[cfg_keys[i]] = usr_in

        try:
            channel = int(self.status_ch_number_combo.currentText())
        except ValueError:
            self.message_viewer.append('Error: Channel must be selected to '
                                       'send user configuration message!')
            return

        self.ANT.set_config(channel, **cfg_dict)

    def send_track_resistance(self):
        grade_boxes = [self.grade_box, self.crr_box]
        grade_keys = ['grade', 'wheel_diameter_offset', 'bike_weight',
                      'bike_wheel_diameter', 'gear_ratio']
        grade_dict = {}
        for i, box in enumerate(grade_boxes):
            try:
                usr_in = int(box.text())
            except ValueError:
                pass
            else:
                grade_dict[grade_keys[i]] = usr_in

        try:
            channel = int(self.status_ch_number_combo.currentText())
        except ValueError:
            self.message_viewer.append('Error: Channel must be selected to '
                                       'send user configuration message!')

        self.ANT.set_track_resistance(channel, **grade_dict)

    # def send_tx_msg(self, msg):
    #     tx_thread = ANTWorker(self,
    #                           self.node.send_tx_msg,
    #                           msg)
    #     tx_thread.done_signal.connect(functools.partial(self.tx_msg_status,
    #                                                     msg))
    #     tx_thread.start()

    def tx_msg_status(self, success, msg):
        if success:
            pass
        else:
            self.send_tx_msg(msg)

    def periodic_ANT_update(self):

        if (self.ANT.node is not None
                and len(self.ANT.node.messages) > self.prev_msg_len):
            new_content = self.ANT.node.messages[self.prev_msg_len:]
            for x in new_content:
                self.message_viewer.append(x)
            self.prev_msg_len = len(self.ANT.node.messages)

        self.power_box.setText(f"{self.ANT.data.inst_power:.1f}")
        self.speed_box.setText(f"{self.ANT.data.speed:.1f}")
        self.avg_power_box.setText(f"{self.ANT.data.avg_power:.1f}")
        self.event_box.setText(f"{self.ANT.event_count:.0f}")

    @pyqtSlot()
    def returnPressedSlot():
        """Pyqt decorator."""
        pass

    @pyqtSlot()
    def writeDocSlot():
        """Pyqt decorator."""
        pass

    @pyqtSlot()
    def browseSlot(self):
        """Pyqt decorator."""
        pass


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


class ANTSelector(QWidget):
    """Create window for viewing available ANT devices for connection to
       select the desired one for connection
    """
    selected_signal = pyqtSignal(int)
    search_signal = pyqtSignal(int)

    def __init__(self, ANT):

        self.start_time = datetime.now()
        self.ANT = ANT

        # Initialize superclass
        super(QWidget, self).__init__()
        # Load the graphical layout
        path = "libAnt/GUI/ant_selection.ui"
        self.UI_elements = uic.loadUi(path, self)

        # Button Connections
        self.select_device_button.clicked.connect(self.select_device)
        self.cancel_selection_button.clicked.connect(self.cancel)
        # self.update_timer = QTimer()
        # self.update_timer.timeout.connect(self.update)
        # self.update_timer.internal_timer.stop()

    def update(self):
        # TODO: Update method to refresh available devices on the GUI

        pass

    def select_device(self):
        # Specify the channel of the device the user wants to connect to
        dev_channel = self.available_devices_list.currentItem().data

        # Close the other channels
        # TODO: This may cause issues if trying to close in search mode. Will
        # need to verify with queue sequence
        for channel in self.ANT.node.channels:
            if (channel is not None
                and channel.number != dev_channel.number
                    and not channel.closing):
                close_thread = ANTWorker(self, channel.close)
                close_thread.done_signal.connect(self.ANT.node.clear_channel)
                close_thread.start()

        # TODO: On the last close thread, if device is FE-C open search mode to
        # connect to other channels with same device number
        close_thread.done_signal.connect(
            lambda: self.emit_connection_channel(dev_channel.number))
        # Emit selected device channel to main program
        self.selected_signal.emit(dev_channel.number)
        self.close()

    def emit_connection_channel(self, channel_num):
        """emit signal for main program to look for additional connections.
        """
        self.search_signal.emit(channel_num)

    def cancel(self):
        print("Device Selection Cancelled!")
        for channel in self.ANT.node.channels:
            if (channel is not None) and not (channel.closing):
                channel_close_thread = ANTWorker(self, channel.close)
                channel_close_thread.done_signal.connect(
                    self.ANT.node.clear_channel)
                channel_close_thread.start()
        self.available_devices_list.clear()
        self.close()
        pass

    def showEvent(self, event):
        # Open all available channels on the node
        event.accept()
        pass

    def open_search_mode(self, profile=None,
                         profiles=None,
                         device_number=0,
                         show=True,
                         connect=False):
        """
        Initiates device search and displays avaialbe connections on pop-up.

        Parameters
        ----------
        profile : str, optional
            The desired device profile of the search opearation. The node will
            search for all availiable devices of this profile.
        device_ID : int, optional
            The desired device ID for search opearation. The program will
            search for to all available channels with this device ID.

        Returns
        -------
        None.

        """
        i_profile = 0
        # Open all available channels on the node
        for i in range(self.ANT.node.max_channels):
            # Only attempt a connection if not already initialized
            # print(f"Device Number From Open Search mode: {device_number}")
            if self.ANT.node.channels[i] is None:
                if (profiles is not None):
                    if (len(profiles) > i_profile):
                        profile = profiles[i_profile]
                        i_profile += 1
                    else:
                        continue
                open_thread = ANTWorker(self,
                                        self.ANT.node.open_channel,
                                        i,
                                        profile=profile,
                                        device_number=device_number)
                # Connect open to waiter function for device connection
                open_thread.done_signal.connect(
                    functools.partial(self.wait_for_device_connection,
                                      connect=connect))
                open_thread.start()

        if show:
            # Show selector GUI window
            self.show()

    def wait_for_device_connection(self, channel_num, connect=False):
        """Wait for a device connection after opening a channel

        Slot for open_thread done_signal, which will provide a status and 
        channel number of successful channel open event

        Parameters
        ----------
        channel_num : int
            number of channel on node that the waiter thread will track.

        Returns
        -------
        None.

        """
        print("Beginning of wait for device connection")
        # Initailize the waiter thread
        wait_thread = ANTWorker(self, self.wait_for_device_ID,
                                self.ANT.node.channels[channel_num])
        # Connect the event handler to the completion of the waiting period.
        # the search will either timeout or add a successful connection
        wait_thread.done_signal.connect(
            functools.partial(self.handle_pairing_event,
                              channel_num,
                              connect=connect))
        wait_thread.start()
        # print(f"End of wait for device connection on channel: {channel_num}")

    def wait_for_device_ID(self, channel):
        print(f"Beginning of wait method on channel: {channel}.")
        # Channels are thread objects and can be monitored. If search times out
        # the thread will terminate
        while channel.is_alive():
            # Monitor if the status attribute has been updated, indicating a
            # successful connection handshake
            if channel.status is not None:
                return channel
            time.sleep(0.1)
        self.ANT.node.clear_channel(channel.number)
        # print("End of wait for device ID!")

    def handle_pairing_event(self, channel_num, channel, connect=False):

        print("--------------In pairing event Handler----------------")
        print(f"Channel Number: {channel_num}, Channel Object: {channel}")

        if channel is not None:

            # if connect kwarg is true, automatically select device to connect
            if connect:
                self.selected_signal.emit(channel.number)

            # Add successful channel pairing to device field
            else:
                self.available_devices_list.addItem(ANTListItem(channel))

        else:
            pass
            # print("Unsuccessful pairing!")

    def closeEvent(self, event):
        # self.cancel()
        event.accept()
        pass


class ANTListItem(QListWidgetItem):
    def __init__(self, channel_object):
        self.channel = channel_object
        self.profile_dict = {11: "PWR", 17: "FE-C", 120: "HR", 121: "SPD+CD",
                             122: "CD", 123: "SPD"}
        device_number = self.channel.id["device_number"]
        profile = self.profile_dict[self.channel.id["device_type"]]
        self.label = f"{profile} {device_number}"
        super(ANTListItem, self).__init__(self.label)
        self.data = channel_object


class ANTData():
    """Object to hold ANT data."""

    _ATTRIBUTES = ["timestamp", "inst_power",
                   "avg_power", "speed", "rpm", "torque"]
    _DATA_HEADER = ",".join(_ATTRIBUTES)

    def __init__(self, data=None):
        """Init a new instance, with option to carryover previous data."""

        self.timestamp = ""

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

    def get_formatted(self):
        """Return comma separated list of values."""

        attributes = []

        for attr in self._ATTRIBUTES:
            value = getattr(self, attr)
            attributes.append(f"{value}")

        formatted = ",".join(attributes)
        return formatted
