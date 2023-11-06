import threading
from queue import Queue, Empty
from time import sleep
from datetime import datetime

from libAnt.drivers.driver import Driver, DriverException
from libAnt.drivers.usb import USBDriver
import libAnt.message as m
import libAnt.constants as c
import libAnt.exceptions as ex
import traceback


class Network:
    """Define network object for shared, private communication"""

    def __init__(self, key: bytes = b'\x00' * 8, name: str = None):
        self.key = key
        self.name = name
        self.number = 0

    def __str__(self):
        return self.name


class Pump(threading.Thread):
    """Encapsulate device read/write functions for use in external thread

    Pump object recieves messages from queues configured at the node level and
    sends queued messages to the connected ANT device using a thread-safe usb
    driver. Therefore multiple pump objects can reference the same USB device.

    Attributes
    ----------

    Methods
    -------
    run()
        Characteristic of any thread object containing the code to be executed
        when the thread begins
    send_message(queue, waiter, driver)
        Encapsulated function for extracting message from queues and adding
        necessary waiter content
    process_read_message(msg)
        Encapsulated function for processing recieved messages, executing
        necessary callbacks, and raising errors when necessary
    """

    def __init__(self, driver: Driver,
                 config_queue,
                 control_queue,
                 output_queue,
                 tx_queue,
                 on_shutdown,
                 onSuccess,
                 onFailure,
                 debug):
        super().__init__()
        self._stopper = threading.Event()
        self._pauser = threading.Event()
        self._driver = driver
        self._config = config_queue
        self._control = control_queue
        self._out = output_queue
        self._tx = tx_queue
        self._tx_waiters = []
        self._onSuccess = onSuccess
        self._onFailure = onFailure
        self._debug = debug
        self.on_shutdown = on_shutdown

    def __enter__(self):  # Added by edyas 02/12/21
        return self

    def __exit__(self):  # Added by edyas 02/12/21
        self.stop()

    def stop(self):
        if not self._stopper.isSet():
            self._stopper.set()

    def pause(self):
        if self.paused():
            return
        else:
            self._pauser.set()

    def resume(self):
        if not self.paused():
            return
        else:
            self._pauser.clear()

    def paused(self):
        return self._pauser.isSet()

    def stopped(self):
        return self._stopper.isSet()

