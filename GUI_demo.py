# -*- coding: utf-8 -*-
"""
Created on Tue Mar 14 18:10:13 2023

@author: patri
"""

from libAnt.GUI.ant_window import ANTWindow, ANTDevice
import sys
import os
from PyQt5.QtWidgets import QApplication

sys.path.insert(0, os.path.abspath(os.getcwd()))


if __name__ == "__main__":

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    ANT = ANTDevice(debug=True)
    w = ANTWindow(ANT)
    w.show()
    app.exec_()
