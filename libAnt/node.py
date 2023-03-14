import threading
from queue import Queue, Empty
from time import sleep

from libAnt.drivers.driver import Driver, DriverException
import libAnt.message as m
import libAnt.constants as c
import libAnt.exceptions as ex
import traceback


class Network:
    def __init__(self, key: bytes = b'\x00' * 8, name: str = None):
        self.key = key
        self.name = name
        self.number = 0

    def __str__(self):
        return self.name


class Pump(threading.Thread):
    def __init__(self, driver: Driver,
                 config_queue: Queue,
                 control_queue: Queue,
                 output_queue: Queue,
                 tx_queue: Queue,
                 onSuccess,
                 onFailure,
                 debug):
        super().__init__()
        self._stopper = threading.Event()
        self._driver = driver
        self._config = config_queue
        self._control = control_queue
        self._out = output_queue
        self._tx = tx_queue
        self._config_waiters = []
        self._control_waiters = []
        self._tx_waiters = []
        self._onSuccess = onSuccess
        self._onFailure = onFailure
        self._debug = debug

    def __enter__(self):  # Added by edyas 02/12/21
        return self

    def __exit__(self):  # Added by edyas 02/12/21
        self.stop()

    def stop(self):
        self._driver.abort()
        self._stopper.set()

    def stopped(self):
        return self._stopper.isSet()

# Theres gotta be a better way to organize this run method? Right?
    def run(self):
        with self._driver as d:
            while not self.stopped():
                try:
                    #  Write
                    # Config messages should be sent in sequence. If
                    # additions are made to config queue they should be
                    # sent in a row.
                    while not self._config.empty():
                        self.send_message(self._config,
                                          self._config_waiters,
                                          d)

                    # Otherwise messages are grabbed from the control queue
                    self.send_message(self._control,
                                      self._control_waiters,
                                      d)

                    # Otherwise messages are grabbed from the tx queue
                    self.send_message(self._tx, self._tx_waiters, d)

                    # Read
                    try:
                        msg = d.read(timeout=1)
                        # Diagnostic Print Statements view incoming message
                        if self._debug:
                            print(f'Message Recieved: {msg}')
                            # print(f'Message Type: {msg.type}')
                            # print(f'Waiter msg: {w[0]}')
                            # print(f'Waiter msg type: {w[0].type}')
                    except Empty:
                        pass

                    else:
                        try:
                            out = self.process_read_message(msg)

                        except Exception as e:
                            raise e

                        else:
                            if out is not None:
                                self._onSuccess(out)

                except DriverException as e:
                    traceback.print_exc()
                    self._onFailure(e)
                    self.stop()
                    raise e

                except ex.RxFail as e:
                    self._onFailure(e)

                except ex.TxFail as e:
                    self._onFailure(e)
                    self._tx.task_done()
                    self._out.put(False)
                    self._out.join()

                except Exception as e:
                    traceback.print_exc()
                    self._onFailure(e)

        self._config_waiters.clear()
        self._control_waiters.clear()
        sleep(0.1)

    def send_message(self, queue: Queue, waiters, driver):
        try:
            outMsg = queue.get(block=False)
            driver.write(outMsg)

        except Empty:
            pass

        except Exception as e:
            raise e

        else:
            if self._debug:
                print(f'Message Sent: {outMsg}')

            waiters.append((outMsg, outMsg.callback))

    def process_read_message(self, msg):
        if msg.type == c.MESSAGE_CHANNEL_EVENT:
            # This is a response to our outgoing message
            for w in self._config_waiters:
                if w[0].type == msg.content[1] and w[1] is not None:
                    try:
                        out = w[1](msg, w[0].type)
                    except Exception as e:
                        raise e
                    else:
                        return out
                    finally:
                        self._config.task_done()
                        self._config_waiters.remove(w)
                    break

            for w in self._control_waiters:
                if (w[0].type == msg.content[1] and
                        w[1] is not None):
                    try:
                        out = w[1](msg, w[0].type)
                    except Exception as e:
                        raise e
                    else:
                        return out
                    finally:
                        self._control.task_done()
                        self._control_waiters.remove(w)
                    break

            else:
                # msg.content[1] == c.MESSAGE_RF_EVENT:
                try:
                    out = m.process_event_code(msg.content[2])
                except Exception as e:
                    raise e
                else:
                    return out
                finally:
                    if msg.content[2] == c.EVENT_TRANSFER_TX_COMPLETED:
                        self._tx.task_done()
                        self._out.put(True)
                        pass
                    # elif:
                    #     msg.content[2] == c.EVENT_TRANSFER_TX_FAILED:


                        # TODO: Tie Tx messages in waiters back to the expected
                        # response.
                        # self._tx_waiters.remove(w)

        elif msg.type == c.MESSAGE_CHANNEL_BROADCAST_DATA:
            bmsg = m.BroadcastMessage(msg.type,
                                      msg.content)
            bmsg = bmsg.build(msg.content)
            return bmsg

        # Patrick's Stuff
        else:
            # Notification Messages
            if msg.type == c.MESSAGE_STARTUP:
                msg = m.StartUpMessage(msg.content)
                self._control.task_done()
                return(msg.callback(msg))

            elif msg.type == c.MESSAGE_SERIAL_ERROR:
                self._onFailure(msg)
                raise ex.SerialError()

            elif msg.type == c.MESSAGE_CAPABILITIES:
                for w in self._control_waiters:
                    if msg.type == w[0].reply_type:
                        self._control_waiters.remove(w)
                msg = m.CapabilitiesMessage(msg.content)
                self._control.task_done()
                self._out.put(msg)
                self._out.join()
                return

            # Messages from requested message pages
            else:
                for w in self._control_waiters:
                    if msg.type == w[0].reply_type:
                        self._control_waiters.remove(w)
                        self._control.task_done()
                        return(w[1](msg))

                        break


