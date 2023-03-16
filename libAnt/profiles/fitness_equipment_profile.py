#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from libAnt.core import lazyproperty
from libAnt.profiles.profile import ProfileMessage
import libAnt.message as m 
import libAnt.constants as c
import libAnt.exceptions as e


# %%FE-C Tx Messages
class SetTrackResistancePage(m.AcknowledgedMessage):
    """ANT FE-C Section 8.10.2

    Transmit grade change request
    """

    def __init__(self, channel_num: int, grade: int, C_RR=0xFF):
        pg_num = c.PAGE_TRACK_RESISTANCE
        byte1 = byte2 = byte3 = byte4 = 0xFF
        content = bytearray([pg_num, byte1,
                             byte2, byte3, byte4])
        content.extend(int(grade).to_bytes(2, byteorder='big'))
        content.append(C_RR)
        super().__init__(channel_num, content)


class UserConfigurationPage(m.AcknowledgedMessage):
    """ANT FE-C Section 8.10.2

    Transmit user entered data relating to config for virtual environment
    """

    def __init__(self, channel_num: int,
                 user_weight=0xFFFF,
                 wheel_diameter_offset=0xF,
                 bike_weight=0xFFF,
                 bike_wheel_diameter=0xFF,
                 gear_ratio=0x00):
        pg_num = c.PAGE_USER_CONFIGURATION
        weight_bytes = (int(user_weight).to_bytes(2, byteorder='big'))
        byte3 = 0xFF
        offset_bits = bin(int(wheel_diameter_offset))[2:]
        bike_weight_bits = bin(int(bike_weight))[2:].zfill(12)
        bike_weight_LSB = bike_weight_bits[8:]
        bike_weight_MSB = bike_weight_bits[0:8]
        byte4_bits = offset_bits + bike_weight_LSB
        byte4 = (m.bits_2_num(byte4_bits))
        byte5 = (m.bits_2_num(bike_weight_MSB))
        content = bytearray([pg_num])
        content.extend(weight_bytes)
        append_list = [byte3, byte4, byte5, bike_wheel_diameter, gear_ratio]
        for x in append_list:
            content.append(x)

        super().__init__(channel_num, bytes(content))
        self.reply_type = c.MESSAGE_RF_EVENT
        self.source = 'Host'
        self.callback = self.device_reply


def set_user_config(channel_num,
                    user_weight=75,
                    wheel_diamater_offset=0,
                    bike_weight=10,
                    bike_wheel_diameter=700,
                    gear_ratio=0):
    """
    Set user config on trainer

    Parameters
    ----------
    channel_num: int
        Channel number on node
    user_weight: float, optional
        User weight in [kg]
    wheel_diameter_offset: float, optional
        Bike wheel diameter offset adds [mm] precision to wheel diameter
    bike_weight, float optional
        Bike weidht in [kg]
    bike_wheel_diameter
        Bike wheel diameter in mm

    Returns
    -------
    config_msg: UserConfigurationPage
        Formatted message object to be sent to device
    """
    usr_wt_set = int(user_weight / 0.01)
    bike_weight_set = int(bike_weight/0.05)
    bike_wheel_d_set = int(bike_wheel_diameter*0.1)
    gear_ratio_set = int(gear_ratio/0.03)
    config_msg = UserConfigurationPage(channel_num,
                                       user_weight=usr_wt_set,
                                       bike_weight=bike_weight_set,
                                       bike_wheel_diameter=bike_wheel_d_set,
                                       gear_ratio=gear_ratio_set)
    return config_msg


def set_grade(channel_num, grade_in):
    """
    Set grade on trainer

    Parameters
    ----------
    channel_num: int
        Channel number on node
    grade: float
        Grade value in percent []

    Returns
    -------
    grade_msg: SetTrackResistancePage
        Formatted message object to be sent to device
    """

    grade_set = int((grade_in + 200) / 0.01)
    grade_msg = SetTrackResistancePage(channel_num, grade=grade_set)
    return(grade_msg)


class FitnessEquipmentProfileMessage(ProfileMessage):
    """ Message from Specific Trainer / Stationary Bike """

    maxAccumulatedPower = 65536
    maxEventCount = 256

    def __str__(self):
        return super().__str__() + ' Power: {0:.0f}W'.format(self.averagePower)

    @lazyproperty
    def dataPageNumber(self):
        """
        :return: Data Page Number (int)
        """
        return self.msg.content[0]

    @lazyproperty
    def eventCount(self):
        """
        The update event count field is incremented each time the information in the message is updated.
        There are no invalid values for update event count.
        The update event count in this message refers to updates of the Specific Trainer main data page (0x19)
        :return: Power Event Count
        """
        return self.msg.content[1]

    @lazyproperty
    def instantaneousCadence(self):
        """
        The instantaneous cadence field is used to transmit the pedaling cadence recorded from the power sensor.
        This field is an instantaneous value only; it does not accumulate between messages.
        :return: Instantaneous Cadence (W)
        """
        return self.msg.content[2]

    @lazyproperty
    def accumulatedPower(self):
        """
        Accumulated power is the running sum of the instantaneous power data and is incremented at each update
        of the update event count. The accumulated power field rolls over at 65.535kW.
        :return:
        """
        return (self.msg.content[4] << 8) | self.msg.content[3]

    @lazyproperty
    def instantaneousPower(self):
        """ Instantaneous power (W) """
        return ((bin(self.msg.content[6]) & bin(240)) << 8) | self.msg.content[5]
        # come back and check here

    @lazyproperty
    def accumulatedPowerDiff(self):
        if self.previous is None:
            return None
        elif self.accumulatedPower < self.previous.accumulatedPower:
            # Rollover
            return (self.accumulatedPower - self.previous.accumulatedPower) + self.maxAccumulatedPower
        else:
            return self.accumulatedPower - self.previous.accumulatedPower

    @lazyproperty
    def eventCountDiff(self):
        if self.previous is None:
            return None
        elif self.eventCount < self.previous.eventCount:
            # Rollover
            return (self.eventCount - self.previous.eventCount) + self.maxEventCount
        else:
            return self.eventCount - self.previous.eventCount

    @lazyproperty
    def averagePower(self):
        """
        Under normal conditions with complete RF reception, average power equals instantaneous power.
        In conditions where packets are lost, average power accurately calculates power over the interval
        between the received messages
        :return: Average power (Watts)
        """
        if self.previous is None:
            return self.instantaneousPower
        if self.eventCount == self.previous.eventCount:
            return self.instantaneousPower
        return self.accumulatedPowerDiff / self.eventCountDiff