# Theres gotta be a better way to organize this run method? Right?
    def run(self):
        with self._driver as d:
            while not self.stopped():
                if self.paused():
                    sleep(0.1)
                    pass
                else:
                    try:
                        #  Write
                        # Send messages from device level queues
                        self._config.send_message(unload=True)
                        self._control.send_message()
                        # self._tx.send_message()

                        # Send messages from any awaiting channel queues
                        self._control.send_channel_messages()
                        self._tx.send_channel_messages()

                        # Read
                        try:
                            msg = d.read(timeout=1)
                            # Diagnostic Print Statements view incoming message
                            if self._debug:
                                print(f'Message Recieved: {msg}')
                                # print(f'Message Type: {msg.type}')
                                # print(f'Waiter msg: {w.message}')
                                # print(f'Waiter msg type: {w.message.type}')
                        except Empty:
                            pass

                        except DriverException as e:
                            # traceback.print_exc()
                            # self._onFailure(e)
                            # self.on_shutdown.fire()
                            # print("Do we get here?")
                            # self.stop()
                            raise e

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
                        # self.on_shutdown.fire()
                        self.stop()
                        # raise e

                    except ex.RxFail as e:
                        self._onFailure(e)

                    except ex.TxFail as e:
                        self._onFailure(e)
                        self._tx.task_done()
                        self._out.put(False)
                        self._out.join()

                    except ex.RxFailGoToSearch as e:
                        self._onFailure(e)

                    except ex.RxSearchTimeout as e:
                        self._onFailure(e)
                        com_channel = self._out.channels[e.channel]
                        if not com_channel.first_message_flag:
                            com_channel._out.get()
                            self._out.remove_task(e.channel)
                            sleep(0.1)
                            print(f"Timeout Occurred! on channel: {e.channel}")
                            self._out.output_msg(e, e.channel)

                    except Exception as e:
                        traceback.print_exc()
                        self._onFailure(e)

        self._config.waiters.clear()
        self._control.waiters.clear()
        self._tx.waiters.clear()
        sleep(0.1)

    def process_read_message(self, msg):

        # Control Message Responses
        for w in self._control.waiters:
            # Requested Response Messages
            if w.message.type == c.MESSAGE_CHANNEL_REQUEST:
                if w.message.content[1] == msg.type:
                    try:
                        msg = w.callback(msg.content)
                    except Exception as e:
                        raise e
                    finally:
                        self._control.remove_task(w.channel, w)
                        self._out.output_msg(msg, w.channel)

            # Channel Event Messages in response to control messages
            elif msg.type == c.MESSAGE_CHANNEL_EVENT:
                msg = m.ChannelResponseMessage(msg)
                # Match channel response message to message in waiter
                if all([w.message.channel == msg.channel,
                        w.message.type == msg.message_ID,
                        w.callback is not None]):
                    try:
                        out = w.callback(msg, w.message.type)
                    except Exception as e:
                        raise e
                    else:
                        return out
                    finally:
                        self._control.remove_task(w.channel, w)
                    break

        if msg.type == c.MESSAGE_CHANNEL_EVENT:
            msg = m.ChannelResponseMessage(msg)
            # This is a response to our outgoing message
            for w in self._config.waiters:
                # print(f"waiter type: {w.message.type} || message: {msg.type}")
                if w.message.type == msg.message_ID and w.callback is not None:
                    try:
                        out = w.callback(msg, w.message.type)
                    except Exception as e:
                        raise e
                    else:
                        return out
                    finally:
                        self._config.remove_task(w.channel, w)
                    break

            # msg.content[1] == c.MESSAGE_RF_EVENT:
            try:
                out = msg.process_event()
            except Exception as e:
                raise e
            else:
                return out
            finally:
                # Special Case for Channel Close Confirmation message
                # TODO: These two blocks will have to be updated to new architecture
                if (msg.content[1] == c.MESSAGE_RF_EVENT
                        and msg.content[2] == c.EVENT_CHANNEL_CLOSED):
                    print(f"contents of out queue: {list(self._out.queue)}")
                    print(f"number of tasks left in queue {self._out.qsize()}")
                    try:
                        self._out.get(block=False)
                    except Empty:
                        pass
                    else:
                        self._out.task_done()
                    finally:
                        # This works for 1 channel handling at a time...
                        com_channel = self._out.channels[msg.channel]
                        com_channel.first_message_flag = False

                if msg.content[2] == c.EVENT_TRANSFER_TX_COMPLETED:
                    self._tx.task_done()
                    self._out.put(True)

        elif msg.type == c.MESSAGE_CHANNEL_BROADCAST_DATA:
            # Build broadcast message into standard format
            bmsg = m.BroadcastMessage(msg.type,
                                      msg.content)
            bmsg = bmsg.build(msg.content)
            # Change first message flags to notify of successful connection
            com_channel = self._out.channels[bmsg.channel]
            if not com_channel.first_message_flag:
                com_channel._out.get()
                com_channel._out.task_done()
                com_channel.first_message_flag = True

            return bmsg

        # Patrick's Stuff
        else:
            # Notification Messages
            if msg.type == c.MESSAGE_STARTUP:
                start_msg = m.StartUpMessage(msg.content)
                self._control.remove_task(None)
                self._control.waiters.clear()
                return(start_msg.disp_startup(msg))

            elif msg.type == c.MESSAGE_SERIAL_ERROR:
                self._control.remove_task(None)
                raise ex.SerialError(msg.content)


