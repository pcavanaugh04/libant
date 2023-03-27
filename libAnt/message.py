import libAnt.constants as c
import libAnt.exceptions as e


class Message:
    """Parent class of general ANT Message format object.

    Object to represent an ANT message in a format that can be sent via serial
    to an ANT device and communicate with other ANT devices. Messages consist
    of a sync byte, length byte, channel byte, message content and a checksum
    consistent with ANT Section 7.1. Class has custom attributes to return
    useful information about a message in readable format such as length and
    display functions.
    """

    def __init__(self, type: int, content: bytes):
        self._type = type  # Message type indicated in constants file
        self._content = content  # Byte array of Message content
        self.callback = self.device_reply  # Function called on message success
        self.reply_type = None  # Field to indicate if message expects a reply
        self.source = ''  # Descriptive field to know where message comes from

    def __len__(self):
        "Length property updated to only show length of content attribute"
        return len(self._content)

    def __iter__(self):
        "Iterating message object only examines values in content attribute"
        return self._content

    def __str__(self):
        """
        Printing or casting object to string generates hex value of message
        type and lists hex values of content attribute.

        Returns
        -------
        str
            Formatted message containing message type and content.

        """
        return ('({:02X}): '.format(self._type) +
                ' '.join('{:02X}'.format(x) for x in self._content))

    def checksum(self) -> int:
        """Create checksum byte to ensure message is recieved properly.

        Checksum is produced from XOR operation of all bytes in the message.
        """
        chk = c.MESSAGE_TX_SYNC ^ len(self) ^ self._type
        for b in self._content:
            chk ^= b
        return chk

    def encode(self) -> bytes:
        """
        Encode message into standard ANT message format consisting of:
        Sync byte
        Length byte
        Message Type byte
        Content byte array (Channel number will be first byte of this array)
        Checksum byte

        Returns
        -------
        bytes
            Formatted byte object ready to sent to ANT device over serial.

        """
        b = bytearray([c.MESSAGE_TX_SYNC, len(self), self._type])
        b.extend(self._content)
        b.append(self.checksum())
        return bytes(b)

    def device_reply(self, msg, msg_type):
        """
        Callback to check status of a set network key message request

        Parameters
        ----------
        msg : Message
            Event message from ANT device containing status of request.

        Returns
        -------
        str
            Confirmation or Error message based on ANT reply.

        """
        if msg.type == c.MESSAGE_SERIAL_ERROR:
            raise e.SerialError()
            return(SerialErrorMessage.disp_serial_error(msg))
        if not msg.type == c.MESSAGE_CHANNEL_EVENT:
            return(f"Error: Unexpected Message Type {hex(msg.type)}")
        if not msg.content[1] == (msg_type):
            return(f"Error: Unexpected Message Type {hex(msg.type)}")
        if msg.content[2] == 0:
            return(f'Message Success. Type: {hex(msg_type)}')
        else:
            return(process_event_code(msg.content[2]))

    @property
    def type(self) -> int:
        return self._type

    @property
    def content(self) -> bytes:
        return self._content


# %% Config Messages
class SetNetworkKeyMessage(Message):
    """ANT Section 9.5.2.7 (0x46)

    Message to assign the network key to a network number on an ANT device.
    Networks allow for multiple connections and sharing information between
    nodes. Nodes can only connect to other nodes with the same network key.
    The default public network is set to 0, but example private networks such
    as ANT+ devices have their own network key. Hardware is typically limited
    in the number of networks they can store as assignments.
    """

    def __init__(self, network_number: int,
                 key: bytes = c.ANTPLUS_NETWORK_KEY):
        content = bytearray([network_number])
        content.extend(key)
        super().__init__(c.MESSAGE_NETWORK_KEY, bytes(content))
        self.key = key
        self.reply_type = c.MESSAGE_CHANNEL_EVENT
        self.source = 'Host'


class UnassignChannelMessage(Message):
    """ANT Section 9.5.2.1 (0x41)

    Message to unassign a channel on an ANT device. Channels must be unassigned
    and reconfigured to be used again.
    """

    def __init__(self, channel: int):
        content = bytearray([channel])
        super().__init__(c.MESSAGE_CHANNEL_UNASSIGN, bytes(content))
        self.reply_type = c.MESSAGE_CHANNEL_EVENT
        # self.callback = self.device_reply
        self.source = 'Host'


