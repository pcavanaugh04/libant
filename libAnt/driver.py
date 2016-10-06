from abc import abstractmethod
from queue import Queue
from threading import Lock, Thread, Event

import math
from serial import Serial, SerialException, SerialTimeoutException

import usb
import time
from struct import *

from libAnt.constants import MESSAGE_TX_SYNC, MESSAGE_CHANNEL_BROADCAST_DATA
from libAnt.message import Message, SystemResetMessage


class DriverException(Exception):
    pass

class Logger:
    def __init__(self, logFile: str):
        self._logFile = logFile
        self._log = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open(self):
        if self._log is not None:
            self.close()
        self._log = open(self._logFile, 'wb')
        self.onOpen()

    def close(self):
        if self._log is not None:
            self.beforeClose()
            self._log.close()
            self.afterClose()

    def log(self, data: bytes):
        self._log.write(self.encodeData(data))

    def onOpen(self):
        pass

    def beforeClose(self):
        pass

    def afterClose(self):
        pass

    def encodeData(self, data):
        return data

class PcapLogger(Logger):
    def onOpen(self):
        # write pcap global header
        magic_number = b'\xD4\xC3\xB2\xA1'
        version_major = 2
        version_minor = 4
        thiszone = b'\x00\x00\x00\x00'
        sigfigs = b'\x00\x00\x00\x00'
        snaplen = b'\xFF\x00\x00\x00'
        network = b'\x01\x00\x00\x00'
        pcap_global_header = Struct('<4shh4s4s4s4s')
        self._log.write(
            pcap_global_header.pack(magic_number, version_major, version_minor, thiszone, sigfigs,
                                    snaplen, network))

    def encodeData(self, data):
        timestamp = time.time()
        frac, whole = math.modf(timestamp)

        ts_sec = int(whole).to_bytes(4, byteorder='little')
        ts_usec = int(frac * 1000 * 1000).to_bytes(4, byteorder='little')
        incl_len = len(data)
        orig_len = incl_len

        pcap_packet_header = Struct('<4s4sll').pack(ts_sec, ts_usec, incl_len, orig_len)
        return pcap_packet_header + data

class Driver:
    """
    The driver provides an interface to read and write raw data to and from an ANT+ capable hardware device
    """

    def __init__(self, logger: Logger = None):
        self._lock = Lock()
        self._logger = logger
        self._openTime = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def isOpen(self) -> bool:
        with self._lock:
            return self._isOpen()

    def open(self) -> None:
        with self._lock:
            if not self._isOpen():
                self._openTime = time.time()
                if self._logger is not None:
                    self._logger.open()
                self._open()

    def close(self) -> None:
        with self._lock:
            if self._isOpen:
                self._close()
                if self._logger is not None:
                    self._logger.close()

    def reOpen(self) -> None:
        with self._lock:
            if self._isOpen():
                self._close()
            self._open()

    def read(self, timeout=None) -> Message:
        # Splits the string into a list of tokens every n characters
        def splitN(str1, n):
            return [str1[start:start + n] for start in range(0, len(str1), n)]

        if not self.isOpen():
            raise DriverException("Device is closed")

        with self._lock:
            while True:
                sync = self._read(1, timeout=timeout)[0]
                if sync is not MESSAGE_TX_SYNC:
                    continue
                length = self._read(1, timeout=timeout)[0]
                type = self._read(1, timeout=timeout)[0]
                data = self._read(length, timeout=timeout)
                chk = self._read(1, timeout=timeout)[0]
                msg = Message(type, data)

                if self._logger:
                    logMsg = bytearray([sync, length, type])
                    logMsg.extend(data)
                    logMsg.append(chk)

                    self._logger.log(bytes(logMsg))

                if msg.checksum() == chk:
                    return msg

    def write(self, msg: Message) -> None:
        if not self.isOpen():
            raise DriverException("Device is closed")

        with self._lock:
            self._write(msg.encode())

    @abstractmethod
    def _isOpen(self) -> bool:
        pass

    @abstractmethod
    def _open(self) -> None:
        pass

    @abstractmethod
    def _close(self) -> None:
        pass

    @abstractmethod
    def _read(self, count: int, timeout=None) -> bytes:
        pass

    @abstractmethod
    def _write(self, data: bytes) -> None:
        pass