class Node:
    def __init__(self, onSuccess=None,
                 onFailure=None,
                 name: str = None,
                 debug=False):
        self._name = name
        self._init = []
        self._pump = None
        self.on_shutdown = EventHook()
        self._channels = []
        self.config_manager = QueueManager(self, "cfg")
        self.control_manager = QueueManager(self, "ctrl")
        self.outputs_manager = QueueManager(self, "out")
        self.tx_manager = QueueManager(self, "tx")
        self.debug = debug
        self.onSuccess = onSuccess
        self.onFailure = onFailure
        self.messages = []

        try:
            # Try Opening Node with PID corresponding to ANT USB-m device
            self.driver = USBDriver(vid=0x0FCF, pid=0x1009)

        except DriverException:
            try:
                # If failed, try with PID corresponding to ANT USB-2 device
                self.node = USBDriver(vid=0x0FCF, pid=0x1008)

            except DriverException as e:
                # If this fails, the device is probably not plugged in
                raise e

    @property
    def channels(self):
        return self._channels

    @channels.setter
    def channels(self, value):
        self._channels = value

    def add_channel(self, channel_num, channel):
        self.channels[channel_num] = channel

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def start(self, onSuccess=None, onFailure=None):

        if self.isRunning():
            return True

        if onSuccess:
            self.onSuccess = onSuccess
        if onFailure:
            self.onFailure = onFailure

        try:
            # Try Opening Node with PID corresponding to ANT USB-m device
            self.node = Node(USBDriver(vid=0x0FCF, pid=0x1009),
                             debug=False)

        except DriverException:
            try:
                # If failed, try with PID corresponding to ANT USB-2 device
                self.node = Node(USBDriver(vid=0x0FCF, pid=0x1008),
                                 debug=True)
            except DriverException as e:
                # If this fails, the device is probably not plugged in
                print(e)
                return

        self._pump = Pump(self._driver,
                          self.config_manager,
                          self.control_manager,
                          self.outputs_manager,
                          self.tx_manager,
                          self.on_shutdown,
                          self.onSuccess,
                          self.onFailure,
                          self.debug)
        self._pump.start()
        self.reset()
        self.capabilities = self.get_capabilities(disp=False)
        self.serial_number = self.get_ANT_serial_number(disp=False)
        self.max_channels = self.capabilities["max_channels"]
        self.max_networks = self.capabilities["max_networks"]
        # self._pump.first_message_flags = [False] * self.max_channels
        self.channels = [None] * self.max_channels
        # self.config_manager.channel_queues = [None] * self.max_channels
        # self.control_manager.channel_queues = [None] * self.max_channels
        # self.outputs_manager.channel_queues = [None] * self.max_channels
        # self.tx_manager.channel_queues = [None] * self.max_channels
        self.networks = [0] * self.max_networks

        return True

    def open_channel(self, channel_num: int = 0,
                     network_num: int = 0,
                     network_key=c.ANTPLUS_NETWORK_KEY,
                     channel_type=c.CHANNEL_BIDIRECTIONAL_SLAVE,
                     device_type=0,
                     channel_frequency=2457,
                     channel_msg_freq=4,
                     channel_search_timeout=5,
                     **kwargs):
        # Some input checking
        if channel_num > self.max_channels or channel_num < 0:
            print("Error: Channel assignment exceeds device capabilities")
            return False

        if network_num > self.max_networks or network_num < 0:
            print("Error: Network assignment exceeds device capabilities")
            return False

        if self.channels[channel_num] is not None:
            print("Error: Channel is already in use")
            return False

        if 'profile' in kwargs:
            match kwargs.get('profile'):
                case 'FE-C':
                    device_type = 17

                case 'PWR':
                    device_type = 0

                case 'HR':
                    device_type = 0x78
                    channel_msg_freq = 4.06

        # Create channel object in node's channels list
        try:
            self.channels[channel_num] = Channel(self.config_manager,
                                                 self.control_manager,
                                                 self.outputs_manager,
                                                 self.tx_manager,
                                                 self.onSuccess,
                                                 self.onFailure,
                                                 channel_num,
                                                 network_num,
                                                 network_key,
                                                 channel_type,
                                                 device_type,
                                                 channel_frequency,
                                                 channel_msg_freq,
                                                 channel_search_timeout)

        except Exception as e:
            self.onFailure(e)
            return False

        self.onSuccess(f"Channel {channel_num} Configuration Success!\n"
                       f"Attempting to Open Channel {channel_num}...")

        return (self.channels[channel_num].open())

    # TODO: Make this channel attribute?
    def close_channel(self, channel_num, timeout=False):
        try:
            self.channels[channel_num].close(timeout=timeout)
        except Exception as e:
            raise e
            return False
        else:
            del self.channels[channel_num]
            self.channels[channel_num] = None
            return True

    # TODO: Make this channel attribute
    def send_tx_msg(self, msg):
        self.tx_messages.put(msg)
        self.tx_messages.join()
        msg_success = self.outputs.get()
        self.outputs.task_done()
        return msg_success

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
        return True

    def isRunning(self):
        if self._pump is None:
            return False
        return self._pump.is_alive()

    def reset(self):
        self.control_manager.put(m.ResetSystemMessage())
        if self.channels == []:
            return
        else:
            for x in self.channels:
                if x is not None:
                    del x
            self.channels = [None] * self.max_channels

    def get_capabilities(self, disp=True):
        self.control_manager.put(m.RequestCapabilitiesMessage(), block=False)
        self.control_manager.join()
        cap_msg = self.outputs_manager.get(block=True)
        self.outputs_manager.task_done()
        cap_dict = cap_msg.capabilities_dict
        if disp:
            self.onSuccess(cap_msg.disp_capabilities(cap_msg))
        return cap_dict

    # def get_channel_status(self, channel_num: int, disp=True):
    #     # Not sure if this works
    #     self.control_messages.put(m.RequestChannelStatusMessage(channel_num),
    #                               block=False)
    #     self.control_messages.join()
    #     stat_msg = self.outputs.get(block=True)
    #     self.outputs.task_done()
    #     stat_dict = stat_msg.status_dict
    #     if disp:
    #         self.onSuccess(stat_msg.disp_status(stat_msg))
    #     return stat_dict

    # def get_channel_ID(self, channel_num: int, disp=True):
    #     self.control_messages.put(m.RequestChannelIDMessage(channel_num),
    #                               block=False)
    #     self.control_messages.join()
    #     id_msg = self.outputs.get(block=True)
    #     id_dict = id_msg.id_dict
    #     self.outputs.task_done()

    #     if disp:
    #         self.onSuccess(id_msg.disp_ID(id_msg))
    #     return id_dict

    def get_ANT_serial_number(self, disp=True):
        self.control_manager.put(m.RequestSerialNumberMessage(),
                                 block=False)
        self.control_manager.join()
        sn_msg = self.outputs_manager.get(block=True)
        sn = sn_msg.serial_number
        self.outputs_manager.task_done()
        if disp:
            self.onSuccess(sn_msg.disp_SN(sn_msg))
        return sn

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

    def add_msg(self, msg):
        dt = datetime.now()
        dt_str = dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.messages.append(f"{dt_str},{msg}")


