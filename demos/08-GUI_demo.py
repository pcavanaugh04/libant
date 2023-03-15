# -*- coding: utf-8 -*-
"""
Created on Tue Mar 14 18:10:13 2023

@author: patri
"""

import sys
# import os
from PyQt5.QtWidgets import QApplication
from GUI.main_window import MainWindow

# Add packages directory to path
# sys.path.insert(0, os.path.join(os.getcwd(), "packages"))

if __name__ == "__main__":
    # Set up Logging Functionality and Saving Locations
    # log_path = os.path.join(os.getcwd(), "Logs")
    # logger = LoggerFactory(log_path=log_path)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    app.exec_()