class SerialDriver(Driver):
    """
    An implementation of a serial ANT+ device driver
    """

    def __init__(self, device: str, baudRate: int = 115200, logger: Logger = None):
        super().__init__(logger=logger)
        self._device = device
        self._baudRate = baudRate
        self._serial = None

    def __str__(self):
        if self.isOpen():
            return self._device + " @ " + str(self._baudRate)
        return None

    def _isOpen(self) -> bool:
        return self._serial is None

    def _open(self) -> None:
        try:
            self._serial = Serial(self._device, self._baudRate)
        except SerialException as e:
            raise DriverException(str(e))

        if not self._serial.isOpen():
            raise DriverException("Could not open specified device")

    def _close(self) -> None:
        self._serial.close()
        self._serial = None

    def _read(self, count: int, timeout=None) -> bytes:
        return self._serial.read(count, timeout=timeout)

    def _write(self, data: bytes) -> None:
        try:
            self._serial.write(data)
            self._serial.flush()
        except SerialTimeoutException as e:
            raise DriverException(str(e))


class USBDriver(Driver):
    """
    An implementation of a USB ANT+ device driver
    """

    def __init__(self, vid, pid, logger: Logger = None):
        super().__init__(logger=logger)
        self._idVendor = vid
        self._idProduct = pid
        self._dev = None
        self._epOut = None
        self._epIn = None
        self._interfaceNumber = None
        self._packetSize = 0x20
        self._queue = None
        self._loop = None
        self._driver_open = False

    def __str__(self):
        if self.isOpen():
            return str(self._dev)
        return "Closed"

    class USBLoop(Thread):
        def __init__(self, ep, packetSize: int, queue: Queue):
            super().__init__()
            self._stopper = Event()
            self._ep = ep
            self._packetSize = packetSize
            self._queue = queue

        def stop(self) -> None:
            self._stopper.set()

        def run(self) -> None:
            while not self._stopper.is_set():
                try:
                    data = self._ep.read(self._packetSize, timeout=1000)
                    for d in data:
                        self._queue.put(d)
                except usb.core.USBError as e:
                    if e.errno not in (60, 110) and e.backend_error_code != -116:  # Timout errors
                        self._stopper.set()
            # We Put in an invalid byte so threads will realize the device is stopped
            self._queue.put(None)

    def _isOpen(self) -> bool:
        return self._driver_open

    def _open(self) -> None:
        print('USB OPEN START')
        try:
            # find the first USB device that matches the filter
            self._dev = usb.core.find(idVendor=self._idVendor, idProduct=self._idProduct)

            if self._dev is None:
                raise DriverException("Could not open specified device")

            # Detach kernel driver
            try:
                if self._dev.is_kernel_driver_active(0):
                    try:
                        self._dev.detach_kernel_driver(0)
                    except usb.USBError as e:
                        raise DriverException("Could not detach kernel driver")
            except NotImplementedError:
                pass  # for non unix systems

            # set the active configuration. With no arguments, the first
            # configuration will be the active one
            self._dev.set_configuration()

            # get an endpoint instance
            cfg = self._dev.get_active_configuration()
            self._interfaceNumber = cfg[(0, 0)].bInterfaceNumber
            interface = usb.util.find_descriptor(cfg, bInterfaceNumber=self._interfaceNumber,
                                                 bAlternateSetting=usb.control.get_interface(self._dev,
                                                                                             self._interfaceNumber))
            usb.util.claim_interface(self._dev, self._interfaceNumber)

            self._epOut = usb.util.find_descriptor(interface, custom_match=lambda e: usb.util.endpoint_direction(
                e.bEndpointAddress) == usb.ENDPOINT_OUT)

            self._epIn = usb.util.find_descriptor(interface, custom_match=lambda e: usb.util.endpoint_direction(
                e.bEndpointAddress) == usb.ENDPOINT_IN)

            if self._epOut is None or self._epIn is None:
                raise DriverException("Could not initialize USB endpoint")

            self._queue = Queue()
            self._loop = self.USBLoop(self._epIn, self._packetSize, self._queue)
            self._loop.start()
            self._driver_open = True
            print('USB OPEN SUCCESS')
        except IOError as e:
            self._close()
            raise DriverException(str(e))

    def _close(self) -> None:
        print('USB CLOSE START')
        if self._loop is not None:
            if self._loop.is_alive():
                self._loop.stop()
                self._loop.join()
        self._loop = None
        try:
            self._dev.reset()
            usb.util.dispose_resources(self._dev)
        except:
            pass
        self._dev = self._epOut = self._epIn = None
        self._driver_open = False
        print('USB CLOSE END')

    def _read(self, count: int, timeout=None) -> bytes:
        data = bytearray()
        for i in range(0, count):
            b = self._queue.get(timeout=timeout)
            if b is None:
                self._close()
                raise DriverException("Device is closed!")
            data.append(b)
        return bytes(data)

    def _write(self, data: bytes) -> None:
        return self._epOut.write(data)