class AssignChannelMessage(Message):
    """ANT Section 9.5.2.2 (0x42)

    Message to reserve a channel number on an ANT device for communication.
    Message specifies network number, channel type and channel number.
    """

    def __init__(self, channel: int,
                 type: int,
                 network: int = 0,
                 extended: int = None):
        content = bytearray([channel, type, network])
        if extended is not None:
            content.append(extended)
        super().__init__(c.MESSAGE_CHANNEL_ASSIGN, bytes(content))
        self.reply_type = c.MESSAGE_CHANNEL_EVENT
        self.source = 'Host'


class SetChannelIdMessage(Message):
    """ANT Section 9.5.2.3 (0x51)

    Message to configure a channel based on the expected device connection.
    """

    def __init__(self, channel: int,
                 device_number: int = 0,
                 pairing_bit: int = 0,
                 device_type: int = 0,
                 tx_type: int = 0):
        content = bytearray([channel])
        content.extend(device_number.to_bytes(2, byteorder='little'))
        content.append(int(pairing_bit)*128 + int(device_type))
        content.append(tx_type)
        super().__init__(c.MESSAGE_CHANNEL_ID, bytes(content))
        self.reply_type = c.MESSAGE_CHANNEL_EVENT
        self.source = 'Host'


class ChannelMessagingPeriodMessage(Message):
    """ANT Section 9.5.2.4 (0x43)

    Configure messaging period, or the data frequency, of a channel.
    Parameters include channel number and messaging period. Messaging
    period is set to (messaging_period_seconds)*32768
    """

    def __init__(self, channel: int, frequency: int = 4):
        """
        Constructor for set messaging period message.

        Parameters
        ----------
        channel : int
            Channel number on device being set.
        frequency : int, optional
            Channel messaging frequency [hz] The default value is 4hz

        Returns
        -------
        None

        """
        content = bytearray([channel])
        content.extend(int(1/frequency*32768).to_bytes(2, byteorder='little'))
        super().__init__(c.MESSAGE_CHANNEL_PERIOD, content)
        self.reply_type = c.MESSAGE_CHANNEL_EVENT
        self.source = 'Host'


class ChannelSearchTimeoutMessage(Message):
    """ANT Section 9.5.2.5 (0x44)

    Configure search timeout for recieve message searching. Parameter sent to
    device = time/2.5
    """

    def __init__(self, channel: int, timeout: int = 30):
        """
        Constructor for set messaging period message.

        Parameters
        ----------
        channel : int
            Channel number on device being set.
        timeout : int, optional
            Search timeout [s]. Value divided by 2.5 to send to device

        Returns
        -------
        None

        """
        content = bytes([channel, int(timeout/2.5)])
        super().__init__(c.MESSAGE_CHANNEL_SEARCH_TIMEOUT, content)
        self.reply_type = c.MESSAGE_CHANNEL_EVENT
        self.source = 'Host'


class SetChannelRfFrequencyMessage(Message):
    """ANT Section 9.5.2.6 (0x54)

    Message to configure RF frequency band channel will communicate with.
    Both devices in a channel must have same RF frequency assigned
    """

    def __init__(self, channel: int, frequency: int = 2457):
        """
        Construct RF frequency message

        Parameters
        ----------
        channel : int
            Channel number on device being set.
        frequency : int, optional
            Value of Frequency in MHz. Parameter sent to device is freq - 2400
        Returns
        -------
        None
        """

        content = bytes([channel, frequency - 2400])
        super().__init__(c.MESSAGE_CHANNEL_FREQUENCY, content)
        self.reply_type = c.MESSAGE_CHANNEL_EVENT
        self.source = 'Host'


class EnableExtendedMessagesMessage(Message):
    """ANT Section 9.5.2.17 (0x66)

    Message to configure a channel based on the expected device connection.
    """

    def __init__(self, enable: bool = True):
        content = bytes([0, int(enable)])
        super().__init__(c.MESSAGE_ENABLE_EXT_RX_MESSAGES, content)
        self.reply_type = c.MESSAGE_CHANNEL_EVENT
        self.source = 'Host'


