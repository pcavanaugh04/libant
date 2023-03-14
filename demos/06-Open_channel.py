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


with Node(USBDriver(vid=0x0FCF, pid=0x1008),
          callback,
          eCallback,
          'MyNode') as n:
    # Try out some different ANT+ Profiles
    # Heartrate: device='HR'
    # Power Meter: device='PWR'
    # Smart Trainer: device='FE-C'
    n.open_channel(channel_num=0, device='HR')
    sleep(2)
    n.send_tx_msg(0, grade=0)
    sleep(5)
    n.channels[0].close()
    sleep(1)