class DummyDriver(Driver):
    def __init__(self, logger: Logger = None):
        super().__init__(logger=logger)
        self._isopen = False
        self._data = Queue()
        msg1 = Message(MESSAGE_CHANNEL_BROADCAST_DATA, b'\x00\x01\x02\x03\x04\x05\x06\x07').encode()
        for b in msg1:
            self._data.put(b)
        msg2 = Message(MESSAGE_CHANNEL_BROADCAST_DATA, b'\x00\xF1\xF2\xF3\xF4\xF5\xF6\xF7').encode()
        for b in msg2:
            self._data.put(b)
        msg3 = Message(MESSAGE_CHANNEL_BROADCAST_DATA, b'\x00\xF9\xFA\xFB\xFC\xFD\xFE\xFF').encode()
        for b in msg3:
            self._data.put(b)

    def _isOpen(self) -> bool:
        return self._isopen

    def _close(self) -> None:
        self._isopen = False

    def _read(self, count: int, timeout=None) -> bytes:
        data = bytearray()
        for i in range(0, count):
            data.append(self._data.get(timeout=timeout))
        return bytes(data)

    def _open(self) -> None:
        self._isopen = True

    def _write(self, data: bytes) -> None:
        pass


class PcapDriver(Driver):
    def __init__(self, pcap, logger: Logger = None):
        super().__init__(logger=logger)
        self._isopen = False
        self._pcap = pcap
        self._buffer = Queue()

        self._loop = None

    class PcapLoop(Thread):
        def __init__(self, pcap, buffer: Queue):
            super().__init__()
            self._stopper = Event()
            self._pcap = pcap
            self._buffer = buffer

        def stop(self) -> None:
            self._stopper.set()

        def run(self) -> None:
            self._pcapfile = open(self._pcap, 'rb')
            # move file pointer to first packet header
            global_header_length = 24
            self._pcapfile.seek(global_header_length, 0)

            first_ts = 0
            start_time = time.time()
            while not self._stopper.is_set():
                try:
                    ts_sec, = unpack('i', self._pcapfile.read(4))
                except error:
                    break
                ts_usec = unpack('i', self._pcapfile.read(4))[0] / 1000000

                if first_ts is 0:
                    first_ts = ts_sec + ts_usec

                ts = ts_sec + ts_usec
                send_time = ts - first_ts
                elapsed_time = time.time() - start_time
                if send_time > (elapsed_time):
                    sleep_time = send_time - elapsed_time
                    time.sleep(sleep_time)

                packet_length = unpack('i', self._pcapfile.read(4))[0]
                self._pcapfile.seek(4, 1)
                for i in range(packet_length):
                    self._buffer.put(self._pcapfile.read(1))

            self._pcapfile.close()

    def _isOpen(self) -> bool:
        return self._isopen

    def _open(self) -> None:
        self._isopen = True
        self._loop = self.PcapLoop(self._pcap, self._buffer)
        self._loop.start()

    def _close(self) -> None:
        self._isopen = False
        if self._loop is not None:
            if self._loop.is_alive():
                self._loop.stop()
                self._loop.join()
        self._loop = None

    def _read(self, count: int, timeout=None) -> bytes:
        result = bytearray()

        while len(result) < count:
            result += self._buffer.get(block=True, timeout=timeout)

        return bytes(result)

    def _write(self, data: bytes) -> None:
        pass