class LibConfigMessage(Message):
    """ANT Section 9.5.2.20 (0x6E)

    Tell ANT to utilize extended packet usage
    """

    def __init__(self, rx_timestamp: bool = True,
                 rssi: bool = True,
                 channel_ID: bool = True):
        config = 0
        if rx_timestamp:
            config |= c.EXT_FLAG_TIMESTAMP
        if rssi:
            config |= c.EXT_FLAG_RSSI
        if channel_ID:
            config |= c.EXT_FLAG_CHANNEL_ID
        super().__init__(c.MESSAGE_LIB_CONFIG, bytes([0, config]))
        self.reply_type = c.MESSAGE_CHANNEL_EVENT
        self.source = 'Host'


# %% Control Messages ANT Section 9.5.4
class ResetSystemMessage(Message):
    """ANT Section 9.5.4.1 (0x4A)

    Reset device and put in low-power state. Terminate all channels and cease
    all communication. Most devices will reply with a startup message
    """

    def __init__(self):
        super().__init__(c.MESSAGE_SYSTEM_RESET, bytes([0]))
        self.reply_type = c.MESSAGE_STARTUP
        self.source = 'Host'
        self.callback = StartUpMessage


class OpenChannelMessage(Message):
    """ANT Section 9.5.4.2 (0x4B)

    Open a channel on a device. Channel must have been assigned and configured
    previously.
    """

    def __init__(self, channel: int = 0):
        """
        Construct Open Channel message

        Parameters
        ----------
        channel : int
            Channel number on device to open

        Returns
        -------
        None
        """
        super().__init__(c.MESSAGE_CHANNEL_OPEN, bytes([channel]))
        self.reply_type = c.MESSAGE_CHANNEL_EVENT
        self.source = 'Host'


class CloseChannelMessage(Message):
    """ANT Section 9.5.4.3 (0x4C)

    Close a channel on a device. Host will recieve two replies: initially a
    RESPONSE_NO_ERROR followed by an EVENT_CHANNEL_CLOSED. Host needs to wait
    until a channel close message is recieved to perform any new operations
    """

    def __init__(self, channel: int = 0):
        """
        Construct Open Channel message

        Parameters
        ----------
        channel : int
            Channel number on device to open

        Returns
        -------
        None
        """
        super().__init__(c.MESSAGE_CHANNEL_CLOSE, bytes([channel]))
        self.reply_type = c.MESSAGE_CHANNEL_EVENT
        self.source = 'Host'
        # TODO: Implement Callback to wait for both expected responses to close


class OpenRxScanModeMessage(Message):
    """ANT Section 9.5.4.5 (0x5B)

    Opens Channel 0 in continuous scanning mode. Device will recieve all
    messages from any device in range configured to the same channel ID
    """

    def __init__(self, sync_channel_packets_only: bool = False):
        super().__init__(c.MESSAGE_OPEN_RX_SCAN_MODE,
                         bytes([0, sync_channel_packets_only]))
        self.reply_type = c.MESSAGE_CHANNEL_EVENT
        self.source = 'Host'


class SleepMessage(Message):
    """ANT Section 9.5.4.6 (0xC5)

    Put device in sleep mode (ultra low power state). Not appliciable to USB
    devices.
    """

    def __init__(self):
        super().__init__(c.MESSAGE_SLEEP, bytes([0]))
        self.source = 'Host'
        self.callback = StartUpMessage.disp_startup


# %%% Request Messages
class RequestMessage(Message):
    """ANT Section 9.5.4.4 (0x4D)

    Message sent to request specific information from the device. ANT will
    with specific message page based on request. Follwing subclasses of request
    message correspond to avaliable request message types and expected replies
    """

    def __init__(self, content: bytes):
        super().__init__(c.MESSAGE_CHANNEL_REQUEST, content)
        self.source = 'Host'


class RequestCapabilitiesMessage(RequestMessage):
    def __init__(self):
        content = bytearray([0, c.MESSAGE_CAPABILITIES])
        super().__init__(content)
        self.callback = CapabilitiesMessage
        self.reply_type = c.MESSAGE_CAPABILITIES


class RequestChannelStatusMessage(RequestMessage):
    def __init__(self, channel_num: int):
        content = bytearray([channel_num, c.MESSAGE_CHANNEL_STATUS])
        super().__init__(content)
        self.callback = ChannelStatusMessage
        self.reply_type = c.MESSAGE_CHANNEL_STATUS


