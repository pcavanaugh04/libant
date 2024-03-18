# -*- coding: utf-8 -*-
"""
Created on Tue Mar 14 18:10:13 2023

@author: patri
"""

from libAnt.GUI.ant_window import ANTWindow
from libAnt.ANT_device import ANTDevice
import sys
import os
from PyQt5.QtWidgets import QApplication

sys.path.insert(0, os.path.abspath(os.getcwd()))

from libAnt.logger_factory import LoggerFactory


if __name__ == "__main__":

    # Set up Logging Functionality and Saving Locations
    logger = LoggerFactory()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    ANT = ANTDevice(debug=True, logger=logger.name)
    w = ANTWindow(ANT)
    w.show()
    app.exec_()
