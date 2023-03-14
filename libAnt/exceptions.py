# -*- coding: utf-8 -*-
"""
Created on Mon Mar 13 10:24:19 2023
Exceptions module for libAnt library

@author: patri
"""
import libAnt.constants as c


class SerialError(Exception):
    def init(self):
        pass


class RxFail(Exception):
    def init(self):
        pass


class TxFail(Exception):
    def init(self):
        pass


class RxSearchTimeout(Exception):
    def init(self):
        pass


class ChannelInWrongState(Exception):
    def init(self):
        pass


class ChannelNotOpened(Exception):
    def init(self):
        pass


class ChannelIDNotSet(Exception):
    def init(self):
        pass


class MessageSizeExceedsLimit(Exception):
    def init(self):
        pass


class InvalidMessage(Exception):
    def init(self):
        pass


class InvalidNetworkNumber(Exception):
    def init(self):
        pass


class SerialQueueOverflow(Exception):
    def init(self):
        pass