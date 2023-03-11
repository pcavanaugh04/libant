import threading
from queue import Queue, Empty
from time import sleep

from libAnt.drivers.driver import Driver
import libAnt.message as m
import libAnt.constants as c
import traceback


class Network:
    def __init__(self, key: bytes = b'\x00' * 8, name: str = None):
        self.key = key
        self.name = name
        self.number = 0

    def __str__(self):
        return self.name


class Pump(threading.Thread):
    def __init__(self, driver: Driver, initMessages, out: Queue, onSuccess, onFailure):
        super().__init__()
        self._stopper = threading.Event()
        self._driver = driver
        self._out = out
        self._initMessages = initMessages
        self._waiters = []
        self._onSuccess = onSuccess
        self._onFailure = onFailure
    
    def __enter__(self):                #Added by edyas 02/12/21
        return self
    
    def __exit__(self):                 #Added by edyas 02/12/21
        self.stop()

    def stop(self):
        self._driver.abort()
        self._stopper.set()

    def stopped(self):
        return self._stopper.isSet()

# Theres gotta be a better way to organize this run method? Right?
# Waiters array appears to be messages that are awating a response from the stick
    def run(self):
        while not self.stopped():
            try:
                with self._driver as d:
                    # Startup
                    rst = m.ResetSystemMessage()
                    self._waiters.append((rst, rst.callback))
                    d.write(rst)
                    # Wait time for Stick to complete reset event
                    sleep(0.6)

                    for msg in self._initMessages:
                        if hasattr(msg, 'reply_type'):
                            self._waiters.append((msg, msg.callback))
                        else:
                            self._waiters.append((msg))
                        self._out.put(msg)

                    while not self.stopped():
                        #  Write
                        try:
                            outMsg = self._out.get(block=False)
                            d.write(outMsg)
                            # print(f'Message Sent: {outMsg}')

                        except Empty:
                            pass

                        except Exception as e:
                            print(e)

                        else:
                            self._waiters.append((outMsg, outMsg.callback))

                        # Read
                        try:
                            msg = d.read(timeout=1)
                            # Diagnostic Print Statements view incoming message
                            # print(f'Message Recieved: {msg}')
                            # print(f'Message Type: {msg.type}')
                            # print(f'Waiter msg: {w[0]}')
                            # print(f'Waiter msg type: {w[0].type}')

                            if msg.type == c.MESSAGE_CHANNEL_EVENT:
                                # This is a response to our outgoing message
                                for w in self._waiters:
                                    if w[0].type == msg.content[1]:  # ACK
                                        if w[1] is not None:
                                            self._onSuccess(w[1](msg))

                                        self._waiters.remove(w)
                                        break
                            elif msg.type == c.MESSAGE_CHANNEL_BROADCAST_DATA:
                                bmsg = m.BroadcastMessage(msg.type,
                                                          msg.content)
                                bmsg = bmsg.build(msg.content)
                                self._onSuccess(bmsg)

                            # Framework for setting up control messages and processing replies from the stick
                            # Patrick's Stuff
                            else:
                                for w in self._waiters:
                                    if len(w) == 2:  # m has msg and callback
                                        if msg.type == w[0].reply_type:
                                            self._onSuccess(w[1](msg))
                                            self._waiters.remove(w)
                                    else:
                                        self._onSuccess(msg)
                                        self._waiters.remove(w)

                        except Empty:
                            pass
            except Exception as e:
                traceback.print_exc()
                self._onFailure(e)

            self._waiters.clear()
            sleep(1)


class Node:
    def __init__(self, driver: Driver, name: str = None):
        self._driver = driver
        self._name = name
        self._out = Queue()
        self._init = []
        self._pump = None
        self._configMessages = Queue()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def start(self, onSuccess, onFailure):
        if not self.isRunning():
            self.onSuccess = onSuccess
            self.onFailure = onFailure
            self._pump = Pump(self._driver,
                              self._init,
                              self._out,
                              onSuccess,
                              onFailure)
            self._pump.start()

    def enableRxScanMode(self, networkKey=c.ANTPLUS_NETWORK_KEY,
                         channelType=c.CHANNEL_TYPE_ONEWAY_RECEIVE,
                         frequency: int = 2457,
                         rxTimestamp: bool = True,
                         rssi: bool = True,
                         channelId: bool = True):
        self._init.append(m.SystemResetMessage())
        self._init.append(m.SetNetworkKeyMessage(0, networkKey))
        self._init.append(m.AssignChannelMessage(0, channelType))
        self._init.append(m.SetChannelIdMessage(0))
        self._init.append(m.SetChannelRfFrequencyMessage(0, frequency))
        self._init.append(m.EnableExtendedMessagesMessage())  # Do I need to do this?
        self._init.append(m.LibConfigMessage(rxTimestamp, rssi, channelId))  # What is this?
        self._init.append(m.OpenRxScanModeMessage())

    def stop(self):
        if self.isRunning():
            self._pump.stop()
            self._pump.join()

    def isRunning(self):
        if self._pump is None:
            return False
        return self._pump.is_alive()

    # TODO: Should _out be classed as a property?
    
    def getCapabilities(self):
        self._out.put(m.RequestCapabilitiesMessage(), block=False)

    def getChannelStatus(self, channel_num: int):
        self._out.put(m.RequestChannelStatusMessage(channel_num), block=False)

    def getChannelID(self, channel_num: int):
        self._out.put(m.RequestChannelIDMessage(channel_num), block=False)

    def getANTSerialNumber(self):
        self._out.put(m.RequestSerialNumberMessage(), block=False)

    def openChannel(self, network_key=c.ANTPLUS_NETWORK_KEY,
                    channel_type=c.CHANNEL_BIDIRECTIONAL_SLAVE,
                    frequency: int = 2457,
                    rxTimestamp: bool = True,
                    rssi: bool = True,
                    channelId: bool = True):
        """Open ANT Channel with Given Parameters.

        Default is bidirectional slave channel on ANT+ Network

        Parameters
        ----------
        network_key : bytes, optional
            ANT network key for device connection. Set to zero for public key.
            The default is ANTPLUS_NETWORK_KEY.
        channel_type : hex, optional
            Hex value of channel type corresponding to ANT Protocol usage doc
            section X.X.XX. The default is CHANNEL_BIDIRECTIONAL_SLAVE.
        frequency : int, optional
            RF frequency band of the channel.
            The default is 2457 for ANT+ Devices.
        rxTimestamp : bool, optional
            DESCRIPTION. The default is True.
        rssi : bool, optional
            DESCRIPTION. The default is True.
        channelId : bool, optional
            DESCRIPTION. The default is True.

        Returns
        -------
        None.

        """

# TODO: Make Channel Class as attribute of node
# class Channel:
    