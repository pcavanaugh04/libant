"""
Created on Wed Mar  1 15:17:46 2023

@author: patri
"""

from time import sleep
from random import random

from libAnt.drivers.usb import USBDriver
from libAnt.node import Node
import libAnt.profiles.fitness_equipment_profile as p


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
          'MyNode',
          debug=False) as n:
    # Smart Trainer: device='FE-C'
    channel = 0

    n.open_channel(channel_num=channel, device='FE-C')
    # This is now a blocking function. The program will not progress until
    # a connection is made
    # Send user config
    cfg = p.set_user_config(channel)
    status = n.send_tx_msg(cfg)

    # Send Grade change messages until one fails or user interrupt
    success = True
    while success:
        try:
            grade = random() * 20 - 10
            msg = p.set_grade(channel, grade)
            print(f'Sending Grade Change Message: {msg}')
            success = n.send_tx_msg(msg)
            # Wait for response
            sleep(2)
        except KeyboardInterrupt:
            break

    # Close Channel
    n.channels[0].close()
    sleep(1)