class Channel(threading.Thread):
    """Channel class to handle IO of a single connection"""

    def __init__(self, cfig_manager,
                 ctrl_manager,
                 tx_manager,
                 out_manager,
                 on_success,
                 on_failure,
                 channel_num=0,
                 network_num=0,
                 network_key=c.ANTPLUS_NETWORK_KEY,
                 channel_type=c.CHANNEL_BIDIRECTIONAL_SLAVE,
                 device_type=0,
                 channel_frequency=2457,
                 channel_msg_freq=4,
                 channel_search_timeout=30):

        super().__init__()
        self.number = channel_num
        # Queue Managers for device level control
        self.cfig_manager = cfig_manager
        self.ctrl_manager = ctrl_manager
        self.tx_mangaer = tx_manager
        self.out_manager = out_manager

        # Callback Assignments
        self.onSuccess = on_success
        self.onFailure = on_failure

        # Channel queues for specific channel actions
        self._ctrl = ANTQueue(self.number)
        self._out = ANTQueue(self.number)
        self._tx = ANTQueue(self.number)
        self.queues = {"ctrl": self._ctrl, "out": self._out, "tx": self._tx}
        self.network = network_num
        self.network_key = network_key
        self._type = channel_type
        self.device_type = device_type
        self.frequency = channel_frequency
        self.msg_freq = channel_msg_freq
        self.search_timeout = channel_search_timeout
        self.first_message_flag = False

        self.cfig_manager.put(m.SetNetworkKeyMessage(self.network,
                                                     self.network_key))
        self.cfig_manager.put(m.AssignChannelMessage(self.number,
                                                     self._type))
        self.cfig_manager.put(m.SetChannelIdMessage(self.number,
                                                    device_type=self.device_type))
        self.cfig_manager.put(m.SetChannelRfFrequencyMessage(self.number,
                                                             self.frequency))
        self.cfig_manager.put(m.ChannelMessagingPeriodMessage(self.number,
                                                              self.msg_freq))
        self.cfig_manager.put(m.ChannelSearchTimeoutMessage(self.number,
                                                            self.search_timeout))
        self.cfig_manager.join()

    def open(self):
        self.ctrl_manager.put(m.OpenChannelMessage(self.number))
        self.ctrl_manager.join()
        # Start Channel thread for processing I/O messages
        self.start()

        return True

    def close(self, timeout=False):
        if not timeout:
            self.ctrl_manager.put(m.CloseChannelMessage(self.number))
            self.ctrl_manager.join()

        else:
            sleep(0.5)

        print("Do we get here?")
        self.cfig_manager.put(m.UnassignChannelMessage(self.number))
        self.cfig_manager.join()

    def run(self):
        """Run method for channel thread. Process inputs and outputs to main
        device thread"""

        # Channel creation starts with waiting for first successful message
        self._out.put("Blocking until First Message")
        self._out.join()

        # Thread will reactivate once an item has been recognized and removed
        # from the queue. If the channel times out, the pump will place
        # the error message back into the output queue

        try:
            err = self._out.get(block=True, timeout=0.5)
        except Empty:
            pass

        else:
            # Close channel if timeout is recieved
            if isinstance(err, ex.RxSearchTimeout):
                self._out.task_done()
                self._out.put("Temp String")
                self._out.join()
                self.close(timeout=True)
                return
                # TODO: Emit signal to indicate channel has timed out

        self.onSuccess("First Message Recieved!\n"
                       f"Idenfiying Channel {self.number} Properties...")
        # Identify channel parameters
        self.id = self.get_ID(disp=True)
        self.status = self.get_status(disp=True)

        # TODO: add continuous run loop after proper config
        while True:
            sleep(0.1)
            pass

    def get_ID(self, disp=False):
        """Request channel ID properties from node on established connection.

        """
        self._ctrl.put(m.RequestChannelStatusMessage(self.number),
                       block=False)
        self._ctrl.join()
        stat_msg = self._out.get(block=True)
        self._out.task_done()
        stat_dict = stat_msg.status_dict
        if disp:
            self.onSuccess(stat_msg.disp_status(stat_msg))
        return stat_dict

    def get_status(self, disp=False):
        """Request channel status from node and return properties.

        """
        self._ctrl.put(m.RequestChannelIDMessage(self.number),
                       block=False)
        self._ctrl.join()
        id_msg = self._out.get(block=True)
        id_dict = id_msg.id_dict
        self._out.task_done()

        if disp:
            self.onSuccess(id_msg.disp_ID(id_msg))
        return id_dict


