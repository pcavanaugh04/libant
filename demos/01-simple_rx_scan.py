#!/usr/bin/env python3
from time import sleep

from libAnt.drivers.serial import SerialDriver
from libAnt.drivers.usb import USBDriver
from libAnt.node import Node


def callback(msg):
    print(msg)


def eCallback(e):
    print(e)


# for USB driver on Windows
with Node(USBDriver(vid=0x0FCF, pid=0x1009), 'MyNode') as n:
    n.enableRxScanMode()
    n.start(callback, eCallback)
    sleep(30)  # Listen for 30sec
