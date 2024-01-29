from libAnt.core import lazyproperty
from libAnt.profiles.profile import ProfileMessage
from datetime import datetime

import libAnt.message as m


class PowerDataPage(ProfileMessage):
    """Power Data from Power Profile device."""

    max_accumulated_power = 65536
    max_event_count = 256

    def __init__(self, msg: m.BroadcastMessage, prev):
        self.msg = msg
        if self.page_number != 0x10:
            return ("Error: Unrecognized Page Type!")
        self.previous = prev
        self.timestamp = datetime.now()

    def __str__(self):
        """Reformat to show most relevant information."""
        return super().__str__() + ' Power: {0:.0f}W'.format(self.avg_power)

    @lazyproperty
    def page_number(self):
        """Unpack page number field.

        :return: Data Page Number (int)
        """
        return self.msg.content[0]

    @lazyproperty
    def event(self):
        """Unpack event count field.

        The update event count field is incremented each time the information
        in the message is updated. There are no invalid values for update event
        count. The update event count in this message refers to updates of the
        standard Power-Only main data page (0x10)

        :return: Power Event Count
        """
        return self.msg.content[1]

    @lazyproperty
    def inst_cadence(self):
        """Unpack instantaneous cadence [RPM] field.

        The instantaneous cadence field is used to transmit the pedaling
        cadence recorded from the power sensor. This field is an instantaneous
        value only; it does not accumulate between messages.

        :return: Instantaneous Cadence (W)
        """
        return self.msg.content[3]

    @lazyproperty
    def accumulated_power(self):
        """Unpack accumulated power [W] field.

        Accumulated power is the running sum of the instantaneous power data
        and is incremented at each update of the update event count. The
        accumulated power field rolls over at 65.535kW.

        Returns
        -------
        Accumulated power [W] : int

        """
        return (self.msg.content[5] << 8) | self.msg.content[4]

    @lazyproperty
    def inst_power(self):
        """Unpack Instantaneous power (W)."""
        return (self.msg.content[7] << 8) | self.msg.content[6]

    @lazyproperty
    def accumulated_pwr_diff(self):
        """Accumulated power reading accounting for potential rollover."""
        if self.previous is None:
            return None
        elif self.accumulated_power < self.previous.accumulated_power:
            # Rollover
            return ((self.accumulated_power - self.previous.accumulated_power)
                    + self.max_accumulated_power)
        else:
            return self.accumulated_power - self.previous.accumulated_power

    @lazyproperty
    def event_count_diff(self):
        """Return event count accounting for potential rollover."""
        if self.previous is None:
            return None
        elif self.event < self.previous.event:
            # Rollover
            return (self.event - self.previous.event) + self.max_event_count
        else:
            return self.event - self.previous.event

    @lazyproperty
    def avg_power(self):
        """Power reading accounting for potential lost packets.

        Under normal conditions with complete RF reception, average power
        equals instantaneous power. In conditions where packets are lost,
        average power accurately calculates power over the interval between
        the received messages
        :return: Average power (Watts)
        """
        if self.previous is None:
            return self.inst_power
        if self.event == self.previous.event:
            return self.inst_power
        return self.accumulated_pwr_diff / self.event_count_diff


class TorqueDataPage:
    """Torque Data from Power Profile Device."""

    max_accumulated_torque = 2048
    max_event_count = 256
    max_accumulated_wheel_period = 32

    def __init__(self, msg: m.BroadcastMessage, prev):
        self.msg = msg
        if self.page_number != 0x11:
            return ("Error: Unrecognized Page Type!")
        self.previous = prev
        self.timestamp = datetime.now()

    def __str__(self):
        """Reformat to show most relevant information."""
        return super().__str__() + 'Torque: {0:.0f}W'.format(self.avg_torque)

    @lazyproperty
    def page_number(self):
        """Unpack page number field.

        :return: Data Page Number (int)
        """
        return self.msg.content[0]

    @lazyproperty
    def event(self):
        """Unpack event count field.

        The update event count field is incremented each time the information
        in the message is updated. There are no invalid values for update event
        count. The update event count in this message refers to updates of the
        standard Power-Only main data page (0x10)

        :return: Power Event Count
        """
        return self.msg.content[1]

    @lazyproperty
    def wheel_ticks(self):
        """Unpack Wheel Tick Field.

        The wheel ticks field increments with each wheel revolution and is used
        to calculate linear distance traveled. The wheel ticks field rolls over
        every 256 wheel revolutions, which is approximately 550 meters assuming
        a 2m wheel circumference. There are no invalid values for this field.
        """
        return (self.msg.content[2])

    @lazyproperty
    def inst_cadence(self):
        """Unpack instantaneous cadence [RPM] field.

        The instantaneous cadence field is used to transmit the pedaling
        cadence recorded from a crank based meter. This field is an
        instantaneous value only; it does not accumulate between messages.

        :return: Instantaneous Cadence (W)
        """
        return self.msg.content[3]

    @lazyproperty
    def accumulated_wheel_period(self):
        """Unpack accumulated power [W] field.

        Accumulated power is the running sum of the instantaneous power data
        and is incremented at each update of the update event count. The
        accumulated power field rolls over at 65.535kW.

        Returns
        -------
        Accumulated power [W] : int

        """
        return (self.msg.content[5] << 8) | self.msg.content[4]

    @lazyproperty
    def accumulated_torque(self):
        """Unpack Instantaneous power (W)."""
        return (self.msg.content[7] << 8) | self.msg.content[6]

    @lazyproperty
    def accumulated_torque_diff(self):
        """Accumulated power reading accounting for potential rollover."""
        if self.previous is None:
            return None
        elif self.accumulated_torque < self.previous.accumulated_torque:
            # Rollover
            return (self.accumulated_torque - self.previous.accumulated_torque
                    + self.max_accumulated_torque)
        else:
            return self.accumulated_torque - self.previous.accumulated_torque

    @lazyproperty
    def accumulated_wheel_period_diff(self):
        """Accumulated wheel period accounting for potential rollover."""
        if self.previous is None:
            return None
        elif (self.accumulated_wheel_period
              < self.previous.accumulated_wheel_period):
            # Rollover
            return ((self.accumulated_wheel_period
                     - self.previous.accumulated_wheel_period)
                    + self.max_accumulated_wheel_period)
        else:
            return (self.accumulated_wheel_period
                    - self.previous.accumulated_wheel_period)

    @lazyproperty
    def event_count_diff(self):
        """Return event count accounting for potential rollover."""
        if self.previous is None:
            return None
        elif self.event < self.previous.event:
            # Rollover
            return (self.event - self.previous.event) + self.max_event_count
        else:
            return self.event - self.previous.event

    @lazyproperty
    def avg_torque(self):
        """Power reading accounting for potential lost packets.

        Under normal conditions with complete RF reception, average power
        equals instantaneous power. In conditions where packets are lost,
        average power accurately calculates power over the interval between
        the received messages
        :return: Average power (Watts)
        """
        if self.previous is None:
            return

        # Case for retransmitted packet
        if self.event == self.previous.event:
            return self.previous.avg_torque

        else:
            return self.accumulated_torque_diff / self.event_count_diff

    @lazyproperty
    def avg_wheel_period(self):
        """Power reading accounting for potential lost packets.

        Under normal conditions with complete RF reception, average power
        equals instantaneous power. In conditions where packets are lost,
        average power accurately calculates power over the interval between
        the received messages
        :return: Average power (Watts)
        """
        if self.previous is None:
            return

        if self.event == self.previous.event:
            return self.previous.avg_wheel_period

        else:
            return self.accumulated_wheel_period_diff / self.event_count_diff
