import os
import time
import logging

BASE_FILE = os.path.dirname(os.path.abspath(__file__))


def create_log_file(requirement_id):
    logs_base_path = os.path.join(BASE_FILE, 'test_logs')

    if not os.path.exists(logs_base_path):
        os.mkdir(logs_base_path)

    latest_link = logs_base_path + '/latest'

    timestamp = time.strftime("%Y-%m-%d-%H:%M:%S")
    log_file = requirement_id + '-' + timestamp
    log_path = os.path.join(logs_base_path, log_file)

    os.mkdir(log_path)

    if os.path.exists(latest_link):
        os.unlink(latest_link)

    os.symlink(log_path, latest_link)
    return log_path


class Log(object):
    def __init__(self, name=None):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level = logging.DEBUG)
        if name:
            self._format = '%(asctime)s - %(name)s - %(levelname)-7s || %(message)s'
        else:
            self._format = '%(asctime)s - %(levelname)-7s || %(message)s'

    def debug(self, msg, *args, **kwargs):
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._logger.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self._logger.critical(msg, *args, **kwargs)

    def log(self, level, msg, *args, **kwargs):
        self._logger.log(level, msg, *args, **kwargs)


class LogFile(Log):
    def __init__(self, filename, name=None):
        super(LogFile, self).__init__(name)
        self._handler = logging.FileHandler(filename)
        self._handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(self._format)
        self._handler.setFormatter(formatter)
        self._logger.addHandler(self._handler)


class LogStream(Log):
    def __init__(self, name=None):
        super(LogStream, self).__init__(name)
        self._handler = logging.StreamHandler()
        self._handler.setLevel(logging.DEBUG)

        self._logger.addHandler(self._handler)


class LogFileStream(Log):
    def __init__(self, filename, name=None):
        super(LogFileStream, self).__init__(name)
        formatter = logging.Formatter(self._format)

        self._file = logging.FileHandler(filename)
        self._file.setLevel(logging.DEBUG)
        self._file.setFormatter(formatter)

        self._console = logging.StreamHandler()

        self._logger.addHandler(self._file)
        self._logger.addHandler(self._console)


if __name__ == "__main__":
    log = LogFileStream('log.txt')
    log.info("Start print log")
    log.debug("Do something")
    log.warning("Something maybe fail.")
    log.info("Finish")

    pass