class EventHook(object):

    def __init__(self):
        self.__handlers = []

    def __iadd__(self, handler):
        self.__handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.__handlers.remove(handler)
        return self

    def fire(self, *args, **keywargs):
        for handler in self.__handlers:
            handler(*args, **keywargs)

    def clearObjectHandlers(self, inObject):
        for theHandler in self.__handlers:
            if theHandler.im_self == inObject:
                self -= theHandler


class ANTQueue(Queue):
    """
    Subclass of threading.queue class with additonal attributes specific to
    handling multiple channels of ANT communication. Once a channel has been
    initialized, messages should be processed in an out of channel queues to
    organize blocking .join() statements when awaiting a device event or
    response
    """

    def __init__(self, channel_num):
        # Initailzie Queue object superclass
        super().__init__()
        self.channel_number = channel_num


class QueueManager(Queue):
    """
    Manage multiple queues across threads to ensure messages and information
    is correctly being translated and recieved across channels
    """

    def __init__(self, node, name):
        super().__init__()
        self._node = node  # Node object
        self.waiters = []  # array of waiter response messages and callbacks
        self.name = name  # Key of the matching channel queue type

    @property
    def channels(self):
        return self._node._channels

    def send_message(self, channel_num=None, unload=False):
        """Send messages to the USB driver from queue

        Parameters
        ----------
        waiters: list
            List of messages awaiting some form of response

        driver: Driver
            USB driver communicating with device

        channel_num: int
            Channel number initiating the request. This will define if a channel
            thread is awaiting a response to an outgoing message. a None value
            indicates that no specific channel requested this message

        unload: Bool
            Unloads all contents of the queue into the device if True
        """
        driver = self._node._pump._driver

        if unload:
            while not self.empty():
                self.send_message(channel_num=None)

        try:
            # Grab messages from input queue
            outMsg = self.get(block=False)
            driver.write(outMsg)

            # Special case for reset message
            if outMsg.type == c.MESSAGE_SYSTEM_RESET:
                # Wait for system to finish reset before doing anything
                sleep(0.6)
                return

        except Empty:
            pass

        except Exception as e:
            raise e

        else:
            # Create waiter object for waiter structure
            w = Waiter(outMsg, channel=channel_num)
            # Append message and callback to waiter array
            self.waiters.append(w)

            if self._node._pump._debug:
                print(f'Message Sent: {outMsg}')

    def send_channel_messages(self):
        """Grab and send messages waiting in channel queues"""

        for channel in self.channels:
            if channel is None:
                continue

            try:
                # Grab messages from queue
                msg = channel.queues[self.name].get(block=False)

            except Empty:
                continue

            except Exception as e:
                raise e

            else:
                self.put(msg)
                self.send_message(channel_num=channel.number)

    def remove_task(self, channel, waiter=None):
        """Remove task from proper queue and corresponding waiter object"""
        if channel is not None:
            self.channels[channel].queues[self.name].task_done()

        else:
            self.task_done()

        if waiter is not None:
            self.waiters.remove(waiter)

    def output_msg(self, message, channel):
        if channel is not None:
            self.channels[channel].queues[self.name].put(message)

        else:
            self.put(message)


class Waiter:
    """Contain information on messages waiting responses"""

    def __init__(self, message, channel=None):
        self.message = message
        self.callback = message.callback
        self.channel = channel
