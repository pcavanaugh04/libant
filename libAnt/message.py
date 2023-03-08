from libAnt.constants import *


class Message:
    def __init__(self, type: int, content: bytes):
        self._type = type
        self._content = content
        self.callback = None
        self.reply_type = None  # Field to indicate if message expects a reply
        self.source = ''

    def __len__(self):
        return len(self._content)

    def __iter__(self):
        return self._content

    def __str__(self):
        return '({:02X}): '.format(self._type) + ' '.join('{:02X}'.format(x) for x in self._content)

    def checksum(self) -> int:
        chk = MESSAGE_TX_SYNC ^ len(self) ^ self._type
        for b in self._content:
            chk ^= b
        return chk

    def encode(self) -> bytes:
        b = bytearray([MESSAGE_TX_SYNC, len(self), self._type])
        b.extend(self._content)
        b.append(self.checksum())
        return bytes(b)

    @property
    def type(self) -> int:
        return self._type

    @property
    def content(self) -> bytes:
        return self._content


# %% Config Messages
class SetNetworkKeyMessage(Message):
    def __init__(self, channel: int, key: bytes = ANTPLUS_NETWORK_KEY):
        content = bytearray([channel])
        content.extend(key)
        super().__init__(MESSAGE_NETWORK_KEY, bytes(content))
        self.key = key
        self.reply_type = MESSAGE_CHANNEL_EVENT
        self.callback = SetNetworkKeyMessage.network_success


    def network_success(msg):
        if not msg.type == MESSAGE_CHANNEL_EVENT:
            return(f"Error: Unexpected Message Type {msg.type}")
        if not msg.content[1] == MESSAGE_NETWORK_KEY:
            return
        if msg.content[2] == 0:
            return(f'Network Key Set to: {ANTPLUS_NETWORK_KEY}')
        # else:
        #     return(process_error_code(msg.content[2]))


class AssignChannelMessage(Message):
    def __init__(self, channel: int, type: int, network: int = 0, extended: int = None):
        content = bytearray([channel, type, network])
        if extended is not None:
            content.append(extended)
        super().__init__(MESSAGE_CHANNEL_ASSIGN, bytes(content))


class SetChannelIdMessage(Message):
    def __init__(self, channel: int, deviceNumber: int = 0, deviceType: int = 0, transType: int = 0):
        content = bytearray([channel])
        content.extend(deviceNumber.to_bytes(2, byteorder='big'))
        content.append(deviceType)
        content.append(transType)
        super().__init__(MESSAGE_CHANNEL_ID, bytes(content))


class SetChannelRfFrequencyMessage(Message):
    def __init__(self, channel: int, frequency: int = 2457):
        content = bytes([channel, frequency - 2400])
        super().__init__(MESSAGE_CHANNEL_FREQUENCY, content)


class EnableExtendedMessagesMessage(Message):
    def __init__(self, enable: bool = True):
        content = bytes([0, int(enable)])
        super().__init__(MESSAGE_ENABLE_EXT_RX_MESSAGES, content)


class LibConfigMessage(Message):
    def __init__(self, rxTimestamp: bool = True, rssi: bool = True, channelId: bool = True):
        config = 0
        if rxTimestamp:
            config |= EXT_FLAG_TIMESTAMP
        if rssi:
            config |= EXT_FLAG_RSSI
        if channelId:
            config |= EXT_FLAG_CHANNEL_ID
        super().__init__(MESSAGE_LIB_CONFIG, bytes([0, config]))


# %% Control Messages
class SystemResetMessage(Message):
    def __init__(self):
        super().__init__(MESSAGE_SYSTEM_RESET, b'\x00') # Pcavana 2 March 2023 - Change content to b'\x00'
        self.expect_reply = True
        self.source = 'Host'
        self.callback = StartUpMessage.disp_startup
        self.reply_type = MESSAGE_STARTUP


class OpenRxScanModeMessage(Message):
    def __init__(self):
        super().__init__(MESSAGE_OPEN_RX_SCAN_MODE, bytes([0]))


# %%% Request Messages
class RequestMessage(Message):
    def __init__(self, content: bytes):
        super().__init__(MESSAGE_CHANNEL_REQUEST, content)
        self.expect_reply = True
        self.source = 'Host'


class RequestCapabilitiesMessage(RequestMessage):
    def __init__(self):
        content = bytearray([0, MESSAGE_CAPABILITIES])
        super().__init__(content)
        self.source = 'Host'
        self.callback = CapabilitiesMessage.disp_capabilities
        self.reply_type = MESSAGE_CAPABILITIES


class RequestChannelStatusMessage(RequestMessage):
    def __init__(self, channel_num: int):
        content = bytearray([channel_num, MESSAGE_CHANNEL_STATUS])
        super().__init__(content)
        self.source = 'Host'
        self.callback = ChannelStatusMessage.disp_status
        self.reply_type = MESSAGE_CHANNEL_STATUS


