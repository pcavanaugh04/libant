# -*- coding: utf-8 -*-
"""
Created on Tue Mar 14 18:14:15 2023

@author: patri
"""
from PyQt5.QtWidgets import QMainWindow
from PyQt5 import uic
import os
from datetime import datetime
from PyQt5.QtCore import pyqtSlot, pyqtBoundSignal, pyqtSignal, QObject
from libAnt.node import Node
from libAnt.drivers.usb import USBDriver, DriverException
from libAnt.message import Message


class MainWindow(QMainWindow):

    def __init__(self):
        # %% Load UI elements
        self.program_start_time = datetime.now()

        # Initialize superclass
        QMainWindow.__init__(self)
        # Load the graphical layout
        path = os.path.join(os.getcwd(), "GUI", "ant_UI.ui")
        self.UI_elements = uic.loadUi(path, self)
        try:
            self.node = Node(USBDriver(vid=0x0FCF, pid=0x1008), debug=False)
        except DriverException as e:
            print(e)
            return

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

        self.node.start(self.obj.callback, self.obj.error_callback)
        # self.node.open_channel(0, profile='FE-C')

    def closeEvent(self, event):
        self.node.stop()
        event.accept()
        pass

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