class Node:
    def __init__(self, driver: Driver,
                 onSuccess,
                 onFailure,
                 name: str = None,
                 debug=False):
        self._driver = driver
        self._name = name
        self._out = Queue()
        self._init = []
        self._pump = None
        self.config_messages = Queue()
        self.control_messages = Queue()
        self.outputs = Queue()
        self.tx_messages = Queue()
        self.channels = []
        self.debug = debug
        
        try:
            self.start(onSuccess, onFailure)
        except DriverException as e:
            print("Exception Occured!")
            raise e
        else:
            self.capabilities = self.get_capabilities(disp=False)
            self.max_channels = self.capabilities["max_channels"]
            self.max_networks = self.capabilities["max_networks"]
            self.channels = [None]*self.max_channels
            self.networks = [0]*self.max_networks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def start(self, onSuccess, onFailure):
        if not self.isRunning():
            self.onSuccess = onSuccess
            self.onFailure = onFailure
            self._pump = Pump(self._driver,
                              self.config_messages,
                              self.control_messages,
                              self.outputs,
                              self.tx_messages,
                              onSuccess,
                              onFailure,
                              self.debug)
            self._pump.start()
            self.reset()

    def open_channel(self, channel_num: int = 0,
                     network_num: int = 0,
                     network_key=c.ANTPLUS_NETWORK_KEY,
                     channel_type=c.CHANNEL_BIDIRECTIONAL_SLAVE,
                     device_type=0,
                     channel_frequency=2457,
                     channel_msg_freq=4,
                     channel_search_timeout=30,
                     **kwargs):
        # Some input checking
        if channel_num > self.max_channels or channel_num < 0:
            print("Error: Channel assignment exceeds device capabilities")
            return

        if network_num > self.max_networks or network_num < 0:
            print("Error: Network assignment exceeds device capabilities")
            return

        if self.channels[channel_num] is not None:
            print("Error: Channel is already in use")

        if 'device' in kwargs:
            match kwargs.get('device'):
                case 'FE-C':
                    device_type = 17

                case 'PWR':
                    device_type = 0

                case 'HR':
                    device_type = 0x78
                    channel_msg_freq = 4.06

        # Create channel object in node's channels list
        try:
            self.channels[channel_num] = Channel(self.config_messages,
                                                 self.control_messages,
                                                 self.outputs,
                                                 channel_num,
                                                 network_num,
                                                 network_key,
                                                 channel_type,
                                                 device_type,
                                                 channel_frequency,
                                                 channel_msg_freq,
                                                 channel_search_timeout)
        except Exception as e:
            raise e
            return

        try:
            self.channels[channel_num].open()

        except Exception as e:
            raise e
            return

    def close_channel(self, channel_num):
        try:
            self.channels[channel_num].close()
        except Exception as e:
            raise e
        else:
            del self.channels[channel_num]
            self.channels[channel_num] = None

    def send_tx_msg(self, msg):
        self.tx_messages.put(msg)
        self.tx_messages.join()
        msg_status = self.outputs.get()
        self.outputs.task_done()
        return(msg_status)
        # TODO: Implement tx success/fail callbacks

    # Depreciated
    def enableRxScanMode(self, networkKey=c.ANTPLUS_NETWORK_KEY,
                         channelType=c.CHANNEL_TYPE_ONEWAY_RECEIVE,
                         frequency: int = 2457,
                         rxTimestamp: bool = True,
                         rssi: bool = True,
                         channelId: bool = True):
        self._init.append(m.ResetSystemMessage())
        self._init.append(m.SetNetworkKeyMessage(0, networkKey))
        self._init.append(m.AssignChannelMessage(0, channelType))
        self._init.append(m.SetChannelIdMessage(0))
        self._init.append(m.SetChannelRfFrequencyMessage(0, frequency))
        self._init.append(m.EnableExtendedMessagesMessage())
        self._init.append(m.LibConfigMessage(rxTimestamp, rssi, channelId))
        self._init.append(m.OpenRxScanModeMessage())

    def stop(self):
        if self.isRunning():
            self._pump.stop()
            self._pump.join()

    def isRunning(self):
        if self._pump is None:
            return False
        return self._pump.is_alive()

    def reset(self):
        self.control_messages.put(m.ResetSystemMessage())
        if self.channels == []:
            return
        else:
            for x in self.channels:
                if x is not None:
                    del x
            self.channels = [None]*self.max_channels

    def get_capabilities(self, disp=True):
        self.control_messages.put(m.RequestCapabilitiesMessage(), block=False)
        self.control_messages.join()
        cap_msg = self.outputs.get(block=True)
        self.outputs.task_done()
        cap_dict = cap_msg.capabilities_dict
        if disp:
            print(cap_msg.disp_capabilities(cap_msg))
        return cap_dict

    def get_channel_status(self, channel_num: int):
        # Not sure if this works
        self.control_messages.put(m.RequestChannelStatusMessage(channel_num),
                                  block=False)

    def get_channel_ID(self, channel_num: int):
        # Not sure if this works
        self.control_messages.put(m.RequestChannelIDMessage(channel_num),
                                  block=False)

    def get_ANT_serial_number(self):
        # Not sure if this works
        self.control_messages.put(m.RequestSerialNumberMessage(), block=False)

    # Depreciated. Saved for docstring
    def pair_FEC_channel(self, network_key=c.ANTPLUS_NETWORK_KEY,
                         channel_number=0,
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
        pass


class Channel:
    """Channel class to handle IO of a single connection"""

    def __init__(self, config_queue,
                 control_queue,
                 out_queue,
                 channel_num=0,
                 network_num=0,
                 network_key=c.ANTPLUS_NETWORK_KEY,
                 channel_type=c.CHANNEL_BIDIRECTIONAL_SLAVE,
                 device_type=0,
                 channel_frequency=2457,
                 channel_msg_freq=4,
                 channel_search_timeout=30):

        self._cfig = config_queue
        self._ctrl = control_queue
        self._out = out_queue
        self.number = channel_num
        self.network = network_num
        self.network_key = network_key
        self._type = channel_type
        self.device_type = device_type
        self.frequency = channel_frequency
        self.msg_freq = channel_msg_freq
        self.search_timeout = channel_search_timeout

        self._cfig.put(m.SetNetworkKeyMessage(self.network,
                                              self.network_key))
        self._cfig.put(m.AssignChannelMessage(self.number,
                                              self._type))
        self._cfig.put(m.SetChannelIdMessage(self.number,
                                             device_type=self.device_type))
        self._cfig.put(m.SetChannelRfFrequencyMessage(self.number,
                                                      self.frequency))
        self._cfig.put(m.ChannelMessagingPeriodMessage(self.number,
                                                       self.msg_freq))
        self._cfig.put(m.ChannelSearchTimeoutMessage(self.number,
                                                     self.search_timeout))
        self._cfig.join()

    def open(self):
        self._ctrl.put(m.OpenChannelMessage(self.number))

    def close(self):
        self._ctrl.put(m.CloseChannelMessage(self.number))
