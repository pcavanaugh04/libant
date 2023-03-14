# -*- coding: utf-8 -*-
"""
Created on Tue Mar 14 18:14:15 2023

@author: patri
"""
from PyQt5.QtWidgets import QMainWindow
from PyQt5 import uic
import os
from datetime import datetime
from PyQt5.QtCore import pyqtSlot


class MainWindow(QMainWindow):

    def __init__(self):
        # %% Load UI elements
        self.program_start_time = datetime.now()

        # Load the graphical layout
        path = os.path.join(os.getcwd(), "resources", "main_UI.ui")
        self.UI_elements = uic.loadUi(path, self)

    def closeEvent(self):
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