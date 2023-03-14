"""
Created on Wed Mar  1 15:17:46 2023

@author: patri
"""

from time import sleep

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
    sleep(5)
    # Wait for connection, read some messages
    # TODO: Implement channel connection success notifier capability
    # Send user config
    cfg = p.set_user_config(channel)
    print(f'Sending Configuration Message: {cfg}')
    status = n.send_tx_msg(cfg)
    print(status)
    # Try sending grade change tx messages
    success = True
    while success:
        msg = p.set_grade(channel, 1)
        print(f'Sending Grade Change Message: {cfg}')
        success = n.send_tx_msg(msg)
        # Wait for response
        sleep(1)
        
    # Close Channel
    n.channels[0].close()
    sleep(1)
