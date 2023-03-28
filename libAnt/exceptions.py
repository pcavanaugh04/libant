"""
Created on Mon Mar 13 10:24:19 2023
Exceptions module for libAnt library. This module connects ANT Protocol
messages associated with failures to custom exception classes to allow the
program to track and handle failure events within a try-except structure.

@author: patri
"""
# import libAnt.constants as c


class SerialError(Exception):
    """ANT Section 9.5.3.2 (0xAE)

    The Serial Error Message is sent in response to a poorly formed USB data.
    The data portion of this message may be used to debug the USB packet.
    """

    def __init__(self, msg):
        from libAnt.message import SerialErrorMessage
        err_msg = SerialErrorMessage.disp_serial_error(msg)
        super().__init__(err_msg)
        self.message = err_msg


class RxFail(Exception):
    """ANT Section 9.5.6.1 (0x02)

    A receive channel missed a message which it was expecting. This happens
    when a slave is tracking a master and is expecting a message at the set
    message rate.
    """

    def __init__(self, message="Rx Fail"):
        super().__init__(message)
        self.message = message


class TxFail(Exception):
    """ANT Section 9.5.6.1 (0x06)

    An Acknowledged Data message, or a Burst Transfer Message has been
    initiated and the transmission failed to complete successfully
    """

    def __init__(self, message="Tx Fail"):
        super().__init__(message)
        self.message = message


class RxSearchTimeout(Exception):
    """ANT Section 9.5.6.1 (0x08)

    The channel has dropped to search mode after missing too many messages.
    """

    def init(self, message="Channel Dropout. Go To Search"):
        super().__init__(message)
        self.message = message
        pass


# Exceptions to Be implemented
class ChannelInWrongState(Exception):
    def init(self, msg):
        message = ("Error: Channel in Wrong State for Message"
                   f"Type: {msg.type}")
        super().__init__(message)
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