class RequestChannelIDMessage(RequestMessage):
    def __init__(self, channel_num: int):
        content = bytearray([channel_num, c.MESSAGE_CHANNEL_ID])
        super().__init__(content)
        self.callback = ChannelIDMessage
        self.reply_type = c.MESSAGE_CHANNEL_ID


class RequestSerialNumberMessage(RequestMessage):
    def __init__(self):
        content = bytearray([0, c.MESSAGE_SERIAL_NUMBER])
        super().__init__(content)
        self.callback = SerialNumberMessage
        self.reply_type = c.MESSAGE_SERIAL_NUMBER


# %% Data Messages

class BroadcastMessage(Message):
    """ANT Section 9.5.5.1

    Braodcast messages are one-way, un-acknowledged data packets sent across a
    channel. The data payload is 8 bytes and can be configred to contain
    extended fields.
    """

    def __init__(self, type: int, content: bytes):
        self.flag = None
        self.device_number = self.device_type = self.tx_type = None
        self.rssi_measurement_type = self.rssi = self._rssi_threshold = None
        self.rssi = None
        self.rssi_threshold = None
        self.rx_timestamp = None
        self.channel = None
        self.ext_content = None
        super().__init__(type, content)

    def build(self, raw: bytes):
        """Construct broadcast message to a standard format.

        The build method extracts information from the broadcast message object
        and reformats the object into a standard, 8byte payload. This method
        can process extended data packets.

        Parameters
        ----------
        raw : bytes
            A 9 byte array consisting of channel number raw[0] and message
            content raw[1:9]

        Returns
        -------
        self
            returns an updated version of the broadcast message object for
            assignment

        """
        self._type = c.MESSAGE_CHANNEL_BROADCAST_DATA
        self.channel = raw[0]
        self._content = raw[1:9]
        if len(raw) > 9:  # Extended message
            self.flag = raw[9]
            self.ext_content = raw[10:]
            offset = 0
            if self.flag & c.EXT_FLAG_CHANNEL_ID:
                self.device_number = int.from_bytes(self.ext_content[:2],
                                                    byteorder='little',
                                                    signed=False)
                self.device_type = self.ext_content[2]
                self.tx_type = self.ext_content[3]
                offset += 4
            if self.flag & c.EXT_FLAG_RSSI:
                rssi = self.ext_content[offset:(offset + 3)]
                self.rssi_measurement_type = rssi[0]
                self.rssi = rssi[1]
                self.rssi_threshold = rssi[2]
                offset += 3
            if self.flag & c.EXT_FLAG_TIMESTAMP:
                self.rx_timestamp = int.from_bytes(self.ext_content[offset:],
                                                   byteorder='little',
                                                   signed=False)
        return self

    def checksum(self) -> int:
        pass

    def encode(self) -> bytes:
        pass


class AcknowledgedMessage(Message):
    """ANT Section 9.5.5.2 (0x4F)

    Send from master or slave to recieving node when the success or failure of
    a message needs to be known. This message is sometimes used by different
    device profiles to configure content and share control information from
    slave to master devices.
    """

    def __init__(self, channel_num, content: bytes):
        content = bytes([channel_num]) + content
        super().__init__(c.MESSAGE_CHANNEL_ACKNOWLEDGED_DATA, content)


# %% Notification Messages
class StartUpMessage(Message):
    """ANT Section 9.5.3.1 (0x6F)

    Message sent by ANT upond device startup or after reset event. Message
    contains information on reset type
    """

    def __init__(self, content):
        content = bytes(content)
        super().__init__(c.MESSAGE_STARTUP, content)
        self.source = 'ANT'
        self.callback = self.disp_startup

    def disp_startup(self, msg):
        """Display startup message from device with associated start-up codes

        This method can be chosed to be printed to the success callback where
        it is called.

        Returns
        -------
        start_str : str
            Formatted message for display

        """
        start_bits = bit_array(self.content[0])
        start_str = 'Device Startup Successful. Reset type:\n'
        if start_bits[0]:
            start_str += '\tHARDWARE_RESET_LINE\n'
        if start_bits[1]:
            start_str += '\tWATCH_DOG_RESET\n'
        if start_bits[5]:
            start_str += '\tCOMMAND_RESET\n'
        if start_bits[6]:
            start_str += '\tSYNCHRONOUS_RESET\n'
        if start_bits[7]:
            start_str += '\tSUSPEND_RESET\n'
        return start_str.strip()


