# -*- coding: utf-8 -*-
"""
Created on Tue Mar 14 18:10:13 2023

@author: patri
"""

import sys
import os

parent_dir = os.path.abspath(os.path.join(os.getcwd(), '..'))
sys.path.append(os.path.join(parent_dir, "libAnt"))

from PyQt5.QtWidgets import QApplication
from GUI.main_window import MainWindow


if __name__ == "__main__":

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    app.exec_()
