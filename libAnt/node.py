import threading
from queue import Queue, Empty
from time import sleep

from libAnt.drivers.driver import Driver
from libAnt.message import *


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
                    rst = SystemResetMessage()
                    self._waiters.append((rst, rst.callback))
                    d.write(rst)
                    # Wait time for Stick to complete reset event
                    sleep(0.6)

                    for m in self._initMessages:
                        if hasattr(m, 'reply_type'):
                            self._waiters.append((m, m.callback))
                        else:
                            self._waiters.append((m))

                    while not self.stopped():
                        #  Write
                        try:
                            outMsg = self._out.get(block=False)
                            d.write(outMsg)

                        except Empty:
                            pass

                        except Exception as e:
                            print(e)

                        if hasattr(outMsg, 'reply_type'):
                            self._waiters.append((outMsg, outMsg.callback))
                        else:
                            self._waiters.append((outMsg))

                        # Read
                        try:
                            msg = d.read(timeout=1)
                            # Diagnostic Print Statement to view incoming message
                            # print(f'Message Recieved: {msg}')
                            # print(f'Message Type: {msg.type}')

                            # TODO: build a library of the expected resonses associated with each control function

                            # print(f'Waiter msg: {w[0]}')
                            # print(f'Waiter msg type: {w[0].type}')
                            # print(f'Reply Expected?: {w[0].expect_reply}')

                            if msg.type == MESSAGE_CHANNEL_EVENT:
                                # This is a response to our outgoing message
                                for w in self._waiters:
                                    if w[0].type == msg.content[1]:  # ACK
                                        if w[1] is not None:
                                            w[1]()
                                        self._waiters.remove(w)
                                        # TODO: Call waiter callback from tuple (waiter, callback)
                                        break
                            elif msg.type == MESSAGE_CHANNEL_BROADCAST_DATA:
                                bmsg = BroadcastMessage(msg.type, msg.content).build(msg.content)
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
                self._onFailure(e)
            except:
                pass
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
            self._pump = Pump(self._driver, self._init, self._out, onSuccess, onFailure)
            self._pump.start()

    def enableRxScanMode(self, networkKey=ANTPLUS_NETWORK_KEY, channelType=CHANNEL_TYPE_ONEWAY_RECEIVE,
                         frequency: int = 2457, rxTimestamp: bool = True, rssi: bool = True, channelId: bool = True):
        self._init.append(SystemResetMessage())
        self._init.append(SetNetworkKeyMessage(0, networkKey))
        self._init.append(AssignChannelMessage(0, channelType))
        self._init.append(SetChannelIdMessage(0))
        self._init.append(SetChannelRfFrequencyMessage(0, frequency))
        self._init.append(EnableExtendedMessagesMessage())
        self._init.append(LibConfigMessage(rxTimestamp, rssi, channelId))
        self._init.append(OpenRxScanModeMessage())

    def stop(self):
        if self.isRunning():
            self._pump.stop()
            self._pump.join()

    def isRunning(self):
        if self._pump is None:
            return False
        return self._pump.is_alive()

    def getCapabilities(self):
        self._out.put(RequestCapabilitiesMessage(), block=False)
        