class SerialErrorMessage(Message):
    """ANT Section 9.5.3.2 (0xAE)

    Message sent by ANT to indicate a standard message packet was improperly
    formatted. Message contains error code in place of channel byte and copies
    the sent message as the rest of the message content
    """

    def __init__(self, content: bytes):
        super().__init__(c.MESSAGE_SERIAL_ERROR, content)
        self.source = "ANT"

    def disp_serial_error(msg):
        if not msg.type == c.MESSAGE_SERIAL_ERROR:
            return(f"Error: Unexpected Message Type {msg.type}")
        err_str = 'ERROR: Serial Error: '
        match msg[0]:
            case 0:
                err_str += ('First message byte does not match ANT'
                            ' serial message Tx synch byte (0xA4)')
            case 2:
                err_str += ('Checksum of ANT message is incorrect')
            case 3:
                err_str += ('Size of ANT message is too large')

        err_str += '\nInvalid Message: {str(msg)}\n'
        return(err_str)


# %% Requested Response Messages
class CapabilitiesMessage(Message):
    """ANT Section 9.5.7.4 (0x54)

    Message sent from ANT in response to capabilities request message. Message
    contains summary of ANT device capabilities. See ANT Document for full
    implementation
    """

    def __init__(self, content: bytes):
        super().__init__(c.MESSAGE_CAPABILITIES, content)
        self.capabilities_dict = {}
        capabilities_keys = ['max_channels', 'max_networks', 'std_options',
                             'adv_options', 'adv_options2',
                             'max_sensRcore_channels', 'adv_options3',
                             'adv_options4']
        for i, value in enumerate(content):
            if 'options' in capabilities_keys[i]:
                value = bit_array(value)
            self.capabilities_dict[capabilities_keys[i]] = value
        self.source = 'ANT'
        self.callback = self.disp_capabilities

    def disp_capabilities(self, msg):
        if not msg.type == c.MESSAGE_CAPABILITIES:
            return(f"Error: Unexpected Message Type {msg.type}")

        cap_msg = CapabilitiesMessage(msg.content)
        cap_str = "\nANT Device Capabilities:\n"
        for key, value in cap_msg.capabilities_dict.items():
            match key:
                case 'std_options':
                    cap_str += (f'\t{key}:\n'
                                f'\t\tCAPABILITIES_NO_RECEIVE_CHANNELS: {bool(value[0])}\n'
                                f'\t\tCAPABILITIES_NO_TRANSMIT_CHANNELS: {bool(value[1])}\n'
                                f'\t\tCAPABILITIES_NO_RECEIVE_MESSAGES: {bool(value[2])}\n'
                                f'\t\tCAPABILITIES_NO_TRANSMIT_MESSAGES: {bool(value[3])}\n'
                                f'\t\tCAPABILITIES_NO_ACKD_MESSAGES: {bool(value[4])}\n'
                                f'\t\tCAPABILITIES_NO_BURST_MESSAGES: {bool(value[5])}\n')

                case 'adv_options':
                    cap_str += (f'\t{key}:\n'
                                f'\t\tCAPABILITIES_NETWORK_ENABLED: {bool(value[1])}\n'
                                f'\t\tCAPABILITIES_SERIAL_NUMBER_ENABLED: {bool(value[3])}\n'
                                f'\t\tCAPABILITIES_PER_CHANNEL_TX_POWER_ENABLED: {bool(value[4])}\n'
                                f'\t\tCAPABILITIES_LOW_PRIORITY_SEARCH_ENABLED: {bool(value[5])}\n'
                                f'\t\tCAPABILITIES_SCRIPT_ENABLED: {bool(value[6])}\n'
                                f'\t\tCAPABILITIES_SEARCH_LIST_ENABLED: {bool(value[7])}\n')

                case 'adv_options2':
                    cap_str += (f'\t{key}:\n'
                                f'\t\tCAPABILITIES_LED_ENABLED: {bool(value[0])}\n'
                                f'\t\tCAPABILITIES_EXT_MESSAGE_ENABLED: {bool(value[1])}\n'
                                f'\t\tCAPABILITIES_SCAN_MODE_ENABLED: {bool(value[2])}\n'
                                f'\t\tCAPABILITIES_PROX_SEARCH_ENABLED: {bool(value[4])}\n'
                                f'\t\tCAPABILITIES_EXT_ASSIGN_ENABLED: {bool(value[5])}\n'
                                f'\t\tCAPABILITIES_FS_ANT_FS_ENABLED: {bool(value[6])}\n'
                                f'\t\tCAPABILITIES_FIT1_ENABLED: {bool(value[7])}\n')

                case 'adv_options3':
                    cap_str += (f'\t{key}:\n'
                                f'\t\tCAPABILITIES_ADVANCED_BURST_ENABLED: {bool(value[0])}\n'
                                f'\t\tCAPABILITIES_EVENT_BUFFERING_ENABLED: {bool(value[1])}\n'
                                f'\t\tCAPABILITIES_EVENT_FILTERING_ENABLED: {bool(value[2])}\n'
                                f'\t\tCAPABILITIES_HIGH_DUTY_SEARCH_ENABLED: {bool(value[3])}\n'
                                f'\t\tCAPABILITIES_SEARCH_SHARING_ENABLED: {bool(value[4])}\n'
                                f'\t\tCAPABILITIES_SELECTIVE_DATA_UPDATES_ENABLED: {bool(value[6])}\n'
                                f'\t\tCAPABILITIES_ENCRYPTED_CHANNEL_ENABLED: {bool(value[7])}\n')

                case 'adv_options4':
                    cap_str += (f'\t{key}:\n'
                                f'\t\tCAPABILITIES_RFACTIVE_NOTIFICATION_ENABLED: {bool(value[0])}\n')

                case _:
                    cap_str += f'\t{key}: {value}\n'

        return(cap_str)


