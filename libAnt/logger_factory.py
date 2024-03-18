"""
Created on Mon Jul 11 14:10:18 2022

@author: test
"""

import logging
import os
from datetime import datetime
from io import StringIO as StringBuffer
import sys


class LoggerFactory(logging.Logger):
    """Create a logger Object on the root level in the main program.

    Have child instances in each module. However it would be easier to
    have the logging module only live in here and have this class be
    imported into all modules that use it.

    Attributes
    ----------
    logger : Logger object
        internal logger instance of logger class

    Methods
    -------
    logger_setup(log_path)
        Setup logger instance within a module with formatting and references
    GUI_console_logger()
        Setup logger for logging and displaying messages to GUI console
    add_logging_level(level_name, level_num, method_name=None)
        Add logging level to base logger

    """

    def __init__(self, log_name=None, log_path=None):
        """Construct LoggerFactory Object.

        Construct a logger object with name and specified save path if defined,
        or create logger object referencing root logger if not.
        """

        if log_path:
            if not os.path.exists(log_path):
                os.makedirs(log_path)

            super(LoggerFactory, self).__init__(logging.getLogger())
            print('Full Logger Setup')
            self.logger_setup(log_path)

        else:
            # self = logging.getLogger(__name__)
            super(LoggerFactory, self).__init__(logging.getLogger(log_name))

            if not logging.getLogger().hasHandlers():
                print('Just Console Logger Setup')
                self.logger_setup()

            if not hasattr(logging, 'CONSOLE'):
                self.add_logging_level('CONSOLE', 25)

        self.logger = logging.getLogger()

##############################################################################

    def logger_setup(self, log_path=None):
        """Setup logger within a module.

        Parameters
        ----------
        log_path : str
            Directory path of log save file

        Returns
        -------
        None.
        """

        # Define a format object for the logger
        log_format = logging.Formatter(
            """[%(asctime)s] [%(module)s:%(lineno)d] [%(funcName)s] [%(levelname)s] %(message)s""")

        # Create a reference to the root logger
        logger = logging.getLogger()

        # Add handlers for writing to log file and console printing
        if log_path:
            # Construct the full file path for the logger save file
            now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path_name = os.path.join(log_path, f"{now}_logfile.LOG")

            file_handler = logging.FileHandler(path_name, 'w')
            file_handler.setFormatter(log_format)
            file_handler.setLevel(logging.DEBUG)
            logger.addHandler(file_handler)

        else:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(log_format)
            console_handler.setLevel(logging.INFO)
            logger.addHandler(console_handler)

        logger.setLevel(logging.NOTSET)

##############################################################################

    def GUI_console_logger(self):
        """Define stream handler to write to GUI console feature

        Parameters
        ----------
        None.

        Returns
        -------
        None.
        """

        self.logger = logging.getLogger()
        self.logger.log_capture_string = StringBuffer()
        GUI_handler = logging.StreamHandler(self.logger.log_capture_string)
        GUI_handler.setLevel(logging.CONSOLE)
        log_format = logging.Formatter(
            '[%(asctime)s] [%(module)s] %(message)s',
            datefmt="%H:%M:%S")
        GUI_handler.setFormatter(log_format)
        self.logger.addHandler(GUI_handler)

###############################################################################

    def add_logging_level(self, level_name, level_num, method_name=None):
        """Add new level to the `logging` module and the current logging class.

        Parameters
        ----------
        level_name : str
            Becomes an attribute of the `logging` module with the same value
        levle_num : int
            Numeric value of the custom level corresponding to one of the
            default logger heirarchy levels
        method_name : method object, optional
            A convience method for the logging class, if not specified,
            level_name.lower() is used for method_name

        To avoid accidental clobberings of existing attributes, this method
        will raise an `AttributeError` if the level name is already an
        attribute of the `logging` module or if the method name is already
        present

        Example
        -------
        >>> addLoggingLevel('TRACE', logging.DEBUG - 5)
        >>> logging.getLogger(__name__).setLevel("TRACE")
        >>> logging.getLogger(__name__).trace('that worked')
        >>> logging.trace('so did this')
        >>> logging.TRACE
        5

        """

        if not method_name:
            method_name = level_name.lower()

        if hasattr(logging, level_name):
            sys.exit("You must restart Console to relaunch program")
            # raise AttributeError(
            #     f'{level_name} already defined in logging module')
        if hasattr(logging, method_name):
            raise AttributeError(
                f'{method_name} already defined in logging module')
        if hasattr(logging.getLoggerClass(), method_name):
            raise AttributeError(
                f'{method_name} already defined in logger class')

        # This method was inspired by the answers to Stack Overflow post
        # http://stackoverflow.com/q/2183233/2988730, especially
        # http://stackoverflow.com/a/13638084/2988730
        def log_for_level(self, message, *args, **kwargs):
            if self.isEnabledFor(level_num):
                self._log(level_num, message, args, **kwargs)

        def log_to_root(message, *args, **kwargs):
            logging.log(level_num, message, *args, **kwargs)

        logging.addLevelName(level_num, level_name)
        setattr(logging, level_name, level_num)
        setattr(logging.getLoggerClass(), method_name, log_for_level)
        setattr(logging, method_name, log_to_root)