class RequestChannelIDMessage(RequestMessage):
    def __init__(self, channel_num: int):
        content = bytearray([channel_num, MESSAGE_CHANNEL_ID])
        super().__init__(content)
        self.source = 'Host'
        self.callback = ChannelIDMessage.disp_ID
        self.reply_type = MESSAGE_CHANNEL_ID


class RequestSerialNumberMessage(RequestMessage):
    def __init__(self):
        content = bytearray([0, MESSAGE_SERIAL_NUMBER])
        super().__init__(content)
        self.source = 'Host'
        self.callback = SerialNumberMessage.disp_SN
        self.reply_type = MESSAGE_SERIAL_NUMBER


# %% Data Messages

class BroadcastMessage(Message):
    def __init__(self, type: int, content: bytes):
        self.flag = None
        self.deviceNumber = self.deviceType = self.transType = None
        self.rssiMeasurementType = self.rssi = self._rssiThreshold = None
        self.rssi = None
        self.rssiThreshold = None
        self.rxTimestamp = None
        self.channel = None
        self.extendedContent = None

        super().__init__(type, content)

    def build(self, raw: bytes):
        self._type = MESSAGE_CHANNEL_BROADCAST_DATA
        self.channel = raw[0]
        self._content = raw[1:9]
        if len(raw) > 9:  # Extended message
            self.flag = raw[9]
            self.extendedContent = raw[10:]
            offset = 0
            if self.flag & EXT_FLAG_CHANNEL_ID:
                self.deviceNumber = int.from_bytes(self.extendedContent[:2], byteorder='little', signed=False)
                self.deviceType = self.extendedContent[2]
                self.transType = self.extendedContent[3]
                offset += 4
            if self.flag & EXT_FLAG_RSSI:
                rssi = self.extendedContent[offset:(offset + 3)]
                self.rssiMeasurementType = rssi[0]
                self.rssi = rssi[1]
                self.rssiThreshold = rssi[2]
                offset += 3
            if self.flag & EXT_FLAG_TIMESTAMP:
                self.rxTimestamp = int.from_bytes(self.extendedContent[offset:],
                                                  byteorder='little', signed=False)
        return self

    def checksum(self) -> int:
        pass

    def encode(self) -> bytes:
        pass


# %% Notification Messages
class StartUpMessage:
    def __init__(self, content: bytes):
        super().__init__(MESSAGE_STARTUP, content)

    def disp_startup(msg):
        if not msg.type == MESSAGE_STARTUP:
            return(f"Error: Unexpected Message Type {msg.type}")
        start_bits = bit_array(msg.content[0])
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
        return(start_str[0:-1])


class SerialErrorMessage:
    def __init__(self, content: bytes):
        super().__init__(MESSAGE_SERIAL_ERROR, content)

# TODO: Unpack Serial Error Message
    def disp_serial_error(msg):
        if not msg.type == MESSAGE_SERIAL_ERROR:
            return(f"Error: Unexpected Message Type {msg.type}")
        start_bits = bit_array(msg.content[0])
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
        return(start_str[0:-1])


# %% Requested Response Messages
class CapabilitiesMessage(Message):
    def __init__(self, content: bytes):
        super().__init__(MESSAGE_CAPABILITIES, content)
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

    def disp_capabilities(msg):
        if not msg.type == MESSAGE_CAPABILITIES:
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
    """ANT Protocol Section 9.5.7.1."""

    def __init__(self, content: bytes):
        super().__init__(MESSAGE_CHANNEL_STATUS, content)
        self.channel_num = int(content[0])
        channel_status = bit_array(content[1])
        match bits_2_num(channel_status[6:8]):
            case 0:
                self.channel_state = 'Un-Assigned'
            case 1:
                self.channel_state = 'Assigned'
            case 2:
                self.channel_state = 'Searching'
            case 3:
                self.channel_state = 'Tracking'
        self.network_number = bits_2_num(channel_status[4:6])
        self.channel_type = bits_2_num(channel_status[0:4])
        self.source = 'ANT'

    def disp_status(msg):
        if not msg.type == MESSAGE_CHANNEL_STATUS:
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

        return status_str


class ChannelIDMessage(Message):
    """ANT Protocol Section 9.5.7.2."""
    # TODO: Implement Extended Device number field in Tx Type

    def __init__(self, content: bytes):
        super().__init__(MESSAGE_CHANNEL_ID, content)
        self.channel_num = int(content[0])
        self.device_number = int.from_bytes((content[1].to_bytes(1, 'little') +
                                            content[2].to_bytes(1, 'little')),
                                            byteorder='little')
        self.device_type = int(content[3])
        self.tx_type = bit_array(content[4])

    def disp_ID(msg):
        if not msg.type == MESSAGE_CHANNEL_ID:
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

        return id_str


class SerialNumberMessage(Message):
    def __init__(self, content: bytes):
        super().__init__(MESSAGE_SERIAL_NUMBER, content)
        x = b''
        for i in content:
            x += i.to_bytes(1, 'little')
        self.serial_number = int.from_bytes(x, byteorder='little')
        self.source = 'ANT'

    def disp_SN(msg):
        if not msg.type == MESSAGE_SERIAL_NUMBER:
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
