"""
Created on Tue Mar 14 18:14:15 2023.

@author: patri
"""
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QListWidgetItem
from PyQt5 import uic
from PyQt5.QtCore import QTimer
import sys
import os
import time
from datetime import datetime
from libAnt.ANT_device import ANTWorker, ANTChannel, PWRData, FECData, SPDCDData
from PyQt5.QtCore import pyqtSlot, pyqtSignal
# from libAnt.node import Node
# from libAnt.drivers.usb import DriverException
# from libAnt.message import BroadcastMessage
# import libAnt.exceptions as e
# import libAnt.constants as c
import logging
import functools
# import libAnt.profiles.fitness_equipment_profile as p
# import libAnt.profiles.power_profile as pwr


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
        self.current_channel = None

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
        self.dev_profiles = self.ANT.dev_profiles
        # self.dev_profiles = ['HR', 'FE-C', 'PWR', '']

        # Button Connections
        self.open_search_button.clicked.connect(self.open_search_selection)
        self.close_channel_button.clicked.connect(self.close_channel)
        self.user_config_button.clicked.connect(self.send_usr_cfg)
        self.track_resistance_button.clicked.connect(
            self.send_track_resistance)

        # Demo Save Data button
        self.save_data_button.clicked.connect(self.save_data_test)

        self.status_channel_number_combo.currentIndexChanged.connect(
            self.change_selected_channel_update)

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
            self.ANT.channels = \
                [ANTChannel(i) for i in range(self.ANT.node.max_channels)]
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
        """Assignment updates to be performed on connection to a channel."""
        # Add channel to available selections to view status
        self.status_channel_number_combo.addItem(str(channel_num))
        # Make assignments based on channel information from the node
        ch = self.ANT.node.channels[channel_num]
        ANT_ch = self.ANT.channels[channel_num]
        ANT_ch.is_active = True
        ANT_ch.type = ch.status.get("channel_type")
        ANT_ch.network_number = ch.status.get("network_number")
        ANT_ch.device_type = ch.id.get("device_type")
        ANT_ch.device_number = ch.id.get("device_number")
        ANT_ch.state = ch.status.get("channel_state")
        # Set data type for the channel at connection
        match ANT_ch.device_type:
            case 11:
                ANT_ch.data = PWRData()
            case 17:
                ANT_ch.data = FECData()
            case 121:
                ANT_ch.data = SPDCDData()

        # change index to new channel

        # self.channel_field_update(ANT_ch)

    def channel_field_update(self, ANT_ch):
        """Visual updates to device fields on UI."""
        if ANT_ch is not None:
            self.channel_type_box.setText(str(ANT_ch.type))
            self.network_number_box.setText(str(ANT_ch.network_number))
            self.device_number_box.setText(str(ANT_ch.device_number))
            self.device_type_box.setText(str(ANT_ch.device_type))
            self.channel_state_box.setText(str(ANT_ch.state))

        else:
            self.channel_type_box.setText("N/A")
            self.network_number_box.setText("N/A")
            self.device_number_box.setText("N/A")
            self.device_type_box.setText("N/A")
            self.channel_state_box.setText("N/A")

    def close_channel(self):
        channel_num = int(self.status_channel_number_combo.currentText())
        close_thread = ANTWorker(self,
                                 self.ANT.close_channel,
                                 channel_num,
                                 connection=self.channel_remove)
        close_thread.start()

    def channel_remove(self, channel_num):
        if channel_num is not None:
            index = self.status_channel_number_combo.findText(str(channel_num))
            self.status_channel_number_combo.removeItem(index)
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
            channel = int(self.status_channel_number_combo.currentText())
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
            channel = int(self.status_channel_number_combo.currentText())
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
        """Visual updates to window based on update timer event callback."""
        # Check position of scroll bar
        scroll_position = self.message_viewer.verticalScrollBar().value()
        is_at_bottom = scroll_position == self.message_viewer.verticalScrollBar().maximum()

        if self.current_channel is not None:
            ch = self.current_channel
            if (len(ch.messages) > ch.prev_msg_len):
                new_content = \
                    ch.messages[ch.prev_msg_len:]
                for x in new_content:
                    self.message_viewer.append(x)
                ch.prev_msg_len = len(ch.messages)

        else:
            if (len(self.ANT.messages) > self.ANT.prev_msg_len):
                new_content = self.ANT.messages[self.ANT.prev_msg_len:]
                for x in new_content:
                    self.message_viewer.append(x)
                self.ANT.prev_msg_len = len(self.ANT.messages)

        if not is_at_bottom:
            self.message_viewer.verticalScrollBar().setValue(scroll_position)

        self.power_box.setText(f"{self.ANT.data.inst_power:.1f}")
        self.speed_box.setText(f"{self.ANT.data.speed:.1f}")
        self.avg_power_box.setText(f"{self.ANT.data.avg_power:.1f}")
        self.event_box.setText(f"{self.ANT.event_count:.0f}")

    def change_selected_channel_update(self):
        """Visual updates to window when selected channel is changed."""
        # Read new value from channel combo box
        try:
            current_channel_num = int(
                self.status_channel_number_combo.currentText())
        # Case if blank ('') value is read indicating no channel
        except ValueError:
            self.current_channel = None
        else:
            self.current_channel = self.ANT.channels[current_channel_num]
        # Clear Previous Messages
        self.message_viewer.clear()

        if self.current_channel is not None:
            # Updates to device fields
            self.channel_field_update(self.current_channel)

            # Updates to message viewer
            # Structure message contents
            bulk_append_msgs = "\n".join(self.current_channel.messages)
            self.message_viewer.setPlainText(bulk_append_msgs)

        else:
            # Updates to device fields
            self.channel_field_update(None)
            # Updates to message viewer
            # Structure message contents
            bulk_append_msgs = "\n".join(self.ANT.messages)
            self.message_viewer.setPlainText(bulk_append_msgs)

    def save_data_test(self):
        """Test function to demo save features of multichannel ANT handling."""

        print("Do we get into the save method?")
        # Check to see if files are currently open
        if any([channel.log_data_flag for channel in self.ANT.channels]):
            print("Do we get into the close channel?")
            for channel in self.ANT.channels:
                if channel.is_active:
                    channel.close_log_file()
            return

        # otherwise generate a new data log
        else:
            print("Do we get into the save init?")
            save_location = r"C:\homologationTemp"
            timestamp_str = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
            test_name = "ANT_multichannel_save_test"
            save_folder_dir = \
                os.path.join(save_location, f"{timestamp_str}-{test_name}")
            os.mkdir(save_folder_dir)

            for channel in self.ANT.channels:
                if channel.is_active:
                    channel.log_name = "Test_Log"
                    channel.log_path = save_folder_dir
                    channel.log_data_flag = True

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
