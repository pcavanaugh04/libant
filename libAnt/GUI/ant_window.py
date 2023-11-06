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
from datetime import datetime
from PyQt5.QtCore import pyqtSlot, pyqtSignal, QObject, QThread
from libAnt.node import Node
from libAnt.drivers.usb import DriverException
import libAnt.exceptions as e
import logging
import functools
import libAnt.profiles.fitness_equipment_profile as p


class ANTWindow(QMainWindow):

    def __init__(self):
        # Load UI elements
        self.program_start_time = datetime.now()

        # Initialize superclass
        QMainWindow.__init__(self)
        # Load the graphical layout
        path = os.path.join(os.getcwd(), "libAnt", "GUI", "ant_UI.ui")
        self.UI_elements = uic.loadUi(path, self)
        self.node = None
        self.search_window = None
        # Define Signal/Slot Relationship for emitting success and failure

        class HandlerObject(QObject):
            success_signal = pyqtSignal('PyQt_PyObject')
            failure_signal = pyqtSignal('PyQt_PyObject')

            def __init__(self):
                super().__init__()

            def callback(self, msg):
                self.success_signal.emit(msg)

            def error_callback(self, emsg):
                self.failure_signal.emit(emsg)

        self.obj = HandlerObject()
        self.trainer_msgs = [None]

        def signal_handler(msg):
            if hasattr(msg, 'build') and int(msg.content[0]) == 0x19:
                trainer_msg = p.TrainerDataPage(msg, self.trainer_msgs[-1])
                self.trainer_msgs.append(trainer_msg)
                self.power_box.setText(str(trainer_msg.inst_power))
                self.event_box.setText(str(trainer_msg.event))
                self.avg_power_box.setText(str(trainer_msg.avg_power))

            msg = str(msg)

            # if "ready to clear channel" in msg:
            #     self.node.clear_channel(int(msg[-1]), timeout=True)

            self.node.messages.append(msg)
            self.message_viewer.append(msg)

        self.obj.success_signal.connect(signal_handler)
        self.obj.failure_signal.connect(signal_handler)
        # Define avaliable Device Profiles
        # self.dev_profiles = ['FE-C', 'PWR', 'HR', '']
        self.dev_profiles = ['HR', 'FE-C', 'PWR', '']

        # Button Connections
        self.open_search_button.clicked.connect(self.open_search_selection)
        self.close_channel_button.clicked.connect(self.close_channel)
        self.user_config_button.clicked.connect(self.send_usr_cfg)
        self.track_resistance_button.clicked.connect(self.send_grade_msg)

        # Signal Connections
        self.init_node(debug=True)

    def init_node(self, debug=False):
        try:
            self.node = Node(debug=debug)
        except DriverException as e:
            print(e)
            return

    def check_success(self, success):
        if success:
            print("Operation Success!")

        else:
            print("Operation Failed!")

    def closeEvent(self, event):
        # Close and terminate ANT Node
        if self.node is not None:
            end_thread = ANTWorker(self, self.node.stop)
            end_thread.start()
            end_thread.finished.connect(
                lambda: QTimer.singleShot(0, self.close_application))
        else:
            QTimer.singleShot(100, self.close_application)

        # Close search selector if visible
        if self.search_window is not None and self.search_window.isVisible():
            self.search_window.close()

        # Remove Package Additions to Path
        sys.path.pop(0)
        event.accept()

    def close_application(self):
        """Remove handlers from root logger on close."""
        QApplication.quit()
        logging.getLogger().root.handlers.clear()

    def showEvent(self, event):
        if self.node is not None and not self.node.isRunning():
            start_thread = ANTWorker(self,
                                     self.node.start,
                                     self.obj.callback,
                                     self.obj.error_callback)
            start_thread.done_signal.connect(self.device_startup)
            start_thread.done_signal.connect(self.open_search_selection)
            start_thread.start()

        event.accept()

    def open_search_selection(self):
        """Open UI and start channel search function for ANT devices.

        Method opens all available channels on Node and waits for successful
        connection to any ANT devices in proximity
        """

        # Generate a new session of ANT selector window
        self.search_window = ANTSelector(self.node)
        profile = self.channel_profile_combo.currentText()
        if profile == '':
            profile = None
        device_number = self.device_ID_field.text()
        if device_number == '':
            device_number = None
        self.search_window.open_search_mode(profile=profile,
                                            device_number=device_number)
        self.search_window.selected_signal.connect(self.channel_startup)

    # def open_channel(self, channel=0, profile='FE-C'):
    #     self.open_thread = ANTWorker(self,
    #                                  self.node.open_channel,
    #                                  channel,
    #                                  profile=profile)

        # TODO: go to node level connection method to make sure it can handle 7 requests at once
        # 31 oct 2023 Goal - Dive into the node spot
        # TODO: Need an intermediate connection step to indicate a successful handshake
        # self.open_thread.done_signal.connect(self.set_connection_status)
        # self.open_thread.done_signal.connect(
        #     functools.partial(self.set_config, channel))
        # self.open_thread.start()

        # Depreciated open channel method
        #     self.channel_add_num = int(self.channel_number_combo.currentText())
        #     channel_profile = str(self.channel_profile_combo.currentText())
        #     # self.thread_parent = QObject()
        #     open_thread = ANTWorker(self,
        #                             self.node.open_channel,
        #                             self.channel_add_num,
        #                             profile=channel_profile)
        #     open_thread.done_signal.connect(self.channel_startup)
        #     open_thread.start()

    def device_startup(self, success):
        if success:
            # print(self.node._pump._driver._dev._product)
            self.name_box.setText(str(self.node._pump._driver._dev._product))
            self.serial_number_box.setText(str(self.node.serial_number))
            self.max_channels_box.setText(str(self.node.max_channels))
            self.max_networks_box.setText(str(self.node.max_networks))
            # ch_list = [str(i) for i in range(self.node.max_channels)]
            # self.channel_number_combo.addItems(ch_list)
            self.channel_profile_combo.addItems(self.dev_profiles)
        else:
            self.message_viewer.append("Error in Device Startup! "
                                       "Relaunch Program to try again")

    def channel_startup(self, channel_num):
        self.status_ch_number_combo.addItem(str(channel_num))
        ch = self.node.channels[channel_num]
        self.channel_type_box.setText(str(ch.status.get("channel_type")))
        self.network_number_box.setText(
            str(ch.status.get("network_number")))
        self.device_id_box.setText(str(ch.id.get("device_number")))
        self.device_type_box.setText(str(ch.id.get("device_type")))
        self.channel_state_box.setText(str(ch.status.get("channel_state")))

    def close_channel(self):
        channel_num = int(self.status_ch_number_combo.currentText())
        self.combo_remove_index = self.status_ch_number_combo.currentIndex()
        close_thread = ANTWorker(self,
                                 self.node.close_channel,
                                 channel_num)
        close_thread.done_signal.connect(self.channel_remove)
        close_thread.start()

    def channel_remove(self, success):
        if success:
            self.status_ch_number_combo.removeItem(self.combo_remove_index)
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

        cfg = p.set_user_config(channel, **cfg_dict)
        self.send_tx_msg(cfg)

    def send_grade_msg(self):
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
            return

        grade = p.set_grade(channel, **grade_dict)
        self.send_tx_msg(grade)

    def send_tx_msg(self, msg):
        tx_thread = ANTWorker(self,
                              self.node.send_tx_msg,
                              msg)
        tx_thread.done_signal.connect(functools.partial(self.tx_msg_status,
                                                        msg))
        tx_thread.start()

    def tx_msg_status(self, success, msg):
        if success:
            pass
        else:
            self.send_tx_msg(msg)

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

    def __init__(self, node):

        self.start_time = datetime.now()
        self.node = node

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
        device_channel = self.available_devices_list.currentItem().data

        # Close the other channels
        # TODO: This may cause issues if trying to close in search mode. Will
        # need to verify with queue sequence
        for channel in self.node.channels:
            if channel is not None and channel.number != device_channel.number:
                close_thread = ANTWorker(self, channel.close)
                close_thread.done_signal.connect(self.node.clear_channel)
                close_thread.start()

        # Emit selected device channel to main program
        self.selected_signal.emit(device_channel.number)
        self.close()

    def cancel(self):
        print("Device Selection Cancelled!")
        for channel in self.node.channels:
            if channel is not None:
                channel_close_thread = ANTWorker(self, channel.close)
                channel_close_thread.done_signal.connect(
                    self.node.clear_channel)
                channel_close_thread.start()
        self.close()
        pass

    def showEvent(self, event):
        # Open all available channels on the node
        event.accept()
        pass

    def open_search_mode(self, profile=None, device_number=None):
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

        # Open all available channels on the node
        for i in range(self.node.max_channels):
            # Only attempt a connection if not already initialized
            if self.node.channels[i] is None:
                open_thread = ANTWorker(self,
                                        self.node.open_channel,
                                        i,
                                        profile=profile,
                                        device_number=device_number)
                # Connect open to waiter function for device connection
                open_thread.done_signal.connect(
                    self.wait_for_device_connection)
                open_thread.start()
        # Show selector GUI window
        self.show()

    def wait_for_device_connection(self, channel_num):
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
        # Initailize the waiter thread
        wait_thread = ANTWorker(self, self.wait_for_device_ID,
                                self.node.channels[channel_num])
        # Connect the event handler to the completion of the waiting period.
        # the search will either timeout or add a successful connection
        wait_thread.done_signal.connect(
            functools.partial(self.handle_pairing_event, channel_num))
        wait_thread.start()
        # print(f"End of wait for device connection on channel: {channel_num}")

    def wait_for_device_ID(self, channel):
        print(f"Beginning of wait method on channel: {channel}.")
        # Channels are thread objects and can be monitored. If search times out
        # the thread will terminate
        while channel.is_alive():
            # Monitor if the ID attribute has been updated, indicating a
            # successful connection handshake
            if channel.id is not None:
                return channel
            time.sleep(0.1)
        self.node.clear_channel(channel.number)
        # print("End of wait for device ID!")

    def handle_pairing_event(self, channel_num, channel):

        print("--------------In pairing event Handler----------------")
        print(f"Channel Number: {channel_num}, Channel Object: {channel}")
        if channel is not None:
            # Add successful channel pairing to device field
            # self.available_devices_list.addItem(
            #     f"{channel.id['device_number']}",
            #     userData=channel)
            # TODO: Look for a way to tie labels and object to one field
            self.available_devices_list.addItem(ANTListItem(channel))

        else:
            pass
            # print("Unsuccessful pairing!")

    def closeEvent(self, event):
        event.accept()
        pass


class ANTListItem(QListWidgetItem):
    def __init__(self, channel_object):
        self.channel = channel_object
        self.profile_dict = {0: "PWR", 17: "FE-C", 120: "HR"}
        device_number = self.channel.id["device_number"]
        profile = self.profile_dict[self.channel.id["device_type"]]
        self.label = f"{profile} {device_number}"
        super(ANTListItem, self).__init__(self.label)
        self.data = channel_object
