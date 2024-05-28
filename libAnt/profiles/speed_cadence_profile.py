from libAnt.core import lazyproperty
from libAnt.profiles.profile import ProfileMessage
from datetime import datetime


class SpeedCadencePage(ProfileMessage):
    """ Message from Speed & Cadence sensor """

    MAX_CADENCE_EVENT_TIME = 65536
    MAX_SPEED_EVENT_TIME = 65536
    MAX_CADENCE_REV_COUNT = 65536
    MAX_SPEED_REV_COUNT = 65536

    maxstaleSpeedCounter = 7
    maxstaleCadenceCounter = 7

    def __init__(self, msg, wheel_diameter, previous=None):
        super().__init__(msg, previous)
        self.wheel_diameter = wheel_diameter
        self.msg = msg
        self.previous = previous
        self.timestamp = datetime.now()
        # self.staleSpeedCounter = previous.staleSpeedCounter if previous is not None else 0
        # self.staleCadenceCounter = previous.staleCadenceCounter if previous is not None else 0
        self.total_cadence_revs = previous.total_revs + \
            self.cadence_rev_count_diff if previous is not None else 0
        self.total_speed_revs = previous.total_speed_revs + \
            self.speed_rev_count_diff if previous is not None else 0

        # if self.previous is not None:
        #     if self.speedEventTime == self.previous.speedEventTime:
        #         self.staleSpeedCounter += 1
        #     else:
        #         self.staleSpeedCounter = 0

        #     if self.cadenceEventTime == self.previous.cadenceEventTime:
        #         self.staleCadenceCounter += 1
        #     else:
        #         self.staleCadenceCounter = 0

    def __str__(self):
        ret = '{} Speed: {:.2f}m/s (avg: {:.2f}m/s)\n'.format(super().__str__(), self.speed,
                                                              self.avg_speed)
        ret += '{} Cadence: {:.2f}rpm (avg: {:.2f}rpm)\n'.format(
            super().__str__(), self.cadence, self.avg_cadence)
        ret += '{} Total Distance: {:.2f}m\n'.format(
            super().__str__(), self.total_distance)
        ret += '{} Total Revolutions: {:d}'.format(
            super().__str__(), self.total_revs)
        return ret

    @lazyproperty
    def cadence_event_time(self):
        """ Represents the time of the last valid bike cadence event (1/1024 sec) """
        return (self.msg.content[1] << 8) | self.msg.content[0]

    @lazyproperty
    def cumulative_cadence_rev_count(self):
        """ Represents the total number of pedal revolutions """
        return (self.msg.content[3] << 8) | self.msg.content[2]

    @lazyproperty
    def speed_event_time(self):
        """ Represents the time of the last valid bike speed event (1/1024 sec) """
        return (self.msg.content[5] << 8) | self.msg.content[4]

    @lazyproperty
    def cumulative_speed_rev_count(self):
        """ Represents the total number of wheel revolutions """
        return (self.msg.content[7] << 8) | self.msg.content[6]

    @lazyproperty
    def speed_event_time_diff(self):
        if self.previous is None:
            return 0
        elif self.speed_event_time < self.previous.speed_event_time:
            # Rollover
            return (self.speed_event_time - self.previous.speed_event_time) + self.MAX_SPEED_EVENT_TIME
        else:
            return self.speed_event_time - self.previous.speed_event_time

    @lazyproperty
    def cadence_event_time_diff(self):
        if self.previous is None:
            return 0
        elif self.cadence_event_time < self.previous.cadence_event_time:
            # Rollover
            return (self.cadence_event_time - self.previous.cadence_event_time) + self.MAX_CADENCE_EVENT_TIME
        else:
            return self.cadence_event_time - self.previous.cadence_event_time

    @lazyproperty
    def speed_rev_count_diff(self):
        if self.previous is None:
            return 0
        elif self.cumulative_speed_rev_count < self.previous.cumulative_speed_rev_count:
            # Rollover
            return (
                self.cumulative_speed_rev_count - self.previous.cumulative_speed_rev_count) + self.MAX_SPEED_REV_COUNT
        else:
            return self.cumulative_speed_rev_count - self.previous.cumulative_speed_rev_count

    @lazyproperty
    def cadence_rev_count_diff(self):
        if self.previous is None:
            return 0
        elif self.cumulative_cadence_rev_count < self.previous.cumulative_cadence_rev_count:
            # Rollover
            return (
                self.cumulative_cadence_rev_count - self.previous.cumulative_cadence_rev_count) + self.MAX_CADENCE_REV_COUNT
        else:
            return self.cumulative_cadence_rev_count - self.previous.cumulative_cadence_rev_count

    @lazyproperty
    def speed(self):
        """
        :param c: circumference of the wheel (mm)
        :return: The current speed (m/sec)
        """
        if self.previous is None:
            return 0
        if self.speed_event_time == self.previous.speed_event_time:
            # if self.staleSpeedCounter > self.maxstaleSpeedCounter:
            #     return 0
            return self.previous.speed
        ret_value = self.speed_rev_count_diff * 1.024 * \
            self.wheel_diameter / self.speed_event_time_diff
        return ret_value

    @lazyproperty
    def distance(self):
        """
        :param c: circumference of the wheel (mm)
        :return: The distance since the last message (m)
        """
        return self.speed_rev_count_diff * self.wheel_diameter / 1000

    @lazyproperty
    def total_distance(self):
        """
        :param c: circumference of the wheel (mm)
        :return: The total distance since the first message (m)
        """
        return self.total_speed_revs * self.wheel_diameter / 1000

    @lazyproperty
    def cadence(self):
        """
        :return: RPM
        """
        if self.previous is None:
            return 0
        if self.cadence_event_time == self.previous.cadence_event_time:
            # if self.staleCadenceCounter > self.maxstaleCadenceCounter:
            #     return 0
            return self.previous.cadence
        return self.cadence_rev_count_diff * 1024 * 60 / self.cadence_event_time_diff

    # def averageSpeed(self, c):
    #     """
    #     Returns the average speed since the first message
    #     :param c: circumference of the wheel (mm)
    #     :return: m/s
    #     """
    #     if self.firstTimestamp == self.timestamp:
    #         return self.speed(c)
    #     return self.totalDistance(c) / (self.timestamp - self.firstTimestamp)