class ChannelStatusMessage(Message):
    """ANT Section 9.5.7.1 (0x52)

    Message sent from ANT in response to channel status request message.
    Message contains channel type, network number and channel state.
    """

    def __init__(self, content: bytes):
        super().__init__(c.MESSAGE_CHANNEL_STATUS, content)
        self.channel_num = int(content[0])
        channel_status = bit_array(content[1])
        match bits_2_num(channel_status[0:2]):
            case 0:
                self.channel_state = 'Un-Assigned'
            case 1:
                self.channel_state = 'Assigned'
            case 2:
                self.channel_state = 'Searching'
            case 3:
                self.channel_state = 'Tracking'
        self.network_number = bits_2_num(channel_status[2:4])
        self.channel_type = bits_2_num(channel_status[4:])
        self.status_dict = {'channel_number': self.channel_num,
                            'channel_state': self.channel_state,
                            'network_number': self.network_number,
                            'channel_type': self.channel_type}
        self.source = 'ANT'

    def disp_status(self, msg):
        if not msg.type == c.MESSAGE_CHANNEL_STATUS:
            return(f"Error: Unexpected Message Type {msg.type}")

        status_msg = ChannelStatusMessage(msg.content)
        status_str = "\nChannel Status:\n"
        status_str += f"\tChannel Number: {status_msg.channel_num}\n"
        # Channel Type ANT Protocol Table 5-1
        match status_msg.channel_type:
            case 0x00:
                status_str += "\tChannel Type: Bidirectional Slave Channel\n"
            case 0x10:
                status_str += "\tChannel Type: Bidirectional Master Channel\n"
            case 0x20:
                status_str += "\tChannel Type: Shared Bidirectional Master Channel\n"
            case 0x30:
                status_str += "\tChannel Type: Shared Bidirectional Master Channel\n"
            case 0x40:
                status_str += "\tChannel Type: Slave Recieve Only Channel\n"
            case 0x50:
                status_str += "\tChannel Type: Master Recieve Only Channel\n"

        # Network Number ANT Protocol Section 5.2.5.1
        status_str += f"\tNetwork Number: {status_msg.network_number}\n"
        # Channel State
        status_str += f"\tChannel State: {status_msg.channel_state}\n"

        return status_str.strip()


