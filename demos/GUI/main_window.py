# -*- coding: utf-8 -*-
"""
Created on Tue Mar 14 18:14:15 2023

@author: patri
"""
from PyQt5.QtWidgets import QMainWindow
from PyQt5 import uic
import os
from datetime import datetime
from PyQt5.QtCore import pyqtSlot, pyqtSignal, QObject, QThread
from libAnt.node import Node
from libAnt.drivers.usb import USBDriver, DriverException


class MainWindow(QMainWindow):

    def __init__(self):
        # %% Load UI elements
        self.program_start_time = datetime.now()

        try:
            self.node = Node(USBDriver(vid=0x0FCF, pid=0x1008), debug=False)
        except DriverException as e:
            print(e)
            return

        # Initialize superclass
        QMainWindow.__init__(self)
        # Load the graphical layout
        path = os.path.join(os.getcwd(), "GUI", "ant_UI.ui")
        self.UI_elements = uic.loadUi(path, self)

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

        def signal_handler(msg):
            msg = str(msg)
            self.node.messages.append(msg)
            self.message_viewer.append(msg)

        self.obj.success_signal.connect(signal_handler)
        self.obj.failure_signal.connect(signal_handler)
        # Define avaliable Device Profiles
        self.dev_profiles = ['FE-C', 'PWR', 'HR']
        # Button Connections
        self.open_channel_button.clicked.connect(self.open_channel)
        self.close_channel_button.clicked.connect(self.close_channel)

    def check_success(self, success):
        if success:
            print("Operation Success!")

        else:
            print("Operation Failed!")

    def closeEvent(self, event):
        self.node.stop()
        event.accept()

    def showEvent(self, event):
        start_thread = ANTWorker(self,
                                 self.node.start,
                                 self.obj.callback,
                                 self.obj.error_callback)
        start_thread.done_signal.connect(self.device_startup)
        start_thread.start()
        event.accept()

    def open_channel(self):
        self.channel_add_num = int(self.channel_number_combo.currentText())
        channel_profile = str(self.channel_profile_combo.currentText())
        # self.thread_parent = QObject()
        open_thread = ANTWorker(self,
                                self.node.open_channel,
                                self.channel_add_num,
                                profile=channel_profile)
        open_thread.done_signal.connect(self.channel_startup)
        open_thread.start()

    def device_startup(self, success):
        if success:
            # print(self.node._pump._driver._dev._product)
            self.name_box.setText(str(self.node._pump._driver._dev._product))
            self.serial_number_box.setText(str(self.node.serial_number))
            self.max_channels_box.setText(str(self.node.max_channels))
            self.max_networks_box.setText(str(self.node.max_networks))
            ch_list = [str(i) for i in range(self.node.max_channels)]
            self.channel_number_combo.addItems(ch_list)
            self.channel_profile_combo.addItems(self.dev_profiles)
        else:
            self.message_viewer.append("Error in Device Startup! "
                                       "Relaunch Program to try again")

    def channel_startup(self, success):
        if success:
            self.status_ch_number_combo.addItem(str(self.channel_add_num))
            ch = self.node.channels[self.channel_add_num]
            self.channel_type_box.setText(str(ch.status.get("channel_type")))
            self.network_number_box.setText(str(ch.status.get("network_number")))
            self.device_id_box.setText(str(ch.id.get("device_number")))
            self.device_type_box.setText(str(ch.id.get("device_type")))
            self.channel_state_box.setText(str(ch.status.get("channel_state")))
        else:
            self.message_viewer.append("Error in Channel Startup! "
                                       "Check Parameters and try again")

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
        # del self.thread_parent
        # del self.close_thread

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

    done_signal = pyqtSignal(bool)

    def __init__(self, parent, fn, *args, **kwargs):
        super().__init__(parent=parent)
        self.run_function = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        success = self.run_function(*self.args, **self.kwargs)
        self.done_signal.emit(success)
