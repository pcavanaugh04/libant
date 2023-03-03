"""
Created on Wed Mar  1 15:17:46 2023

@author: patri
"""

from time import sleep

from libAnt.drivers.usb import USBDriver
from libAnt.node import Node


def callback(msg):
    print(msg)


def eCallback(e):
    print(e)


# For USB driver
# USBm sticks have pid=0x1009
# USB2 sticks have pid=0x1008
n = Node(USBDriver(vid=0x0FCF, pid=0x1008), 'MyNode')

n.start(callback, eCallback)
n.getCapabilities()
sleep(1)  # Listen for 3sec
n.stop()