class ChannelIDMessage(Message):
    """ANT Section 9.5.7.2 (0x51)

    Message sent from ANT in response to channel ID request message.
    Message contains channel number, device number, device type ID and tx type
    """
    # TODO: Implement Extended Device number field in Tx Type

    def __init__(self, content: bytes):
        super().__init__(c.MESSAGE_CHANNEL_ID, content)
        self.channel_num = int(content[0])
        self.device_number = int.from_bytes((content[1].to_bytes(1, 'little') +
                                            content[2].to_bytes(1, 'little')),
                                            byteorder='little')
        self.device_type = int(content[3])
        self.tx_type = bit_array(content[4])
        self.id_dict = {'channel_number': self.channel_num,
                        'device_number': self.device_number,
                        'device_type': self.device_type,
                        'tx_type': self.device_type}

    def disp_ID(self, msg):
        if not msg.type == c.MESSAGE_CHANNEL_ID:
            return(f"Error: Unexpected Message Type {msg.type}")

        id_msg = ChannelIDMessage(msg.content)
        id_str = "\nChannel ID:\n"
        id_str += f"\tChannel Number: {id_msg.channel_num}\n"
        id_str += f"\tDevice Number: {id_msg.device_number}\n"
        id_str += f"\tDevice Type: {id_msg.device_type}\n"

        # Channel Type ANT Protocol Table 5-2
        match bits_2_num(id_msg.tx_type[6:8]):
            case 0:
                pass
            case 1:
                id_str += "\tTransmission Type: Independent Channel\n"
            case 2:
                id_str += "\tTransmission Type: Shared Channel using 1 byte address\n"
            case 3:
                id_str += "\tTransmission Type: Shared Channel using 2 byte address\n"

        match id_msg.tx_type[5]:
            case 0:
                id_str += "\tUses Global Data Pages: False\n"
            case 1:
                id_str += "\tUses Global Data Pages: True\n"

        return id_str.strip()


class SerialNumberMessage(Message):
    """ANT Section 9.5.7.5 (0x61)

    Return device 4-byte serial number upon request
    """

    def __init__(self, content: bytes):
        super().__init__(c.MESSAGE_SERIAL_NUMBER, content)
        x = b''
        for i in content:
            x += i.to_bytes(1, 'little')
        self.serial_number = int.from_bytes(x, byteorder='little')
        self.source = 'ANT'

    def disp_SN(self, msg):
        if not msg.type == c.MESSAGE_SERIAL_NUMBER:
            return(f"Error: Unexpected Message Type {msg.type}")

        SN_msg = SerialNumberMessage(msg.content)
        sn_str = "\nANT Device Serial Number:\n"
        sn_str += f"\tSerial Number: {SN_msg.serial_number}\n"

        return sn_str


def bit_array(byte):
    """Convert single byte to array of 8 bits

    Parameters
    ----------
    byte : bytes
        Byte to be converted to bits.

    Returns
    -------
    bits : list
        8 element list corresponding to input byte in binary
    """
    byte = int(byte)
    if byte < 0 or byte > 255:
        return (["Error: Input cannot exceed 1 byte"])

    bits = [(byte >> i) & 1 for i in range(8)]

    return bits


def bits_2_num(bit_array):
    """Converts any number of bits in list form to integer

    Parameters
    ----------
    bit_array : list
        list of 1s and 0s to be sliced and converted to int

    Returns
    -------
    int_value : int
        corresponding value as integer
    """
    bit_string = ''.join(str(bit) for bit in bit_array)
    int_value = int(bit_string, 2)

    return int_value


def process_event_code(evt_code):
    match evt_code:
        case c.EVENT_RX_FAIL:
            raise e.RxFail()

        case c.EVENT_TRANSFER_TX_FAILED:
            raise e.TxFail()

        case c.INVALID_MESSAGE:
            raise e.InvalidMessage()

        case c.EVENT_CHANNEL_CLOSED:
            return("Channel Close Success")

        case c.EVENT_TRANSFER_TX_COMPLETED:
            return("Tx Success")

        case c.MESSAGE_SIZE_EXCEEDS_LIMIT:
            raise(e.MessageSizeExceedsLimit())

        case _:
            return(f"Warning: Event Code not yet implemented for :{evt_code}")
